"""
Core pattern matching engine.
Finds failure patterns that match the startup's current metrics.
"""
import asyncio
import json
from backend.db.connection import get_db
from backend.db.schemas import MetricsInput, PatternMatch, WarningSig
from backend.services import gemini


def _burn_multiple(metrics: MetricsInput) -> float:
    """Net Burn Multiple = burn / net_new_arr"""
    net_new_mrr = metrics.mrr * metrics.mrr_growth_rate
    if net_new_mrr <= 0:
        return 99.0
    return metrics.burn_rate / net_new_mrr


def _ltv_cac_ratio(metrics: MetricsInput) -> float:
    if metrics.cac <= 0:
        return 0.0
    return metrics.ltv / metrics.cac


def compute_oracle_score(metrics: MetricsInput, match_confidence: float = 0.0) -> tuple[int, str]:
    """
    Composite startup health score 0-100. Higher = healthier.

    Formula (transparent, deterministic):
      Start at 100. Subtract penalties for unhealthy metrics + matched pattern confidence.
      Add bonuses for strong signals (high NPS, good unit economics).

    Returns (score, band) where band ∈ {"strong", "watch", "warning", "critical"}.
    """
    score = 100.0

    # Pattern match penalty — up to -60 if 100% match
    score -= match_confidence * 60

    # Churn penalty — every 1% over 5% loses 2 points
    churn_pct = metrics.churn_rate * 100
    if churn_pct > 5:
        score -= min((churn_pct - 5) * 2, 30)

    # LTV:CAC penalty — if below 3, lose up to 15
    ltv_cac = (metrics.ltv / metrics.cac) if metrics.cac > 0 else 0
    if ltv_cac < 3:
        score -= min((3 - ltv_cac) * 5, 15)

    # Runway penalty — under 12 months loses up to 15
    if metrics.runway_months < 12:
        score -= min((12 - metrics.runway_months) * 1.5, 15)

    # Burn multiple penalty — over 2x loses up to 10
    bm = _burn_multiple(metrics)
    if bm > 2:
        score -= min((bm - 2) * 2, 10)

    # NPS bonus — over 30 adds up to +10
    if metrics.nps > 30:
        score += min((metrics.nps - 30) / 7, 10)

    # Growth bonus — over 10%/mo adds up to +5
    if metrics.mrr_growth_rate > 0.10:
        score += min((metrics.mrr_growth_rate - 0.10) * 50, 5)

    score = max(0, min(100, round(score)))

    if score >= 75:    band = "strong"
    elif score >= 50:  band = "watch"
    elif score >= 25:  band = "warning"
    else:              band = "critical"

    return int(score), band


def build_recovery_scenario(metrics: MetricsInput, current_match_confidence: float) -> dict:
    """
    Project the Oracle Score under healthier counterfactual metrics.
    Returns the score delta + a list of suggested improvements.
    Does NOT call Gemini — pure math, runs instantly.
    """
    improvements = []
    recovered = metrics.model_copy()

    if metrics.churn_rate > 0.05:
        recovered.churn_rate = 0.05
        improvements.append(f"Reduce churn from {metrics.churn_rate*100:.1f}% to 5%")

    ltv_cac = (metrics.ltv / metrics.cac) if metrics.cac > 0 else 0
    if ltv_cac < 3 and metrics.cac > 0:
        recovered.cac = metrics.ltv / 3
        improvements.append(f"Improve LTV:CAC from {ltv_cac:.1f}x to 3x")

    if metrics.runway_months < 12:
        recovered.runway_months = 12
        improvements.append(f"Extend runway from {metrics.runway_months} to 12 months")

    if metrics.nps < 30:
        recovered.nps = 30
        improvements.append(f"Lift NPS from {metrics.nps} to 30")

    # Lower match confidence proportional to how much we improved (rough heuristic)
    recovered_confidence = current_match_confidence * 0.4 if improvements else current_match_confidence

    current_score, _ = compute_oracle_score(metrics, current_match_confidence)
    recovered_score, _ = compute_oracle_score(recovered, recovered_confidence)

    return {
        "improvements": improvements,
        "score_delta": max(0, recovered_score - current_score),
        "confidence": round(recovered_confidence, 2),
    }


def _reciprocal_rank_fusion(lists: list[list[dict]], k: int = 60) -> list[dict]:
    """
    Reciprocal Rank Fusion — merges multiple ranked lists into one.
    score = Σ 1 / (k + rank)  for each document across all lists.
    Standard k=60 from Cormack et al. 2009.
    """
    scores: dict[str, float] = {}
    docs: dict[str, dict] = {}
    for ranked_list in lists:
        for rank, doc in enumerate(ranked_list):
            pid = doc.get("pattern_id", str(rank))
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank + 1)
            docs[pid] = doc
    sorted_ids = sorted(scores, key=lambda pid: scores[pid], reverse=True)
    return [docs[pid] for pid in sorted_ids]


async def _atlas_search_candidates(metrics: MetricsInput, query_text: str) -> list[dict]:
    """
    MongoDB Atlas Search (BM25) — text search across pattern names,
    narratives, and category fields. Requires an Atlas Search index named 'default'.
    Returns empty list if the index doesn't exist (graceful degradation).
    """
    db = get_db()
    category_hints = []
    if metrics.churn_rate > 0.08:  category_hints.append("churn unit economics")
    if metrics.mrr_growth_rate < 0.08: category_hints.append("stagnation growth")
    if _burn_multiple(metrics) > 5:  category_hints.append("burn spending scaling")
    if metrics.runway_months < 9:    category_hints.append("runway fundraising")
    if metrics.nps < 20:            category_hints.append("product market fit")
    if _ltv_cac_ratio(metrics) < 1: category_hints.append("unit economics acquisition")
    search_phrase = " ".join(category_hints) if category_hints else query_text[:100]
    try:
        pipeline = [
            {
                "$search": {
                    "index": "default",
                    "text": {
                        "query": search_phrase,
                        "path": ["name", "narrative", "category"],
                        "fuzzy": {"maxEdits": 1},
                    },
                }
            },
            {
                "$match": {
                    "stage_month_min": {"$lte": metrics.current_month},
                    "stage_month_max": {"$gte": metrics.current_month},
                }
            },
            {"$limit": 10},
            {"$project": {"narrative_embedding": 0}},
        ]
        results = await db["failure_patterns"].aggregate(pipeline).to_list(length=10)
        return results
    except Exception:
        return []


async def _candidate_patterns(metrics: MetricsInput) -> list[dict]:
    """
    Hybrid retrieval: MongoDB Atlas Vector Search + Atlas Search (BM25)
    merged via Reciprocal Rank Fusion. Falls back to numeric filter if both fail.
    """
    import logging
    db = get_db()

    query_text = (
        f"startup failure: month {metrics.current_month}, "
        f"churn {metrics.churn_rate*100:.0f}%, NPS {metrics.nps}, "
        f"burn ${metrics.burn_rate:,.0f}/month, runway {metrics.runway_months} months, "
        f"LTV:CAC {_ltv_cac_ratio(metrics):.1f}x, burn multiple {_burn_multiple(metrics):.1f}x"
    )

    # Run Vector Search and Atlas Search in parallel
    vector_results = []
    bm25_results   = []

    try:
        query_vector = await gemini.embed(query_text)
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
            logging.getLogger(__name__).warning("Vector search failed: %s", vector_results)
            vector_results = []
        if isinstance(bm25_results, Exception):
            bm25_results = []
    except Exception as e:
        logging.getLogger(__name__).warning("Hybrid retrieval embed failed: %s", e)

    if vector_results or bm25_results:
        merged = _reciprocal_rank_fusion([vector_results, bm25_results]) if bm25_results else vector_results
        return merged[:5]

    # Stage 2: Numeric filter fallback — score by number of matching conditions
    burn_mult = _burn_multiple(metrics)
    ltv_cac = _ltv_cac_ratio(metrics)

    # Use aggregation to rank patterns by how many trigger conditions fire
    pipeline = [
        {
            "$match": {
                "stage_month_min": {"$lte": metrics.current_month},
                "stage_month_max": {"$gte": metrics.current_month},
                "$or": [
                    {"trigger_conditions.mrr_growth_rate_min": {"$lte": metrics.mrr_growth_rate}},
                    {"trigger_conditions.mrr_growth_rate_max": {"$gte": metrics.mrr_growth_rate}},
                    {"trigger_conditions.churn_rate_min": {"$lte": metrics.churn_rate}},
                    {"trigger_conditions.nps_max": {"$gte": metrics.nps}},
                    {"trigger_conditions.burn_multiple_min": {"$lte": burn_mult}},
                    {"trigger_conditions.ltv_cac_ratio_max": {"$gte": ltv_cac}},
                    {"trigger_conditions.runway_months_max": {"$gte": metrics.runway_months}},
                ],
            }
        },
        {
            "$addFields": {
                "_match_score": {
                    "$sum": [
                        {"$cond": [{"$and": [{"$gt": ["$trigger_conditions.churn_rate_min", None]}, {"$lte": ["$trigger_conditions.churn_rate_min", metrics.churn_rate]}]}, 2, 0]},
                        {"$cond": [{"$and": [{"$gt": ["$trigger_conditions.burn_multiple_min", None]}, {"$lte": ["$trigger_conditions.burn_multiple_min", burn_mult]}]}, 2, 0]},
                        {"$cond": [{"$and": [{"$gt": ["$trigger_conditions.nps_max", None]}, {"$gte": ["$trigger_conditions.nps_max", metrics.nps]}]}, 2, 0]},
                        {"$cond": [{"$and": [{"$gt": ["$trigger_conditions.ltv_cac_ratio_max", None]}, {"$gte": ["$trigger_conditions.ltv_cac_ratio_max", ltv_cac]}]}, 2, 0]},
                        {"$cond": [{"$and": [{"$gt": ["$trigger_conditions.runway_months_max", None]}, {"$gte": ["$trigger_conditions.runway_months_max", metrics.runway_months]}]}, 1, 0]},
                        {"$cond": [{"$and": [{"$gt": ["$trigger_conditions.mrr_growth_rate_min", None]}, {"$lte": ["$trigger_conditions.mrr_growth_rate_min", metrics.mrr_growth_rate]}]}, 1, 0]},
                    ]
                }
            }
        },
        {"$sort": {"_match_score": -1}},
        {"$limit": 5},
        {"$project": {"narrative_embedding": 0, "_match_score": 0}},
    ]
    results = await db["failure_patterns"].aggregate(pipeline).to_list(length=5)
    return results


async def _get_previous_analysis(startup_name: str) -> dict | None:
    """Fetch the most recent analysis from MongoDB for session memory context."""
    try:
        from backend.db.connection import get_db
        db = get_db()
        doc = await db["startup_analyses"].find_one(
            {"startup_name": startup_name},
            sort=[("checked_at", -1)],
            projection={"_id": 0, "pattern_name": 1, "confidence": 1,
                        "checked_at": 1, "metrics_snapshot": 1},
        )
        return doc
    except Exception:
        return None


async def _score_with_gemini(metrics: MetricsInput, pattern: dict) -> dict:
    """
    Ask Gemini to score the match confidence and extract detected signals.
    Returns JSON with: confidence, detected_signals, days_to_crisis, narrative_summary.
    """
    # Inject previous analysis for session memory context
    prev = await _get_previous_analysis(metrics.startup_name)
    prev_context = ""
    if prev:
        prev_snap = prev.get("metrics_snapshot", {})
        prev_churn = prev_snap.get("churn_rate", 0) * 100
        prev_score = int((prev.get("confidence") or 0) * 100)
        prev_pattern = prev.get("pattern_name") or "none"
        from datetime import datetime, timezone
        checked = prev.get("checked_at")
        days_ago = ""
        if checked:
            if isinstance(checked, str):
                checked = datetime.fromisoformat(checked.replace("Z", "+00:00"))
            delta = (datetime.now(timezone.utc) - checked).days
            days_ago = f" ({delta} days ago)"
        prev_context = (
            f"\nPREVIOUS ANALYSIS{days_ago}: pattern={prev_pattern}, "
            f"similarity={prev_score}%, churn={prev_churn:.1f}%. "
            f"Note trend changes vs current values in your match_reasoning."
        )

    prompt = f"""
You are a startup failure pattern analyst. Evaluate how closely this startup's
current metrics match the given failure pattern.

STARTUP METRICS:
- Name: {metrics.startup_name}
- Month: {metrics.current_month}
- MRR: ${metrics.mrr:,.0f} (growing {metrics.mrr_growth_rate*100:.1f}%/month)
- Churn rate: {metrics.churn_rate*100:.1f}%/month
- Burn rate: ${metrics.burn_rate:,.0f}/month
- Runway: {metrics.runway_months} months
- Headcount: {metrics.headcount}
- NPS: {metrics.nps}
- CAC: ${metrics.cac:,.0f} | LTV: ${metrics.ltv:,.0f}
- LTV:CAC ratio: {_ltv_cac_ratio(metrics):.1f}x
- Burn multiple: {_burn_multiple(metrics):.1f}x

FAILURE PATTERN: {pattern['name']}
Category: {pattern['category']}
Description: {pattern['narrative']}
Trigger conditions: {json.dumps(pattern['trigger_conditions'])}
Known warning signals: {json.dumps([s['signal'] for s in pattern['warning_signals']])}{prev_context}

TASK: Return JSON with exactly these fields:
{{
  "confidence": <float 0.0-1.0 — how closely do the metrics match this pattern?>,
  "detected_signals": [
    {{"signal": "<signal text>", "status": "DETECTED|EMERGING|NOT_YET", "days_detectable": <int or null>}}
  ],
  "days_to_crisis": <estimated days to crisis if no action — integer>,
  "match_reasoning": "<1-2 sentences explaining exactly which metrics are driving this match and why — be specific, cite numbers>"
}}

IMPORTANT RULES:
- Only return confidence >0.75 if the metrics clearly match multiple trigger conditions.
- For every signal in the "Known warning signals" list, evaluate whether the current metrics show evidence of it. A single snapshot IS enough to detect structural signals (e.g. high churn, low NPS, negative LTV:CAC). Do NOT require trend data — evaluate against the current values.
- If confidence >= 0.75, you MUST mark at least 2 signals as DETECTED or EMERGING. A high confidence match with zero detected signals is a contradiction.
- Use DETECTED when the current metric value clearly meets the signal condition. Use EMERGING when partially met. Use NOT_YET only when no metric evidence exists at all.
- For days_detectable: estimate how many days before today the signal would have first been visible based on the metric values (typically 30-180 days for structural signals).
"""
    raw = await gemini.generate_json_fast(prompt)
    return json.loads(raw)


async def _challenger_evaluate(metrics: MetricsInput, pattern: dict, investigator_confidence: float) -> dict:
    """
    Challenger Agent — a second Gemini 3 instance that independently re-evaluates
    the Investigator's top pattern with deliberate skepticism.

    Returns verdict CONFIRM when within 10pp of the Investigator, DISPUTE otherwise.
    """
    prompt = f"""You are the Challenger Agent — a skeptical second analyst tasked with stress-testing
the Investigator Agent's pattern match. Your job is NOT to agree by default.
Actively look for reasons this pattern does NOT apply. Weight counter-evidence heavily.

STARTUP METRICS:
- Name: {metrics.startup_name}
- Month: {metrics.current_month}
- MRR: ${metrics.mrr:,.0f} (growing {metrics.mrr_growth_rate*100:.1f}%/month)
- Churn rate: {metrics.churn_rate*100:.1f}%/month
- Burn rate: ${metrics.burn_rate:,.0f}/month
- Runway: {metrics.runway_months} months
- Headcount: {metrics.headcount}
- NPS: {metrics.nps}
- CAC: ${metrics.cac:,.0f} | LTV: ${metrics.ltv:,.0f}
- LTV:CAC ratio: {_ltv_cac_ratio(metrics):.1f}x
- Burn multiple: {_burn_multiple(metrics):.1f}x

INVESTIGATOR'S CLAIM: The pattern "{pattern['name']}" matches at {int(investigator_confidence*100)}%.
Category: {pattern['category']}
Trigger conditions: {json.dumps(pattern.get('trigger_conditions', {}))}

YOUR TASK: Challenge this finding. Consider:
1. Which metrics are HEALTHY and contradict the pattern?
2. Are there structural reasons the trigger conditions might NOT apply here?
3. Could the data be explained by a less severe pattern?

Return JSON with exactly:
{{
  "confidence": <float 0.0-1.0 — YOUR independent assessment of how much this pattern actually fits>,
  "reasoning": "<1-2 sentences: what do you agree OR disagree with, and why — cite specific metrics>",
  "strongest_counter": "<the single most compelling metric that works AGAINST this pattern>"
}}

Be genuinely independent. A good Challenger sometimes confirms (when evidence is overwhelming),
but more often finds nuance. Do NOT simply mirror the Investigator's score.
"""
    try:
        raw = await gemini.generate_json_fast(prompt)
        result = json.loads(raw)
        challenger_conf = float(result.get("confidence", investigator_confidence))
        delta = abs(challenger_conf - investigator_confidence)
        verdict = "CONFIRM" if delta <= 0.10 else "DISPUTE"
        return {
            "verdict": verdict,
            "confidence": round(challenger_conf, 2),
            "reasoning": result.get("reasoning", ""),
            "strongest_counter": result.get("strongest_counter", ""),
            "delta_pp": round(delta * 100, 1),
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Challenger agent failed: %s", e)
        return {"verdict": "CONFIRM", "confidence": investigator_confidence,
                "reasoning": "Challenger unavailable.", "strongest_counter": "", "delta_pp": 0.0}


async def match_patterns(metrics: MetricsInput) -> PatternMatch | None:
    """
    Main entry point. Returns the highest-confidence pattern match,
    or None if no dangerous match found.
    """
    candidates = await _candidate_patterns(metrics)
    if not candidates:
        return None

    # Score all candidates concurrently instead of sequentially
    scorings = await asyncio.gather(
        *[_score_with_gemini(metrics, p) for p in candidates],
        return_exceptions=True,
    )

    best_match = None
    best_score = 0.0
    best_scoring = None

    for pattern, scoring in zip(candidates, scorings):
        if isinstance(scoring, Exception):
            continue
        confidence = scoring.get("confidence", 0.0)
        if confidence > best_score:
            best_score = confidence
            best_match = pattern
            best_scoring = scoring

    # Only return a match if confidence is meaningful
    if best_score < 0.60 or best_match is None:
        return None

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

    # Persist to MongoDB for session memory
    try:
        from backend.db.connection import get_db
        from datetime import datetime, timezone
        db = get_db()
        await db["startup_analyses"].insert_one({
            "startup_name": metrics.startup_name,
            "checked_at": datetime.now(timezone.utc),
            "alert": True,
            "pattern_name": best_match["name"],
            "confidence": round(best_score, 2),
            "days_to_crisis": best_scoring.get("days_to_crisis", 90),
            "metrics_snapshot": metrics.model_dump(),
        })
    except Exception:
        pass

    return PatternMatch(
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
