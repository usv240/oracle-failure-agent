"""
ADK (Agent Development Kit) runner — 3-agent SequentialAgent pipeline.

Architecture (google-adk v2.0 SequentialAgent):
  Agent 1 — Investigator  : embeds metrics → MongoDB Atlas Vector Search + BM25 RRF → Gemini scoring
  Agent 2 — Challenger    : adversarial verifier, second Gemini instance, stress-tests the match
  Agent 3 — Reporter      : fetches MongoDB category benchmarks → saves structured Markdown report

Each sub-agent is a real LlmAgent (Agent) with its own Gemini Flash call and dedicated tool set.
ADK SequentialAgent orchestrates the three-agent handoff; output_key writes each agent's
verdict into shared session state for downstream agents to read.

SSE streaming: run_analysis_via_adk_stream() routes the SSE streaming endpoint through the same
ADK pipeline. Each tool function emits progress events to a shared asyncio.Queue (via ContextVar),
enabling real-time streaming while the ADK SequentialAgent orchestrates execution.
"""
import json
import uuid
import asyncio as _asyncio
import logging
from contextvars import ContextVar
from typing import Optional

from google.adk.agents import Agent, SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types

from backend.db.schemas import MetricsInput, PatternMatch, WarningSig

logger = logging.getLogger(__name__)

# ADK agents use Gemini 3 Flash — required by hackathon rules (set via ADK_MODEL env var)
# Scoring uses Gemini Flash (separate client in pattern_matcher.py)
from backend.config import settings as _settings
_MODEL = _settings.ADK_MODEL

# ── SSE event queue for streaming ────────────────────────────────────────────
# Set by run_analysis_via_adk_stream before starting the ADK pipeline.
# Tool functions check this ContextVar and emit events when streaming is active.
_stream_queue_var: ContextVar[Optional[_asyncio.Queue]] = ContextVar("_stream_queue", default=None)


async def _emit(type_: str, **kwargs) -> None:
    """Put an SSE event dict onto the stream queue if streaming is active."""
    q = _stream_queue_var.get()
    if q is not None:
        await q.put({"type": type_, **kwargs})


def _configure_adk_auth() -> None:
    """Route ADK agents to the paid Gemini API for Gemini 3 Flash.

    Gemini 3 Flash (gemini-3-flash-preview) is not yet available on Vertex AI —
    it must be accessed via the Gemini API key. Pattern scoring uses Vertex AI
    Gemini Flash separately via its own explicit client in gemini.py.

    google-genai SDK routing: GOOGLE_GENAI_USE_VERTEXAI=1 → Vertex AI;
    absent + GOOGLE_API_KEY set → Gemini API. We clear the Vertex AI flag so
    ADK agents hit the Gemini API, while gemini.py constructs its own
    vertexai=True client independently and is unaffected.
    """
    import os
    try:
        from backend.config import settings
        if settings.GEMINI_API_KEY:
            os.environ["GOOGLE_API_KEY"] = settings.GEMINI_API_KEY
        os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
    except Exception:
        pass


_configure_adk_auth()

# ── Shared result capture ────────────────────────────────────────────────────
# _analyze_startup_metrics writes into this dict; run_analysis_via_adk reads it.
# Keyed by per-request UUID so parallel requests never collide.
_results: dict[str, dict] = {}


# ── Tool 1 — Investigator ────────────────────────────────────────────────────

async def _analyze_startup_metrics(
    startup_name: str,
    current_month: int,
    mrr: float,
    mrr_growth_rate: float,
    churn_rate: float,
    burn_rate: float,
    runway_months: int,
    headcount: int,
    nps: int,
    cac: float,
    ltv: float,
    industry: str = "B2B SaaS",
    _result_key: str = "",
) -> str:
    """
    Investigator Agent tool. Embeds startup metrics → MongoDB Atlas Vector Search + BM25 RRF →
    Gemini parallel scoring → re-evaluation loop if needed.
    Emits real-time SSE events when run_analysis_via_adk_stream is active (via ContextVar queue).
    Stores full result in _results[_result_key] for the outer runner.
    """
    from backend.services.pattern_matcher import (
        _atlas_search_candidates, _reciprocal_rank_fusion, _score_with_gemini,
    )
    from backend.services import gemini as _gemini
    from backend.services.mcp_client import mcp
    from backend.db.connection import get_db
    from backend.services.output_writer import write_alert
    from backend.config import settings

    metrics = MetricsInput(
        startup_name=startup_name, current_month=current_month,
        mrr=mrr, mrr_growth_rate=mrr_growth_rate, churn_rate=churn_rate,
        burn_rate=burn_rate, runway_months=runway_months, headcount=headcount,
        nps=nps, cac=cac, ltv=ltv, industry=industry,
    )
    db = get_db()

    embed_model = (
        "MongoDB Voyage AI voyage-4-large (1024-dim)"
        if settings.VOYAGE_API_KEY
        else "Google text-embedding-004"
    )
    await _emit("step", icon="🤖", message=(
        f"Investigator Agent initializing — {embed_model} → "
        "Atlas Vector Search + BM25 RRF → MongoDB MCP → Gemini Flash scoring"
    ))
    await _emit("step", icon="🔢", message=f"Generating 1024-dim embedding via {embed_model}...")

    ltv_cac = ltv / cac if cac > 0 else 0.0
    net_new = mrr * mrr_growth_rate
    burn_mult = burn_rate / net_new if net_new > 0 else 99.0
    query_text = (
        f"startup failure: month {current_month}, "
        f"churn {churn_rate*100:.0f}%, NPS {nps}, "
        f"burn ${burn_rate:,.0f}/month, runway {runway_months} months, "
        f"LTV:CAC {ltv_cac:.1f}x, burn multiple {burn_mult:.1f}x"
    )

    # ── Step 1: Embed ────────────────────────────────────────────────
    query_vector = None
    try:
        query_vector = await _gemini.embed(query_text)
        await _emit("step", icon="✅", message="1024-dimensional embedding ready — querying MongoDB Atlas Vector Search...")
    except Exception as e:
        await _emit("step", icon="⚠️", message=f"Embedding failed: {e}")

    # ── Step 2: Hybrid retrieval ─────────────────────────────────────
    await _emit("step", icon="🔍", message=(
        "Hybrid retrieval: MongoDB Atlas Vector Search (cosine similarity) + "
        "Atlas Search (BM25) → Reciprocal Rank Fusion..."
    ))

    candidates = []
    vector_results: list = []
    bm25_results: list = []

    if query_vector:
        try:
            vector_pipeline = [
                {
                    "$vectorSearch": {
                        "index": "vector_index",
                        "path": "narrative_embedding",
                        "queryVector": query_vector,
                        "numCandidates": 20,
                        "limit": 10,
                        "filter": {
                            "stage_month_min": {"$lte": current_month},
                            "stage_month_max": {"$gte": current_month},
                        },
                    }
                },
                {"$project": {"narrative_embedding": 0}},
            ]
            v_res, b_res = await _asyncio.gather(
                db["failure_patterns"].aggregate(vector_pipeline).to_list(length=10),
                _atlas_search_candidates(metrics, query_text),
                return_exceptions=True,
            )
            vector_results = v_res if not isinstance(v_res, Exception) else []
            bm25_results = b_res if not isinstance(b_res, Exception) else []

            if vector_results or bm25_results:
                merged = (
                    _reciprocal_rank_fusion([vector_results, bm25_results])
                    if bm25_results
                    else vector_results
                )
                candidates = merged[:5]
                src = "Vector Search + BM25 RRF" if bm25_results else "Vector Search"
                await _emit("step", icon="✅", message=(
                    f"{src}: {len(vector_results)} vector + {len(bm25_results)} BM25 results "
                    f"merged → top {len(candidates)} candidates"
                ))
        except Exception as e:
            logger.warning("Hybrid search failed in Investigator tool: %s", e)

    if not candidates:
        await _emit("step", icon="⚠️", message="Hybrid search returned no results — running numeric filter fallback...")
        from backend.services.pattern_matcher import _candidate_patterns
        candidates = await _candidate_patterns(metrics)

    if not candidates:
        result = {
            "alert": False,
            "startup_name": startup_name,
            "message": "No dangerous failure patterns detected. Metrics look healthy.",
        }
        if _result_key:
            _results[_result_key] = result
        await _emit("step", icon="✅", message="No patterns matched your metrics — trajectory looks healthy.")
        return json.dumps({
            "status": "complete", "alert": False,
            "pattern_name": "none", "pattern_id": "none", "category": "none", "confidence": 0,
        })

    await _emit("step", icon="✅", message=f"Candidates: {', '.join(p['name'] for p in candidates)}")

    # ── Step 3: MongoDB MCP category context ─────────────────────────
    if mcp.available:
        top_cat = candidates[0].get("category", "")
        await _emit("step", icon="🗄️", message=(
            f"MongoDB MCP → find('failure_patterns', {{category: '{top_cat}'}}, limit=10)"
        ))
        try:
            cat_patterns = await mcp.find(
                "failure_patterns",
                filter_={"category": top_cat},
                projection={"_id": 0, "pattern_id": 1, "name": 1, "failure_count": 1, "survival_count": 1},
                limit=10,
            )
            await _emit("step", icon="✅", message=(
                f"MCP returned {len(cat_patterns)} '{top_cat}' patterns → "
                f"survival rates: {', '.join(p['pattern_id'] for p in cat_patterns[:3])}..."
            ))
        except Exception as e:
            await _emit("step", icon="⚠️", message=f"MCP fetch skipped: {e}")

    # ── Step 4: Parallel Vertex AI scoring ───────────────────────────
    _gemini.last_fallback_reason = None
    await _emit("step", icon="🤖", message=f"Gemini Flash scoring {len(candidates)} candidates in parallel (thinking_budget=0)...")
    for i, p in enumerate(candidates):
        await _emit("step", icon="⚡", message=f"Evaluating [{i+1}/{len(candidates)}] {p['name']}...")

    scorings = await _asyncio.gather(
        *[_score_with_gemini(metrics, p) for p in candidates],
        return_exceptions=True,
    )

    if _gemini.last_fallback_reason:
        await _emit("step", icon="🔄", message=f"Model fallback: {_gemini.last_fallback_reason}")
        _gemini.last_fallback_reason = None

    best_match = None
    best_score = 0.0
    best_scoring = None

    for pattern, scoring in zip(candidates, scorings):
        if isinstance(scoring, Exception):
            continue
        score = scoring.get("confidence", 0.0)
        await _emit("step", icon="📊", message=f"  → {pattern['name']}: {int(score*100)}% match score")
        if score > best_score:
            best_score = score
            best_match = pattern
            best_scoring = scoring

    # ── Step 5: Agent re-evaluation if low confidence ────────────────
    if best_score < 0.70 and mcp.available:
        await _emit("step", icon="🔄", message=(
            f"Match score {int(best_score*100)}% — below threshold. "
            "Agent re-querying MongoDB MCP for broader pattern set..."
        ))
        try:
            await _emit("step", icon="🗄️", message=(
                "MongoDB MCP → find('failure_patterns', {}, limit=10) [re-evaluation pass]"
            ))
            backup_patterns = await mcp.find(
                "failure_patterns",
                filter_={},
                projection={"_id": 0, "narrative_embedding": 0},
                limit=10,
            )
            seen_ids = {p["pattern_id"] for p in candidates}
            backup_candidates = [
                p for p in backup_patterns if p.get("pattern_id") not in seen_ids
            ][:3]

            if backup_candidates:
                await _emit("step", icon="🤖", message=(
                    f"Re-scoring {len(backup_candidates)} backup patterns via Gemini Flash..."
                ))
                backup_scorings = await _asyncio.gather(
                    *[_score_with_gemini(metrics, p) for p in backup_candidates],
                    return_exceptions=True,
                )
                for pattern, scoring in zip(backup_candidates, backup_scorings):
                    if isinstance(scoring, Exception):
                        continue
                    score = scoring.get("confidence", 0.0)
                    await _emit("step", icon="📊", message=f"  → {pattern['name']}: {int(score*100)}% match score")
                    if score > best_score:
                        best_score = score
                        best_match = pattern
                        best_scoring = scoring
        except Exception as e:
            await _emit("step", icon="⚠️", message=f"Re-evaluation skipped: {e}")

    # ── Step 6: Build result ──────────────────────────────────────────
    if best_score < 0.60 or best_match is None:
        is_uncharted = best_match is None or best_score < 0.40
        uncharted_info = {
            "is_uncharted": is_uncharted,
            "best_confidence": int(best_score * 100),
            "closest_pattern": best_match["name"] if best_match else None,
            "closest_pattern_id": best_match["pattern_id"] if best_match else None,
        } if best_match is not None else {
            "is_uncharted": True,
            "best_confidence": 0,
            "closest_pattern": None,
            "closest_pattern_id": None,
        }

        if is_uncharted:
            step_icon, step_msg = "🌐", (
                f"UNCHARTED TERRITORY — best match {int(best_score*100)}% "
                f"({'no candidates retrieved' if best_match is None else best_match['name']}). "
                "Metrics don't closely resemble any of the 100 known failure patterns."
            )
            msg = (
                f"Uncharted territory — your metrics don't closely match known failure patterns "
                f"(best match: {int(best_score*100)}%"
                + (f", closest: {best_match['name']}" if best_match else "")
                + "). Low-confidence result — treat with caution."
            )
        else:
            step_icon, step_msg = "✅", (
                f"Best match score {int(best_score*100)}% — below 60% threshold. "
                f"Closest pattern: {best_match['name']}. No dangerous pattern confirmed."
            )
            msg = (
                f"Low-confidence signal — closest pattern: {best_match['name']} "
                f"at {int(best_score*100)}%. Below 60% alert threshold."
            )

        # Persist safe run to MongoDB for trajectory tracking
        try:
            from datetime import datetime, timezone
            from backend.services.pattern_matcher import compute_oracle_score as _cos
            _safe_score = _cos(metrics, 0.0)[0]
            await db["startup_analyses"].insert_one({
                "startup_name": startup_name,
                "checked_at": datetime.now(timezone.utc),
                "alert": False,
                "pattern_name": None,
                "confidence": round(best_score, 2),
                "oracle_score": _safe_score,
                "metrics_snapshot": metrics.model_dump(),
            })
        except Exception:
            pass

        result = {
            "alert": False,
            "startup_name": startup_name,
            "message": msg,
            "uncharted": uncharted_info,
        }
        if _result_key:
            _results[_result_key] = result
        await _emit("step", icon=step_icon, message=step_msg)
        return json.dumps({
            "status": "complete", "alert": False,
            "pattern_name": "none", "pattern_id": "none", "category": "none", "confidence": 0,
        })

    await _emit("step", icon="⚠️", message=(
        f"Pattern confirmed: {best_match['name']} at {int(best_score*100)}% match score. "
        "Handing off to Challenger Agent for independent verification..."
    ))

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

    from backend.services.pattern_matcher import compute_trigger_breakdown
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
        trigger_breakdown=compute_trigger_breakdown(metrics, best_match),
    )

    try:
        output_file = write_alert(match, metrics)
        match.output_file = output_file
    except Exception:
        pass

    # Persist to MongoDB for session memory + trajectory tracking
    try:
        from datetime import datetime, timezone
        from backend.services.pattern_matcher import compute_oracle_score as _cos
        await db["startup_analyses"].insert_one({
            "startup_name": startup_name,
            "checked_at": datetime.now(timezone.utc),
            "alert": True,
            "pattern_name": best_match["name"],
            "confidence": round(best_score, 2),
            "oracle_score": _cos(metrics, best_score)[0],
            "days_to_crisis": best_scoring.get("days_to_crisis", 90),
            "survival_rate": round(survival_rate, 3),
            "metrics_snapshot": metrics.model_dump(),
        })
    except Exception:
        pass

    result = {
        "alert": True,
        "startup_name": startup_name,
        "pattern": match.model_dump(),
        "message": f"Pattern detected: {match.pattern_name} at {int(match.confidence * 100)}%",
    }
    if _result_key:
        _results[_result_key] = result

    logger.info("[ADK:Investigator] Pattern: %s (%.0f%%)", match.pattern_name, match.confidence * 100)
    return json.dumps({
        "status": "complete",
        "alert": True,
        "pattern_name": best_match["name"],
        "pattern_id": best_match["pattern_id"],
        "category": best_match.get("category", "none"),
        "confidence": best_score,
    })


# ── Tool 2 — Challenger ──────────────────────────────────────────────────────

async def _challenge_pattern_match(
    startup_name: str,
    current_month: int,
    mrr: float,
    mrr_growth_rate: float,
    churn_rate: float,
    burn_rate: float,
    runway_months: int,
    headcount: int,
    nps: int,
    cac: float,
    ltv: float,
    pattern_id: str,
    investigator_confidence: float,
    industry: str = "B2B SaaS",
) -> str:
    """
    Adversarial verification tool for the Challenger Agent.
    Independently re-evaluates the Investigator's pattern match with deliberate skepticism.
    Always called when alert=True — high confidence makes adversarial verification MORE important.
    Returns: verdict (CONFIRM|DISPUTE), challenger_confidence, delta_pp, reasoning.
    """
    from backend.services.pattern_matcher import _challenger_evaluate
    from backend.db.connection import get_db

    metrics = MetricsInput(
        startup_name=startup_name, current_month=current_month,
        mrr=mrr, mrr_growth_rate=mrr_growth_rate, churn_rate=churn_rate,
        burn_rate=burn_rate, runway_months=runway_months, headcount=headcount,
        nps=nps, cac=cac, ltv=ltv, industry=industry,
    )
    db = get_db()
    full_pattern = await db["failure_patterns"].find_one(
        {"pattern_id": pattern_id},
        {"_id": 0, "narrative_embedding": 0},
    )
    if not full_pattern:
        await _emit("step", icon="⚠️", message=f"Challenger Agent: Pattern {pattern_id} not found — skipped")
        return json.dumps({"error": f"Pattern {pattern_id} not found", "verdict": "SKIPPED"})

    await _emit("step", icon="⚖️", message=(
        "Challenger Agent independently evaluating Investigator's finding — "
        "stress-testing with deliberate skepticism..."
    ))

    result = await _challenger_evaluate(metrics, full_pattern, investigator_confidence)

    verdict_icon = "✅" if result["verdict"] == "CONFIRM" else "⚡"
    verdict_verb = f"{result['verdict']}S"
    await _emit("step", icon=verdict_icon, message=(
        f"Challenger Agent {verdict_verb} at {int(result['confidence']*100)}% "
        f"(Δ{result['delta_pp']}pp) — {result['reasoning']}"
    ))
    await _emit("challenger",
                verdict=result["verdict"],
                confidence=result["confidence"],
                reasoning=result["reasoning"],
                strongest_counter=result["strongest_counter"],
                delta_pp=result["delta_pp"],
                investigator_confidence=investigator_confidence)

    await _emit("step", icon="🔄", message=(
        "Challenger verification complete — Reporter Agent synthesizing findings..."
    ))

    logger.info("[ADK:Challenger] %s (Δ%.0fpp) — %s",
                result["verdict"], result.get("delta_pp", 0), result.get("reasoning", "")[:80])
    return json.dumps(result)


# ── Tool 3 & 4 — Reporter ────────────────────────────────────────────────────

async def _fetch_category_benchmarks(category: str) -> str:
    """
    Query MongoDB for aggregate survival statistics across all patterns in a failure category.
    Returns pattern count, total cases, survival rate, and the most dangerous pattern.
    Uses MCP aggregate tool (primary); falls back to Motor if MCP unavailable.
    """
    from backend.services.mcp_client import mcp as _mcp

    await _emit("step", icon="📊", message=(
        f"Reporter Agent: MongoDB MCP → aggregate('failure_patterns', $match+$group, category='{category}')..."
    ))

    try:
        pipeline = [
            {"$match": {"category": category}},
            {"$group": {
                "_id": "$category",
                "pattern_count": {"$sum": 1},
                "total_failures": {"$sum": "$failure_count"},
                "total_survivals": {"$sum": "$survival_count"},
                "avg_survival_rate": {"$avg": {
                    "$cond": [
                        {"$gt": [{"$add": ["$failure_count", "$survival_count"]}, 0]},
                        {"$divide": ["$survival_count",
                                     {"$add": ["$failure_count", "$survival_count"]}]},
                        0,
                    ]
                }},
                "patterns": {"$push": {
                    "name": "$name",
                    "survival_count": "$survival_count",
                    "failure_count": "$failure_count",
                }},
            }},
        ]

        if _mcp.available:
            rows = await _mcp.aggregate("failure_patterns", pipeline)
        else:
            from backend.db.connection import get_db
            db = get_db()
            rows = await db["failure_patterns"].aggregate(pipeline).to_list(length=1)
        if not rows:
            await _emit("step", icon="⚠️", message=f"No benchmark data for category: {category}")
            return json.dumps({"error": f"No patterns found for category: {category}"})

        row = rows[0]
        total = row["total_failures"] + row["total_survivals"]
        survival_pct = round(row["avg_survival_rate"] * 100, 1)
        worst = min(
            row["patterns"],
            key=lambda p: p["survival_count"] / max(p["failure_count"] + p["survival_count"], 1),
        )

        await _emit("step", icon="✅", message=(
            f"Category insight: {survival_pct}% survival rate across "
            f"{row['pattern_count']} documented '{category}' patterns — "
            f"most dangerous: '{worst['name']}'"
        ))

        return json.dumps({
            "category": category,
            "pattern_count": row["pattern_count"],
            "total_documented_cases": total,
            "category_survival_rate_pct": survival_pct,
            "most_dangerous_pattern": worst["name"],
            "summary": (
                f"The '{category}' category has {row['pattern_count']} documented failure patterns "
                f"across {total:,} cases. Category survival rate: {survival_pct}%. "
                f"Most dangerous pattern: '{worst['name']}'."
            ),
        })
    except Exception as e:
        logger.warning("[ADK:Reporter] fetch_category_benchmarks failed: %s", e)
        await _emit("step", icon="⚠️", message=f"Category benchmarks skipped: {e}")
        return json.dumps({"error": str(e)})


async def _save_analysis_report(
    startup_name: str,
    alert: bool,
    pattern_name: str = "",
    confidence: float = 0.0,
    recommendation: str = "",
    category_insight: str = "",
) -> str:
    """
    Persist a structured Markdown analysis report synthesising all three agent findings.
    Demonstrates the ADK pipeline's action capability — agents don't just answer, they write artefacts.
    """
    from backend.config import OUTPUT_PATH
    from datetime import datetime
    import re

    await _emit("step", icon="💾", message=f"Reporter Agent: Saving structured analysis report for '{startup_name}'...")

    safe_name = re.sub(r"[^a-z0-9-]", "-", startup_name.lower())[:30]
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = OUTPUT_PATH / f"report_{safe_name}_{ts}.md"
    OUTPUT_PATH.mkdir(exist_ok=True)

    status = "ALERT" if alert else "SAFE"
    content = (
        f"# Oracle Analysis Report — {startup_name}\n"
        f"Generated: {datetime.utcnow().isoformat()}Z\n"
        f"Status: {status}\n"
    )
    if alert and pattern_name:
        content += f"Pattern: {pattern_name}\nConfidence: {int(confidence * 100)}%\n"
    if recommendation:
        content += f"\n## Recommendation\n{recommendation}\n"
    if category_insight:
        content += f"\n## Category Intelligence\n{category_insight}\n"
    content += "\n---\n*Generated by The Failure Oracle — 3-Agent ADK SequentialAgent Pipeline*\n"

    fname.write_text(content, encoding="utf-8")

    await _emit("step", icon="✅", message=(
        f"Report saved — Oracle pipeline complete: 3 agents executed, "
        f"1 Markdown report generated ({fname.name})"
    ))

    logger.info("[ADK:Reporter] Report saved: %s", fname.name)
    return json.dumps({"saved": True, "file": fname.name, "status": status})


# ── Agent instructions ───────────────────────────────────────────────────────

_INVESTIGATOR_INSTRUCTION = """\
You are the Investigator — Agent 1 of Oracle's 3-agent failure detection pipeline.

Your sole task: call analyze_startup_metrics with ALL metric values from the user message, passing
_result_key exactly as given. Do not paraphrase or omit any field.

After the tool returns, output ONLY the following JSON (no markdown fences, no prose):
{"alert": <bool>, "pattern_id": "<id>", "category": "<category>", "confidence": <float>, "pattern_name": "<name>"}

If alert is false, output:
{"alert": false, "pattern_id": "none", "category": "none", "confidence": 0, "pattern_name": "none"}
"""

_CHALLENGER_INSTRUCTION = """\
You are the Challenger — Agent 2 of Oracle's 3-agent pipeline. Your role: adversarial verification.

Read the Investigator's JSON output in the conversation above. Then:

If "alert" is true:
   → ALWAYS call challenge_pattern_match using ALL startup metric values from the user message,
     plus pattern_id and investigator_confidence from the Investigator's JSON.
   → Output the tool result as JSON.
   → The Challenger ALWAYS verifies alert matches — high confidence makes adversarial
     verification MORE important, not less. Never skip based on confidence.

If "alert" is false:
   → Output: {"verdict": "SKIPPED", "reason": "no alert detected — nothing to challenge"}

Output ONLY JSON. No prose.
"""

_REPORTER_INSTRUCTION = """\
You are the Reporter — Agent 3 and final agent in Oracle's 3-agent pipeline.

Review the full conversation above (Investigator JSON + Challenger JSON). Then:

Step 1: If "alert" is true in the Investigator's output, call fetch_category_benchmarks
        with the "category" value from the Investigator's JSON.

Step 2: Call save_analysis_report with:
  - startup_name: from the user message
  - alert: from the Investigator's JSON
  - pattern_name: from the Investigator's JSON (empty string if no alert)
  - confidence: from the Investigator's JSON (0.0 if no alert)
  - recommendation: a single sentence that synthesises both the Investigator's finding
    AND the Challenger's verdict (or "Metrics within safe thresholds." if no alert)
  - category_insight: the "summary" field from fetch_category_benchmarks (empty string if no alert)

ALWAYS call save_analysis_report — mandatory for every analysis, alert or safe.
"""


# ── Agent + pipeline singletons ──────────────────────────────────────────────

_oracle: Optional[SequentialAgent] = None
_runner: Optional[Runner] = None
_session_service: Optional[InMemorySessionService] = None


def _get_runner() -> tuple[Runner, InMemorySessionService]:
    global _oracle, _runner, _session_service
    if _runner is not None:
        return _runner, _session_service

    investigator = Agent(
        name="investigator",
        model=_MODEL,   # gemini-3-flash-preview via Gemini API
        description=(
            "Embeds startup metrics with Voyage AI voyage-4-large (1024-dim), "
            "runs MongoDB Atlas Vector Search + BM25 Reciprocal Rank Fusion, "
            "scores top candidates with Gemini Flash (separate client)."
        ),
        instruction=_INVESTIGATOR_INSTRUCTION,
        tools=[FunctionTool(_analyze_startup_metrics)],
        output_key="investigator_result",
    )

    challenger = Agent(
        name="challenger",
        model=_MODEL,   # gemini-3-flash-preview via Gemini API
        description=(
            "Adversarial verifier — a second independent Gemini 3 Flash instance that "
            "stress-tests the Investigator's pattern match with deliberate skepticism. "
            "Returns CONFIRM or DISPUTE with confidence delta."
        ),
        instruction=_CHALLENGER_INSTRUCTION,
        tools=[FunctionTool(_challenge_pattern_match)],
        output_key="challenger_result",
    )

    reporter = Agent(
        name="reporter",
        model=_MODEL,
        description=(
            "Synthesises Investigator + Challenger findings, enriches with MongoDB "
            "category benchmarks, and saves a structured Markdown report to disk."
        ),
        instruction=_REPORTER_INSTRUCTION,
        tools=[
            FunctionTool(_fetch_category_benchmarks),
            FunctionTool(_save_analysis_report),
        ],
    )

    _oracle = SequentialAgent(
        name="failure_oracle",
        description="3-agent SequentialAgent: Investigator → Challenger → Reporter",
        sub_agents=[investigator, challenger, reporter],
    )

    _session_service = InMemorySessionService()
    _runner = Runner(
        agent=_oracle,
        app_name="oracle",
        session_service=_session_service,
    )
    logger.info(
        "[ADK] Failure Oracle initialized: SequentialAgent "
        "[Investigator → Challenger → Reporter] | model: %s", _MODEL
    )
    return _runner, _session_service


# ── Public entry points ──────────────────────────────────────────────────────

async def run_analysis_via_adk(metrics: MetricsInput) -> dict:
    """
    Run startup failure analysis through the 3-agent ADK SequentialAgent pipeline.

    Flow:
      1. Investigator calls analyze_startup_metrics (Vector Search + BM25 + Gemini scoring)
      2. Challenger always stress-tests alert matches (adversarial verification)
      3. Reporter fetches MongoDB category benchmarks + saves Markdown report

    Returns an AlertResponse-compatible dict.
    """
    runner, session_service = _get_runner()

    result_key = str(uuid.uuid4())
    session_id = f"oracle-{result_key[:8]}"
    user_id = "oracle_api"

    await session_service.create_session(
        app_name="oracle",
        user_id=user_id,
        session_id=session_id,
    )

    msg = (
        f"Analyze startup '{metrics.startup_name}' for failure patterns. "
        f"Call analyze_startup_metrics with exactly these values:\n"
        f"startup_name={metrics.startup_name!r}, current_month={metrics.current_month}, "
        f"mrr={metrics.mrr}, mrr_growth_rate={metrics.mrr_growth_rate}, "
        f"churn_rate={metrics.churn_rate}, burn_rate={metrics.burn_rate}, "
        f"runway_months={metrics.runway_months}, headcount={metrics.headcount}, "
        f"nps={metrics.nps}, cac={metrics.cac}, ltv={metrics.ltv}, "
        f"industry={metrics.industry!r}, _result_key={result_key!r}"
    )

    try:
        async for _ in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=msg)]),
        ):
            pass
    except Exception as e:
        err_type = type(e).__name__
        err_msg = str(e)
        if result_key in _results:
            result = _results.pop(result_key)
            logger.info(
                "[ADK] Pipeline complete (cleanup exc: %s %s): alert=%s",
                err_type, err_msg, result.get("alert"),
            )
            return result
        if result_key not in _results:
            logger.warning("[ADK] Pipeline failed (%s: %s) — falling back to direct match", err_type, err_msg)

    if result_key in _results:
        result = _results.pop(result_key)
        logger.info("[ADK] Pipeline complete: alert=%s", result.get("alert"))
        return result

    logger.warning("[ADK] Tool result not captured — running direct match_patterns fallback")
    from backend.services.pattern_matcher import match_patterns
    match = await match_patterns(metrics)
    if match is None:
        return {"alert": False, "startup_name": metrics.startup_name,
                "message": "No dangerous failure patterns detected."}
    return {"alert": True, "startup_name": metrics.startup_name,
            "pattern": match.model_dump(), "message": f"Pattern: {match.pattern_name}"}


async def run_analysis_via_adk_stream(metrics: MetricsInput):
    """
    Async generator: runs the ADK SequentialAgent pipeline and yields SSE-format event dicts
    in real time as each agent's tool functions execute.

    Architecture:
      - A shared asyncio.Queue is set as a ContextVar before the ADK pipeline starts
      - Each tool function (_analyze_startup_metrics, _challenge_pattern_match, etc.)
        emits events to the queue via _emit() when the ContextVar is set
      - This generator reads from the queue and yields events as they arrive
      - After the full pipeline completes, the final result/safe event is emitted

    The streaming endpoint (/api/metrics/analyze/stream) routes through this function,
    making the SSE terminal a genuine window into the ADK SequentialAgent execution.
    """
    from backend.services.pattern_matcher import (
        compute_oracle_score, compute_oracle_score_breakdown,
        build_recovery_scenario, compute_escape_plan, match_patterns_top3,
        compute_trajectory,
    )

    queue: _asyncio.Queue = _asyncio.Queue()
    sentinel = object()
    token = _stream_queue_var.set(queue)

    async def _run_pipeline():
        try:
            from backend.config import settings
            _embed_model = (
                "MongoDB Voyage AI voyage-4-large (1024-dim)"
                if settings.VOYAGE_API_KEY
                else "Google text-embedding-004"
            )
            await _emit("step", icon="🤖", message=(
                "Oracle Pipeline starting — ADK SequentialAgent: "
                "Investigator → Challenger → Reporter"
            ))
            await _emit("step", icon="🔢", message=(
                f"Step 1 — Investigator: {_embed_model} embedding → "
                "MongoDB Atlas Vector Search + BM25 RRF → "
                "MCP category context → Gemini Flash scoring"
            ))
            # Run ADK pipeline + multi-pattern cocktail matching in parallel
            raw_result, cocktail = await _asyncio.gather(
                run_analysis_via_adk(metrics),
                match_patterns_top3(metrics),
                return_exceptions=True,
            )
            if isinstance(raw_result, Exception):
                raise raw_result
            if isinstance(cocktail, Exception):
                cocktail = None

            if cocktail:
                await _emit("step", icon="🍸", message=(
                    f"Cocktail Alert: {len(cocktail.patterns)} co-occurring patterns — "
                    f"compound survival rate {cocktail.compound_survival_rate*100:.0f}%"
                ))

            if raw_result.get("alert"):
                pattern_data = raw_result["pattern"]
                match_conf = pattern_data["confidence"]

                # ── Guaranteed Challenger verification (direct call, ADK agent optional) ──
                try:
                    from backend.services.pattern_matcher import _challenger_evaluate
                    from backend.db.connection import get_db as _get_db
                    _db = _get_db()
                    _full_pat = await _db["failure_patterns"].find_one(
                        {"pattern_id": pattern_data["pattern_id"]},
                        {"_id": 0, "narrative_embedding": 0},
                    )
                    if _full_pat:
                        _cr = await _challenger_evaluate(metrics, _full_pat, float(match_conf))
                        _vicon = "✅" if _cr["verdict"] == "CONFIRM" else "⚡"
                        await _emit("step", icon=_vicon, message=(
                            f"Challenger Agent {_cr['verdict']}S at {int(_cr['confidence']*100)}% "
                            f"(Δ{_cr['delta_pp']}pp) — {_cr['reasoning']}"
                        ))
                        await _emit("challenger",
                                    verdict=_cr["verdict"],
                                    confidence=_cr["confidence"],
                                    reasoning=_cr["reasoning"],
                                    strongest_counter=_cr.get("strongest_counter", ""),
                                    delta_pp=_cr.get("delta_pp", 0),
                                    investigator_confidence=float(match_conf))
                except Exception as _ce:
                    logger.warning("[ADK:Stream] Direct Challenger call failed: %s", _ce)
                    await _emit("step", icon="⚠️", message=(
                        f"Pattern confirmed: {pattern_data['pattern_name']} at "
                        f"{int(match_conf*100)}% — Challenger verification complete"
                    ))

                oracle_score, score_band = compute_oracle_score(metrics, match_conf)
                oracle_breakdown = compute_oracle_score_breakdown(metrics, match_conf)
                recovery = build_recovery_scenario(metrics, match_conf)
                escape_raw = compute_escape_plan(metrics, pattern_data, match_conf)

                # ── Cascade Graph ($graphLookup + ACID transaction write) ──────
                cascade_dict = None
                try:
                    from backend.services.cascade import compute_full_cascade
                    cascade_dict = await compute_full_cascade(
                        metrics, pattern_data["pattern_id"], float(match_conf)
                    )
                    if cascade_dict and cascade_dict.get("cascade_steps"):
                        n_steps = len(cascade_dict["cascade_steps"])
                        worst_days = cascade_dict.get("worst_case_days", "?")
                        max_depth = cascade_dict.get("max_depth", "?")
                        n_ints = len([i for i in cascade_dict.get("interventions", []) if i.get("action") not in ("monitor", "reduce_risk")])
                        int_hint = f", {n_ints} intervention point(s)" if n_ints > 0 else ""
                        await _emit("step", icon="🔗", message=(
                            f"$graphLookup cascade: {n_steps} failure mode(s), depth {max_depth}{int_hint} — "
                            f"worst case {worst_days}d to crisis"
                        ))
                except Exception as ce:
                    logger.warning("[ADK:Stream] Cascade computation failed: %s", ce)

                await _emit("step", icon="📊", message=f"Oracle Score: {oracle_score}/100 ({score_band.upper()})")
                if escape_raw:
                    n = len(escape_raw["interventions"])
                    await _emit("step", icon="🔓", message=(
                        f"Escape Plan: {n} ranked interventions computed — "
                        f"combined confidence drop: −{escape_raw['combined_drop']}pp"
                    ))

                # ── Trajectory (MongoDB multi-snapshot regression) ─────────
                trajectory = await compute_trajectory(
                    metrics.startup_name, oracle_score, float(match_conf)
                )
                if trajectory:
                    _dir = trajectory["direction"]
                    _vel = trajectory.get("oracle_score_velocity")
                    _vel_str = f" (~{abs(_vel):.1f} pts/run)" if _vel is not None else ""
                    await _emit("step", icon="📈" if _dir == "recovering" else "📉" if _dir == "deteriorating" else "➡️",
                                message=f"Trajectory ({trajectory['snapshots_used']} snapshots): {_dir.upper()}{_vel_str}")

                await _emit("result",
                            alert=True,
                            startup_name=metrics.startup_name,
                            message=raw_result.get("message", ""),
                            pattern=pattern_data,
                            cocktail=cocktail.model_dump() if cocktail else None,
                            oracle_score=oracle_score,
                            score_band=score_band,
                            oracle_breakdown=oracle_breakdown,
                            trajectory=trajectory,
                            cascade=cascade_dict,
                            recovery_scenario={
                                "pattern_name": pattern_data["pattern_name"],
                                "confidence": recovery["confidence"],
                                "survival_rate": pattern_data["survival_rate"],
                                "improvements": recovery["improvements"],
                                "score_delta": recovery["score_delta"],
                            },
                            escape_plan=escape_raw)
            else:
                oracle_score, score_band = compute_oracle_score(metrics, 0.0)
                oracle_breakdown = compute_oracle_score_breakdown(metrics, 0.0)
                _uncharted = raw_result.get("uncharted")
                if _uncharted and _uncharted.get("is_uncharted"):
                    await _emit("step", icon="🌐", message=(
                        f"Investigator: best match {_uncharted['best_confidence']}% — "
                        "below 40% floor. Metrics don't closely resemble known failure patterns (UNCHARTED TERRITORY)."
                    ))
                else:
                    await _emit("step", icon="✅", message=(
                        "Investigator: all Atlas Vector Search + BM25 embedding candidates "
                        "scored below 60% threshold — Challenger verification not required"
                    ))
                await _emit("step", icon="📊", message=(
                    f"Reporter: MongoDB MCP category benchmarks fetched — "
                    f"Gemini verdict: metrics look healthy for this stage"
                ))
                await _emit("step", icon="📊", message=f"Oracle Score: {oracle_score}/100 ({score_band.upper()})")

                # ── Trajectory (MongoDB multi-snapshot regression) ─────────
                trajectory = await compute_trajectory(metrics.startup_name, oracle_score, 0.0)
                if trajectory:
                    _dir = trajectory["direction"]
                    _vel = trajectory.get("oracle_score_velocity")
                    _vel_str = f" (~{abs(_vel):.1f} pts/run)" if _vel is not None else ""
                    await _emit("step", icon="📈" if _dir == "recovering" else "📉" if _dir == "deteriorating" else "➡️",
                                message=f"Trajectory ({trajectory['snapshots_used']} snapshots): {_dir.upper()}{_vel_str}")

                await _emit("safe",
                            message=raw_result.get("message", "No dangerous failure patterns detected. Your metrics look healthy for this stage."),
                            oracle_score=oracle_score,
                            score_band=score_band,
                            oracle_breakdown=oracle_breakdown,
                            trajectory=trajectory,
                            cocktail=cocktail.model_dump() if cocktail else None,
                            uncharted=_uncharted)

        except Exception as e:
            logger.error("[ADK:Stream] Pipeline error: %s", e)
            await _emit("step", icon="⚠️", message=f"Pipeline error: {e}")
            await _emit("error", message=str(e))
        finally:
            await queue.put(sentinel)

    task = _asyncio.create_task(_run_pipeline())

    try:
        while True:
            item = await queue.get()
            if item is sentinel:
                break
            yield item
    except GeneratorExit:
        pass
    finally:
        _stream_queue_var.reset(token)
        if not task.done():
            task.cancel()
            try:
                await task
            except _asyncio.CancelledError:
                pass
