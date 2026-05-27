"""
Cascade & Cohort API Routes
============================
GET  /api/cascade/{pattern_id}            — $graphLookup cascade chain
POST /api/cascade/analyze                 — full cascade + intervention for a startup
GET  /api/metrics/cohort                  — cohort percentile intelligence ($bucket + $facet)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from backend.db.connection import get_db
from backend.db.schemas import MetricsInput
from backend.services.cascade import compute_full_cascade, get_cascade_chain
from backend.services.pattern_matcher import match_patterns

logger = logging.getLogger(__name__)
router = APIRouter()


# ── GET /api/cascade/{pattern_id} ─────────────────────────────────────────────
@router.get("/{pattern_id}")
async def cascade_for_pattern(pattern_id: str):
    """
    MongoDB $graphLookup: traverse the failure cascade graph up to 3 hops
    from the given pattern, returning a full collapse timeline.
    """
    chain = await get_cascade_chain(pattern_id)
    if not chain:
        raise HTTPException(status_code=404, detail=f"Pattern {pattern_id} not found or has no cascade data")
    return chain


# ── POST /api/cascade/analyze ─────────────────────────────────────────────────
@router.post("/analyze")
async def cascade_for_startup(metrics: MetricsInput):
    """
    Full cascade analysis for a startup:
    1. Detect current failure pattern (vector search + Gemini)
    2. Traverse cascade chain ($graphLookup)
    3. Compute minimum interventions per cascade link
    4. Write result atomically (Motor ACID transaction)
    """
    pattern = await match_patterns(metrics)
    if not pattern:
        return {
            "alert": False,
            "startup_name": metrics.startup_name,
            "message": "No dangerous pattern detected — no cascade to compute.",
            "cascade": None,
        }

    cascade = await compute_full_cascade(metrics, pattern.pattern_id, float(pattern.confidence))

    return {
        "alert": True,
        "startup_name": metrics.startup_name,
        "pattern_id": pattern.pattern_id,
        "pattern_name": pattern.pattern_name,
        "confidence": pattern.confidence,
        "days_to_crisis": pattern.days_to_crisis,
        "cascade": cascade,
    }


# ── GET /api/metrics/cohort ───────────────────────────────────────────────────
@router.get("/cohort/intelligence")
async def cohort_intelligence(
    industry: str = Query(default="B2B SaaS", description="Industry filter"),
    oracle_score: int = Query(default=50, ge=0, le=100, description="Your Oracle Score"),
    current_month: int = Query(default=12, ge=1, le=120, description="Startup age in months"),
):
    """
    Cohort percentile intelligence using MongoDB $bucket + $facet aggregation.

    Tells you:
    • Where you rank among all analyzed startups in your industry + stage
    • Distribution of Oracle Scores for similar companies
    • Most common failure patterns in your cohort
    • What the survivors did differently
    """
    db = get_db()

    month_min = max(1, current_month - 6)
    month_max = current_month + 6

    pipeline = [
        {
            "$match": {
                "industry": {"$regex": industry, "$options": "i"},
                "current_month": {"$gte": month_min, "$lte": month_max},
            }
        },
        {
            "$facet": {
                # Oracle Score distribution across similar cohort
                "score_distribution": [
                    {
                        "$bucket": {
                            "groupBy": "$oracle_score",
                            "boundaries": [0, 20, 40, 60, 80, 101],
                            "default": "unknown",
                            "output": {
                                "count": {"$sum": 1},
                                "avg_score": {"$avg": "$oracle_score"},
                            },
                        }
                    }
                ],
                # Alert rate for this cohort
                "alert_rate": [
                    {
                        "$group": {
                            "_id": "$alert",
                            "count": {"$sum": 1},
                        }
                    }
                ],
                # Top failure patterns in this cohort
                "top_patterns": [
                    {"$match": {"alert": True, "pattern_name": {"$exists": True, "$ne": None}}},
                    {"$group": {"_id": "$pattern_name", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                    {"$limit": 5},
                ],
                # Avg metrics for the cohort
                "cohort_averages": [
                    {
                        "$group": {
                            "_id": None,
                            "avg_oracle_score": {"$avg": "$oracle_score"},
                            "avg_churn": {"$avg": "$churn_rate"},
                            "avg_runway": {"$avg": "$runway_months"},
                            "total": {"$sum": 1},
                        }
                    }
                ],
                # Survivors (no alert, score > 60)
                "survivor_patterns": [
                    {"$match": {"alert": False, "oracle_score": {"$gte": 60}}},
                    {"$group": {
                        "_id": None,
                        "avg_score": {"$avg": "$oracle_score"},
                        "avg_churn": {"$avg": "$churn_rate"},
                        "avg_runway": {"$avg": "$runway_months"},
                        "count": {"$sum": 1},
                    }},
                ],
            }
        },
    ]

    try:
        results = await db["startup_analyses"].aggregate(pipeline).to_list(length=1)
    except Exception as e:
        logger.warning("[cohort] Aggregation failed: %s", e)
        raise HTTPException(status_code=500, detail="Cohort aggregation failed")

    if not results:
        return _empty_cohort(industry, oracle_score, current_month)

    facets = results[0]
    cohort_avgs = facets.get("cohort_averages", [{}])
    avg_data = cohort_avgs[0] if cohort_avgs else {}
    total_in_cohort = int(avg_data.get("total", 0))

    if total_in_cohort < 3:
        return _empty_cohort(industry, oracle_score, current_month)

    # Compute percentile rank
    score_dist = facets.get("score_distribution", [])
    startups_below = sum(
        b["count"] for b in score_dist
        if isinstance(b.get("_id"), (int, float)) and b["_id"] < oracle_score
    )
    percentile = round((startups_below / total_in_cohort) * 100) if total_in_cohort > 0 else 50

    # Alert rate
    alert_counts = {str(b["_id"]): b["count"] for b in facets.get("alert_rate", [])}
    at_risk_count = alert_counts.get("True", alert_counts.get("true", 0))
    alert_rate = round((at_risk_count / total_in_cohort) * 100) if total_in_cohort > 0 else 0

    # Survivor stats
    survivors = facets.get("survivor_patterns", [{}])
    survivor_data = survivors[0] if survivors else {}

    # Build cohort intelligence
    def _ordinal(n: int) -> str:
        """Return ordinal suffix: 1st, 2nd, 3rd, 4th…"""
        if 11 <= (n % 100) <= 13:
            return f"{n}th"
        return {1: f"{n}st", 2: f"{n}nd", 3: f"{n}rd"}.get(n % 10, f"{n}th")

    pord = _ordinal(percentile)
    if percentile <= 10:
        percentile_message = f"You are in the BOTTOM {pord} percentile — critical health for {industry} at Month {current_month}."
        percentile_severity = "critical"
    elif percentile <= 25:
        percentile_message = f"You are in the bottom quartile ({pord} percentile) for {industry} at Month {current_month}."
        percentile_severity = "warning"
    elif percentile <= 50:
        percentile_message = f"You are below median ({pord} percentile) for {industry} at Month {current_month}."
        percentile_severity = "watch"
    elif percentile <= 75:
        percentile_message = f"You are above median ({pord} percentile) for {industry} at Month {current_month}."
        percentile_severity = "healthy"
    else:
        percentile_message = f"You are in the top quartile ({pord} percentile) for {industry} at Month {current_month}."
        percentile_severity = "strong"

    return {
        "industry": industry,
        "current_month": current_month,
        "oracle_score": oracle_score,
        "total_in_cohort": total_in_cohort,
        "percentile": percentile,
        "percentile_message": percentile_message,
        "percentile_severity": percentile_severity,
        "cohort_alert_rate_pct": alert_rate,
        "cohort_avg_oracle_score": round(avg_data.get("avg_oracle_score", 0)),
        "cohort_avg_churn_pct": round((avg_data.get("avg_churn", 0)) * 100, 1),
        "cohort_avg_runway_months": round(avg_data.get("avg_runway", 0), 1),
        "top_failure_patterns": [
            {"pattern_name": p["_id"], "frequency": p["count"]}
            for p in facets.get("top_patterns", [])
        ],
        "survivor_avg_score": round(survivor_data.get("avg_score", 0)) if survivor_data else None,
        "survivor_avg_churn_pct": round((survivor_data.get("avg_churn", 0) or 0) * 100, 1),
        "survivor_avg_runway_months": round(survivor_data.get("avg_runway", 0) or 0, 1),
        "survivor_count": survivor_data.get("count", 0),
        "score_distribution": score_dist,
        "methodology": "$bucket + $facet aggregation on startup_analyses collection",
    }


def _empty_cohort(industry: str, oracle_score: int, current_month: int) -> dict:
    return {
        "industry": industry,
        "current_month": current_month,
        "oracle_score": oracle_score,
        "total_in_cohort": 0,
        "percentile": None,
        "percentile_message": f"Not enough data yet for {industry} at Month {current_month} cohort. Run more analyses to unlock cohort intelligence.",
        "percentile_severity": "unknown",
        "cohort_alert_rate_pct": None,
        "top_failure_patterns": [],
        "methodology": "$bucket + $facet aggregation on startup_analyses collection",
    }
