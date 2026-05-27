import re
import traceback
import logging
from fastapi import APIRouter, HTTPException, Query
from backend.db.schemas import MetricsInput, AlertResponse, PatternMatch, RecoveryScenario, EscapePlan, EscapeIntervention
from backend.services.adk_runner import run_analysis_via_adk
from backend.services.output_writer import write_alert
from backend.services.pattern_matcher import compute_oracle_score, build_recovery_scenario, compute_escape_plan, match_patterns_top3

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", response_model=AlertResponse)
async def analyze_metrics(metrics: MetricsInput):
    """
    Analyze startup metrics via the Google ADK agent.
    The ADK agent orchestrates: MongoDB Atlas Vector Search → Gemini scoring → result.
    Also runs multi-pattern Cocktail matching in parallel to detect co-occurring failure modes.
    """
    import asyncio as _asyncio
    try:
        result, cocktail = await _asyncio.gather(
            run_analysis_via_adk(metrics),
            match_patterns_top3(metrics),
            return_exceptions=True,
        )
        if isinstance(result, Exception):
            raise result
        if isinstance(cocktail, Exception):
            cocktail = None

        if not result.get("alert"):
            score, band = compute_oracle_score(metrics, 0.0)
            return AlertResponse(
                alert=False,
                startup_name=metrics.startup_name,
                cocktail=cocktail,
                oracle_score=score,
                score_band=band,
                message=result.get("message", "No dangerous failure patterns detected."),
            )

        pattern_data = result.get("pattern", {})
        match = PatternMatch(**pattern_data)
        output_file = write_alert(match, metrics)
        match.output_file = output_file

        score, band = compute_oracle_score(metrics, match.confidence)
        recovery_raw = build_recovery_scenario(metrics, match.confidence)
        recovery = RecoveryScenario(
            pattern_name=match.pattern_name,
            confidence=recovery_raw["confidence"],
            survival_rate=match.survival_rate,
            improvements=recovery_raw["improvements"],
            score_delta=recovery_raw["score_delta"],
        )
        escape_raw = compute_escape_plan(metrics, pattern_data, match.confidence)
        escape = EscapePlan(**{
            **escape_raw,
            "interventions": [EscapeIntervention(**i) for i in escape_raw["interventions"]],
        }) if escape_raw else None

        # Cascade Graph — $graphLookup + ACID transaction (non-blocking, best-effort)
        cascade_result = None
        try:
            from backend.services.cascade import compute_full_cascade
            cascade_result = await compute_full_cascade(metrics, match.pattern_id, float(match.confidence))
        except Exception as ce:
            logger.warning("[analyze] Cascade computation failed (non-fatal): %s", ce)

        return AlertResponse(
            alert=True,
            startup_name=metrics.startup_name,
            pattern=match,
            cocktail=cocktail,
            oracle_score=score,
            score_band=band,
            recovery_scenario=recovery,
            escape_plan=escape,
            cascade=cascade_result,
            message=result.get("message", f"Pattern detected at {int(match.confidence*100)}%."),
        )
    except Exception as e:
        logger.error("ERROR in analyze_metrics:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{startup_name}")
async def startup_history(startup_name: str):
    """
    Time-series analysis history for a startup using MongoDB $setWindowFields
    (running average confidence) and $bucket (confidence-tier distribution).

    Both aggregations run against the startup_analyses collection.
    Returns raw check history with running-average trend line + bucket summary.
    """
    from backend.db.connection import get_db
    db = get_db()

    # Running average via $setWindowFields (MongoDB 5.0+)
    history_pipeline = [
        {"$match": {"startup_name": startup_name}},
        {"$sort": {"checked_at": 1}},
        {
            "$setWindowFields": {
                "sortBy": {"checked_at": 1},
                "output": {
                    "running_avg_confidence": {
                        "$avg": "$confidence",
                        "window": {"documents": ["unbounded", "current"]},
                    },
                    "check_number": {"$documentNumber": {}},
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "checked_at": 1,
                "alert": 1,
                "pattern_name": 1,
                "confidence": 1,
                "days_to_crisis": 1,
                "running_avg_confidence": {"$round": ["$running_avg_confidence", 3]},
                "check_number": 1,
            }
        },
    ]

    # Confidence-tier distribution via $bucket
    bucket_pipeline = [
        {"$match": {"startup_name": startup_name}},
        {
            "$bucket": {
                "groupBy": "$confidence",
                "boundaries": [0.0, 0.25, 0.50, 0.75, 1.0],
                "default": "unscored",
                "output": {
                    "count": {"$sum": 1},
                    "avg_days_to_crisis": {"$avg": "$days_to_crisis"},
                },
            }
        },
    ]

    try:
        history = await db["startup_analyses"].aggregate(history_pipeline).to_list(length=50)
        buckets = await db["startup_analyses"].aggregate(bucket_pipeline).to_list(length=10)
    except Exception as e:
        logger.warning("history aggregation failed for %s: %s", startup_name, e)
        raise HTTPException(status_code=500, detail="History aggregation failed")

    if not history:
        raise HTTPException(status_code=404, detail=f"No analysis history found for '{startup_name}'")

    return {
        "startup_name": startup_name,
        "total_checks": len(history),
        "history": history,
        "confidence_buckets": buckets,
    }


@router.get("/autocomplete")
async def startup_autocomplete(q: str = Query(default="", min_length=0)):
    """
    Startup name autocomplete — searches the startup_analyses collection.

    Primary:  MongoDB Atlas Search autocomplete index ('startup_autocomplete').
    Fallback: Motor regex search (always works, no special index needed).

    The Atlas Search autocomplete index should be created in the Atlas UI with:
      field: startup_name, tokenization: edgeGram, minGrams: 2, maxGrams: 10
    """
    if len(q) < 2:
        return {"suggestions": [], "source": "empty"}

    from backend.db.connection import get_db
    db = get_db()

    # Try Atlas Search autocomplete index first
    try:
        pipeline = [
            {
                "$search": {
                    "index": "startup_autocomplete",
                    "autocomplete": {
                        "query": q,
                        "path": "startup_name",
                        "fuzzy": {"maxEdits": 1},
                    },
                }
            },
            {"$group": {"_id": "$startup_name"}},
            {"$limit": 10},
            {"$project": {"_id": 0, "name": "$_id"}},
        ]
        results = await db["startup_analyses"].aggregate(pipeline).to_list(length=10)
        if results:
            logger.info("[Autocomplete] Atlas Search returned %d suggestions for '%s'", len(results), q)
            return {"suggestions": [r["name"] for r in results], "source": "atlas_autocomplete"}
    except Exception as e:
        logger.debug("[Autocomplete] Atlas Search autocomplete unavailable (%s), using regex fallback", e)

    # Regex fallback — works without any special index
    pattern = re.compile(re.escape(q), re.IGNORECASE)
    names = await db["startup_analyses"].distinct("startup_name", {"startup_name": pattern})
    return {"suggestions": sorted(names)[:10], "source": "regex_fallback"}
