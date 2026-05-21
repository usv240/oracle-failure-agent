"""
Streaming analysis endpoint using Server-Sent Events (SSE).

Each real agent step emits an event as it happens:
  1. embed       — Gemini text-embedding-004 call
  2. search      — MongoDB Atlas Vector Search ($vectorSearch)
  3. mcp_fetch   — MongoDB MCP find (category enrichment)
  4. score_N     — Gemini 3 Flash scoring candidate N
  5. reeval      — Agent re-evaluation loop (if best score <70%)
  6. result      — Final pattern match or safe result

The frontend terminal receives these events in real-time.
"""
import json
import asyncio
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from backend.db.schemas import MetricsInput, PatternMatch, WarningSig
from backend.db.connection import get_db
from backend.services import gemini
from backend.services.mcp_client import mcp
from backend.services.output_writer import write_alert

logger = logging.getLogger(__name__)
router = APIRouter()


def _burn_multiple(m: MetricsInput) -> float:
    net = m.mrr * m.mrr_growth_rate
    return m.burn_rate / net if net > 0 else 99.0


def _ltv_cac(m: MetricsInput) -> float:
    return m.ltv / m.cac if m.cac > 0 else 0.0


def _evt(type_: str, **kwargs) -> str:
    return f"data: {json.dumps({'type': type_, **kwargs})}\n\n"


async def _score_pattern(metrics: MetricsInput, pattern: dict) -> dict:
    from backend.services.pattern_matcher import _score_with_gemini
    return await _score_with_gemini(metrics, pattern)


async def _run_agent_stream(metrics: MetricsInput):
    """Generator that yields SSE events as the agent executes."""

    db = get_db()

    # ── Step 1: Embed ────────────────────────────────────────────────
    yield _evt("step", icon="🤖", message="Oracle pipeline initializing — Gemini text-embedding-004 → Atlas Vector Search → MongoDB MCP → Gemini 3 Flash scoring")
    yield _evt("step", icon="🔢", message="Generating 768-dimensional embedding from 11 startup metrics via Gemini text-embedding-004...")

    query_text = (
        f"startup failure: month {metrics.current_month}, "
        f"churn {metrics.churn_rate*100:.0f}%, NPS {metrics.nps}, "
        f"burn ${metrics.burn_rate:,.0f}/month, runway {metrics.runway_months} months, "
        f"LTV:CAC {_ltv_cac(metrics):.1f}x, burn multiple {_burn_multiple(metrics):.1f}x"
    )
    try:
        query_vector = await gemini.embed(query_text)
    except Exception as e:
        yield _evt("error", message=f"Embedding failed: {e}")
        return

    yield _evt("step", icon="✅", message=f"768-dimensional embedding ready.")

    # ── Step 2: MongoDB Atlas Vector Search ─────────────────────────
    yield _evt("step", icon="🔍", message="Hybrid retrieval: MongoDB Atlas Vector Search (cosine similarity) + Atlas Search (BM25) — merging via Reciprocal Rank Fusion...")

    candidates = []
    try:
        from backend.services.pattern_matcher import _atlas_search_candidates, _reciprocal_rank_fusion
        vector_pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "narrative_embedding",
                    "queryVector": query_vector,
                    "numCandidates": 20,
                    "limit": 10,
                    "filter": {
                        "stage_month_min": {"$lte": metrics.current_month},
                        "stage_month_max": {"$gte": metrics.current_month},
                    },
                }
            },
            {"$project": {"narrative_embedding": 0}},
        ]
        vector_results, bm25_results = await asyncio.gather(
            db["failure_patterns"].aggregate(vector_pipeline).to_list(length=10),
            _atlas_search_candidates(metrics, query_text),
            return_exceptions=True,
        )
        if isinstance(vector_results, Exception):
            vector_results = []
        if isinstance(bm25_results, Exception):
            bm25_results = []
        if vector_results or bm25_results:
            merged = _reciprocal_rank_fusion([vector_results, bm25_results]) if bm25_results else vector_results
            candidates = merged[:5]
            src = "Vector Search + BM25 RRF" if bm25_results else "Vector Search"
            yield _evt("step", icon="✅", message=f"{src}: {len(vector_results)} vector + {len(bm25_results)} BM25 results merged → top {len(candidates)} candidates")
    except Exception as e:
        logger.warning("Hybrid search failed: %s", e)

    if not candidates:
        yield _evt("step", icon="⚠️", message="Hybrid search returned no results — running numeric filter fallback...")
        from backend.services.pattern_matcher import _candidate_patterns
        candidates = await _candidate_patterns(metrics)

    if not candidates:
        yield _evt("safe", message="No patterns matched your metrics. Your trajectory looks healthy.")
        return

    names = [p["name"] for p in candidates]
    yield _evt("step", icon="✅", message=f"Candidates: {', '.join(names)}")

    # ── Step 3: MongoDB MCP — fetch category context ─────────────────
    if mcp.available:
        top_category = candidates[0].get("category", "")
        yield _evt("step", icon="🗄️", message=f"MongoDB MCP → find('failure_patterns', {{category: '{top_category}'}}, limit=10)")
        try:
            category_patterns = await mcp.find(
                "failure_patterns",
                filter_={"category": top_category},
                projection={"_id": 0, "pattern_id": 1, "name": 1, "failure_count": 1, "survival_count": 1},
                limit=10,
            )
            yield _evt("step", icon="✅", message=f"MCP returned {len(category_patterns)} '{top_category}' patterns → survival rates: {', '.join(p['pattern_id'] for p in category_patterns[:3])}...")
        except Exception as e:
            yield _evt("step", icon="⚠️", message=f"MCP fetch skipped: {e}")

    # ── Step 4: Parallel Gemini scoring ──────────────────────────────
    gemini.last_fallback_reason = None  # reset before batch
    yield _evt("step", icon="🤖", message=f"Gemini 3 Flash scoring {len(candidates)} candidates in parallel...")

    async def score_with_log(pattern):
        return await _score_pattern(metrics, pattern)

    for i, p in enumerate(candidates):
        yield _evt("step", icon="⚡", message=f"Evaluating [{i+1}/{len(candidates)}] {p['name']}...")

    # Actually score all in parallel (the messages above are pre-emit for UX)
    scorings = await asyncio.gather(
        *[score_with_log(p) for p in candidates],
        return_exceptions=True,
    )

    # Emit fallback notice if Gemini 3 was rate-limited during scoring
    if gemini.last_fallback_reason:
        yield _evt("step", icon="🔄", message=f"Model fallback: {gemini.last_fallback_reason}")
        gemini.last_fallback_reason = None

    best_match = None
    best_score = 0.0
    best_scoring = None

    for pattern, scoring in zip(candidates, scorings):
        if isinstance(scoring, Exception):
            continue
        score = scoring.get("confidence", 0.0)
        yield _evt("step", icon="📊", message=f"  → {pattern['name']}: {int(score*100)}% match score")
        if score > best_score:
            best_score = score
            best_match = pattern
            best_scoring = scoring

    # ── Step 5: Agent re-evaluation if low confidence ────────────────
    if best_score < 0.70 and mcp.available:
        yield _evt("step", icon="🔄", message=f"Match score {int(best_score*100)}% — below threshold. Agent re-querying MongoDB MCP for broader pattern set...")

        try:
            yield _evt("step", icon="🗄️", message="MongoDB MCP → find('failure_patterns', {}, limit=10) [re-evaluation pass]")
            backup_patterns = await mcp.find(
                "failure_patterns",
                filter_={},
                projection={"_id": 0, "narrative_embedding": 0},
                limit=10,
            )
            # Remove already-scored patterns
            seen_ids = {p["pattern_id"] for p in candidates}
            backup_candidates = [p for p in backup_patterns if p.get("pattern_id") not in seen_ids][:3]

            if backup_candidates:
                yield _evt("step", icon="🤖", message=f"Re-scoring {len(backup_candidates)} backup patterns via Gemini 3 Flash...")
                backup_scorings = await asyncio.gather(
                    *[_score_pattern(metrics, p) for p in backup_candidates],
                    return_exceptions=True,
                )
                for pattern, scoring in zip(backup_candidates, backup_scorings):
                    if isinstance(scoring, Exception):
                        continue
                    score = scoring.get("confidence", 0.0)
                    yield _evt("step", icon="📊", message=f"  → {pattern['name']}: {int(score*100)}% match score")
                    if score > best_score:
                        best_score = score
                        best_match = pattern
                        best_scoring = scoring

        except Exception as e:
            yield _evt("step", icon="⚠️", message=f"Re-evaluation skipped: {e}")

    # ── Step 6: Result ────────────────────────────────────────────────
    if best_score < 0.60 or best_match is None:
        yield _evt("step", icon="✅", message=f"Best match score: {int(best_score*100)}% — below 60% threshold. No dangerous pattern confirmed.")
        yield _evt("safe", message="No dangerous failure patterns detected. Your metrics look healthy for this stage.")
        return

    yield _evt("step", icon="⚠️", message=f"Pattern confirmed: {best_match['name']} at {int(best_score*100)}% match score. Generating full alert...")

    # Build PatternMatch object
    signals = [
        WarningSig(
            signal=s["signal"],
            status=s.get("status", "DETECTED"),
            days_detectable=s.get("days_detectable"),
        )
        for s in best_scoring.get("detected_signals", [])
        if s.get("status") in ("DETECTED", "EMERGING")
    ]
    total = best_match["failure_count"] + best_match["survival_count"]
    survival_rate = best_match["survival_count"] / total if total > 0 else 0.0

    match = PatternMatch(
        pattern_id=best_match["pattern_id"],
        pattern_name=best_match["name"],
        confidence=round(best_score, 2),
        failure_count=best_match["failure_count"],
        survival_count=best_match["survival_count"],
        survival_rate=round(survival_rate, 3),
        narrative=best_match["narrative"],
        warning_signals_detected=signals,
        survival_playbook=best_match["survival_playbook"],
        famous_failures=best_match.get("famous_failures", []),
        days_to_crisis=best_scoring.get("days_to_crisis", 90),
        match_reasoning=best_scoring.get("match_reasoning"),
        trigger_conditions=best_match.get("trigger_conditions"),
    )

    try:
        output_file = write_alert(match, metrics)
        match.output_file = output_file
    except Exception:
        pass

    # ── Step 7: Challenger Agent ─────────────────────────────────────
    yield _evt("step", icon="⚖️", message="Challenger Agent independently evaluating Investigator's finding...")
    try:
        from backend.services.pattern_matcher import _challenger_evaluate
        challenger = await _challenger_evaluate(metrics, best_match, best_score)
        verdict_icon = "✅" if challenger["verdict"] == "CONFIRM" else "⚡"
        verdict_msg = (
            f"Challenger Agent {challenger['verdict']}S at {int(challenger['confidence']*100)}% "
            f"({'±' if challenger['verdict']=='CONFIRM' else 'Δ'}{challenger['delta_pp']}pp) — {challenger['reasoning']}"
        )
        yield _evt("step", icon=verdict_icon, message=verdict_msg)
        yield _evt("challenger",
                   verdict=challenger["verdict"],
                   confidence=challenger["confidence"],
                   reasoning=challenger["reasoning"],
                   strongest_counter=challenger["strongest_counter"],
                   delta_pp=challenger["delta_pp"],
                   investigator_confidence=best_score)
    except Exception as e:
        yield _evt("step", icon="⚠️", message=f"Challenger Agent skipped: {e}")

    yield _evt("result",
               alert=True,
               startup_name=metrics.startup_name,
               message=f"Pattern detected: {match.pattern_name} at {int(match.confidence*100)}% match score.",
               pattern=match.model_dump())


@router.post("/analyze/stream")
async def analyze_stream(metrics: MetricsInput):
    """
    Streaming version of the analysis endpoint.
    Returns Server-Sent Events as the agent executes each step.
    """
    return StreamingResponse(
        _run_agent_stream(metrics),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
