"""
Core pattern matching engine.
Finds failure patterns that match the startup's current metrics.
"""
import asyncio
import json
from backend.db.connection import get_db
from backend.db.schemas import MetricsInput, PatternMatch, WarningSig, CocktailPattern, CocktailMatch
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


def compute_trigger_breakdown(metrics: MetricsInput, pattern: dict) -> list[dict]:
    """
    For each trigger condition in the pattern, compute whether the startup's
    current metrics meet it and by how much. Returns a list of rows for the UI.
    """
    tc = pattern.get("trigger_conditions") or {}
    ltv_cac = _ltv_cac_ratio(metrics)
    burn_mult = _burn_multiple(metrics)
    rows = []

    mapping = [
        ("churn_rate_min",        "Churn Rate",      f"{metrics.churn_rate*100:.1f}%",    metrics.churn_rate,       lambda t: (f"≥ {t*100:.0f}%", metrics.churn_rate >= t)),
        ("burn_multiple_min",     "Burn Multiple",   f"{burn_mult:.1f}x",                  burn_mult,                lambda t: (f"≥ {t:.1f}x", burn_mult >= t)),
        ("nps_max",               "NPS",             str(metrics.nps),                     metrics.nps,              lambda t: (f"≤ {t}", metrics.nps <= t)),
        ("ltv_cac_ratio_max",     "LTV:CAC",         f"{ltv_cac:.1f}x",                   ltv_cac,                  lambda t: (f"≤ {t:.1f}x", ltv_cac <= t)),
        ("runway_months_max",     "Runway",          f"{metrics.runway_months}mo",         metrics.runway_months,    lambda t: (f"≤ {t}mo", metrics.runway_months <= t)),
        ("mrr_growth_rate_min",   "MRR Growth",      f"{metrics.mrr_growth_rate*100:.0f}%",metrics.mrr_growth_rate,  lambda t: (f"≥ {t*100:.0f}%", metrics.mrr_growth_rate >= t)),
    ]

    for key, label, current_val, _, threshold_fn in mapping:
        if tc.get(key) is not None:
            threshold_str, met = threshold_fn(tc[key])
            rows.append({
                "metric": label,
                "threshold": threshold_str,
                "current": current_val,
                "met": met,
            })

    return rows


def compute_oracle_score_breakdown(metrics: MetricsInput, match_confidence: float = 0.0) -> dict:
    """
    Same logic as compute_oracle_score but returns a breakdown dict showing
    each penalty/bonus with the actual numbers plugged in.
    Used by the frontend audit view so judges can see the exact formula.
    """
    churn_pct = metrics.churn_rate * 100
    ltv_cac   = (metrics.ltv / metrics.cac) if metrics.cac > 0 else 0
    bm        = _burn_multiple(metrics)

    pattern_penalty = round(match_confidence * 60, 1)
    churn_penalty   = round(min((churn_pct - 5) * 2, 30), 1) if churn_pct > 5 else 0
    ltv_penalty     = round(min((3 - ltv_cac) * 5, 15), 1)   if ltv_cac < 3  else 0
    runway_penalty  = round(min((12 - metrics.runway_months) * 1.5, 15), 1) if metrics.runway_months < 12 else 0
    bm_penalty      = round(min((bm - 2) * 2, 10), 1) if bm > 2 else 0
    nps_bonus       = round(min((metrics.nps - 30) / 7, 10), 1) if metrics.nps > 30 else 0
    growth_bonus    = round(min((metrics.mrr_growth_rate - 0.10) * 50, 5), 1) if metrics.mrr_growth_rate > 0.10 else 0

    rows = [
        {"label": "Base score",      "value": 100,             "detail": "Starting point"},
        {"label": "Pattern match",   "value": -pattern_penalty,
         "detail": f"{int(match_confidence*100)}% match × 60pp max = −{pattern_penalty}pp"},
        {"label": "Churn",           "value": -churn_penalty,
         "detail": f"{churn_pct:.1f}% churn — " + (f"({churn_pct:.1f}−5)×2 = −{churn_penalty}pp" if churn_pct > 5 else "within 5% safe zone")},
        {"label": "LTV:CAC",         "value": -ltv_penalty,
         "detail": f"{ltv_cac:.1f}x ratio — " + (f"(3−{ltv_cac:.1f})×5 = −{ltv_penalty}pp" if ltv_cac < 3 else "above 3x target")},
        {"label": "Runway",          "value": -runway_penalty,
         "detail": f"{metrics.runway_months}mo — " + (f"(12−{metrics.runway_months})×1.5 = −{runway_penalty}pp" if metrics.runway_months < 12 else "above 12mo floor")},
        {"label": "Burn multiple",   "value": -bm_penalty,
         "detail": f"{bm:.1f}x — " + (f"({bm:.1f}−2)×2 = −{bm_penalty}pp" if bm > 2 else "below 2x safe range")},
        {"label": "NPS bonus",       "value": +nps_bonus,
         "detail": f"NPS {metrics.nps} — " + (f"({metrics.nps}−30)/7 = +{nps_bonus}pp" if metrics.nps > 30 else "below 30 bonus threshold")},
        {"label": "Growth bonus",    "value": +growth_bonus,
         "detail": f"{metrics.mrr_growth_rate*100:.0f}% MoM — " + (f"({metrics.mrr_growth_rate*100:.0f}−10)×0.5 = +{growth_bonus}pp" if metrics.mrr_growth_rate > 0.10 else "below 10%/mo threshold")},
    ]

    final_score, band = compute_oracle_score(metrics, match_confidence)
    return {"rows": rows, "final": final_score, "band": band}


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
        # $compound query: narrative/name path boosted by weight, category path boosted higher
        should_clauses: list[dict] = [
            {
                "text": {
                    "query": search_phrase,
                    "path": ["narrative", "name"],
                    "fuzzy": {"maxEdits": 1},
                    "score": {"boost": {"value": 1.5}},
                }
            },
            {
                "text": {
                    "query": search_phrase,
                    "path": "category",
                    "score": {"boost": {"value": 3.0}},
                }
            },
        ]
        pipeline = [
            {
                "$search": {
                    "index": "default",
                    "compound": {
                        "should": should_clauses,
                        "minimumShouldMatch": 1,
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
        # Telemetry: count one vector search per query (fire-and-forget)
        try:
            from backend.services import telemetry
            telemetry.inc("vector_search")
        except Exception:
            pass
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
            # Motor returns timezone-naive datetimes from MongoDB; make UTC-aware before subtracting
            if checked.tzinfo is None:
                checked = checked.replace(tzinfo=timezone.utc)
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


def compute_escape_plan(metrics: MetricsInput, pattern: dict, confidence: float) -> dict | None:
    """
    Compute the minimum metric changes to drop match confidence below 60% (the alert threshold).
    Returns ranked interventions ordered by impact (largest confidence-point drop first).
    Pure math — no Gemini call, runs instantly.
    """
    tc = pattern.get("trigger_conditions") or {}
    if not tc:
        return None

    ltv_cac = _ltv_cac_ratio(metrics)
    burn_mult = _burn_multiple(metrics)
    conf_pct = round(confidence * 100)
    interventions: list[dict] = []

    def _diff(pct_change: float) -> str:
        return "easy" if pct_change < 20 else ("medium" if pct_change < 45 else "hard")

    def _drop(weight: float = 1.0) -> int:
        return min(max(round(conf_pct * 0.18 * weight), 5), 30)

    # ── Churn ──────────────────────────────────────────────────────
    if tc.get("churn_rate_min") is not None and metrics.churn_rate >= tc["churn_rate_min"]:
        target = min(tc["churn_rate_min"] * 0.78, 0.05)
        pct_chg = (metrics.churn_rate - target) / metrics.churn_rate * 100
        interventions.append({
            "metric": "Monthly Churn",
            "current_value": f"{metrics.churn_rate*100:.1f}%",
            "target_value": f"{target*100:.1f}%",
            "change_needed": f"−{pct_chg:.0f}% reduction",
            "difficulty": _diff(pct_chg),
            "estimated_confidence_drop": _drop(1.2 if pct_chg < 30 else 0.9),
            "action": (
                f"Deploy customer-success health scoring: flag accounts with >20% week-over-week"
                f" usage drop, trigger proactive outreach within 24 h. Target: {target*100:.1f}% churn."
            ),
            "impact_tier": "high" if pct_chg < 30 else "medium",
        })

    # ── LTV:CAC ────────────────────────────────────────────────────
    if tc.get("ltv_cac_ratio_max") is not None and ltv_cac <= tc["ltv_cac_ratio_max"]:
        target_ratio = max(tc["ltv_cac_ratio_max"] * 1.35, 3.0)
        pct_chg = (target_ratio - ltv_cac) / max(ltv_cac, 0.1) * 100
        interventions.append({
            "metric": "LTV:CAC Ratio",
            "current_value": f"{ltv_cac:.1f}x",
            "target_value": f"{target_ratio:.1f}x",
            "change_needed": f"Improve by {target_ratio - ltv_cac:.1f}x",
            "difficulty": _diff(min(pct_chg, 80)),
            "estimated_confidence_drop": _drop(1.1),
            "action": (
                f"Shift acquisition budget to highest-LTV segments (referral / inbound). "
                f"Launch expansion revenue: identify top 20% accounts by usage for upsell. Target LTV:CAC {target_ratio:.1f}x."
            ),
            "impact_tier": "high" if ltv_cac < 1 else "medium",
        })

    # ── Burn Multiple ──────────────────────────────────────────────
    if tc.get("burn_multiple_min") is not None and burn_mult >= tc["burn_multiple_min"]:
        target_bm = tc["burn_multiple_min"] * 0.75
        net_new = metrics.mrr * metrics.mrr_growth_rate
        target_burn = target_bm * net_new if net_new > 0 else metrics.burn_rate * 0.6
        pct_chg = max((metrics.burn_rate - target_burn) / metrics.burn_rate * 100, 0)
        interventions.append({
            "metric": "Burn Multiple",
            "current_value": f"{burn_mult:.1f}x",
            "target_value": f"{target_bm:.1f}x",
            "change_needed": f"Cut burn ~{pct_chg:.0f}%",
            "difficulty": _diff(pct_chg),
            "estimated_confidence_drop": _drop(1.0),
            "action": (
                f"90-day burn reduction sprint: freeze non-essential hires, audit SaaS stack,"
                f" negotiate vendor terms. Target: ${target_burn:,.0f}/mo burn rate."
            ),
            "impact_tier": "medium",
        })

    # ── Runway ─────────────────────────────────────────────────────
    if tc.get("runway_months_max") is not None and metrics.runway_months <= tc["runway_months_max"]:
        target_runway = tc["runway_months_max"] + 8
        pct_chg = (target_runway - metrics.runway_months) / max(metrics.runway_months, 1) * 100
        interventions.append({
            "metric": "Cash Runway",
            "current_value": f"{metrics.runway_months} months",
            "target_value": f"{target_runway} months",
            "change_needed": f"+{target_runway - metrics.runway_months} months",
            "difficulty": _diff(min(pct_chg, 90)),
            "estimated_confidence_drop": _drop(0.8),
            "action": (
                f"Bridge now: open SAFE with existing investors, negotiate 90-day payment deferrals"
                f" with vendors, accelerate AR collection. Target: {target_runway}-month runway."
            ),
            "impact_tier": "high" if metrics.runway_months < 6 else "medium",
        })

    # ── NPS ────────────────────────────────────────────────────────
    if tc.get("nps_max") is not None and metrics.nps <= tc["nps_max"]:
        target_nps = min(tc["nps_max"] + 22, 50)
        interventions.append({
            "metric": "Net Promoter Score",
            "current_value": str(metrics.nps),
            "target_value": str(target_nps),
            "change_needed": f"+{target_nps - metrics.nps} NPS points",
            "difficulty": "hard" if target_nps - metrics.nps > 40 else "medium",
            "estimated_confidence_drop": _drop(0.85),
            "action": (
                f"Run 10 customer interviews this week. Ship the top-3 detractor pain points"
                f" in 30-day sprints. Target NPS: {target_nps}."
            ),
            "impact_tier": "medium",
        })

    # ── MRR Growth ─────────────────────────────────────────────────
    if tc.get("mrr_growth_rate_max") is not None and metrics.mrr_growth_rate <= tc["mrr_growth_rate_max"]:
        target_g = tc["mrr_growth_rate_max"] * 1.55
        pct_chg = (target_g - metrics.mrr_growth_rate) / max(metrics.mrr_growth_rate, 0.01) * 100
        interventions.append({
            "metric": "MRR Growth Rate",
            "current_value": f"{metrics.mrr_growth_rate*100:.1f}%/mo",
            "target_value": f"{target_g*100:.1f}%/mo",
            "change_needed": f"+{(target_g - metrics.mrr_growth_rate)*100:.1f}pp",
            "difficulty": _diff(min(pct_chg, 90)),
            "estimated_confidence_drop": _drop(1.1),
            "action": (
                f"Launch a usage-based upsell tier targeting your top 20% power users."
                f" Add a referral incentive. Target: {target_g*100:.1f}%/mo MRR growth."
            ),
            "impact_tier": "high" if metrics.mrr_growth_rate < 0.05 else "medium",
        })

    if not interventions:
        return None

    # Sort by impact descending, then difficulty ascending
    interventions.sort(key=lambda x: (-x["estimated_confidence_drop"],
                                      {"easy": 0, "medium": 1, "hard": 2}[x["difficulty"]]))

    top3_sum = sum(i["estimated_confidence_drop"] for i in interventions[:3])
    combined_drop = min(int(top3_sum * 0.82), int(conf_pct * 0.68))

    return {
        "current_confidence": conf_pct,
        "escape_threshold": 60,
        "interventions": interventions,
        "combined_drop": combined_drop,
        "escape_possible": conf_pct - combined_drop < 60,
    }


async def match_patterns_top3(metrics: MetricsInput) -> CocktailMatch | None:
    """
    Multi-pattern Cocktail matching: find up to the top 3 co-occurring failure patterns.

    Returns a CocktailMatch only when 2+ patterns exceed the 0.60 confidence threshold.
    Compound survival rate: max(0.02, min(individual_rates) * 0.5^(n-1))
    This models how co-occurring failure modes multiply risk non-linearly.
    """
    candidates = await _candidate_patterns(metrics)
    if not candidates:
        return None

    scorings = await asyncio.gather(
        *[_score_with_gemini(metrics, p) for p in candidates],
        return_exceptions=True,
    )

    # Collect every confident match (>= 0.60)
    qualified: list[tuple[float, dict, dict, float]] = []
    for pattern, scoring in zip(candidates, scorings):
        if isinstance(scoring, Exception):
            continue
        confidence = float(scoring.get("confidence", 0.0))
        if confidence >= 0.60:
            total = pattern["failure_count"] + pattern["survival_count"]
            survival_rate = pattern["survival_count"] / total if total > 0 else 0.0
            qualified.append((confidence, scoring, pattern, survival_rate))

    # A cocktail requires at least 2 overlapping patterns
    if len(qualified) < 2:
        return None

    qualified.sort(key=lambda x: x[0], reverse=True)
    top3 = qualified[:3]
    n = len(top3)

    survival_rates = [item[3] for item in top3]
    compound_survival = max(0.02, min(survival_rates) * (0.5 ** (n - 1)))

    cocktail_patterns = [
        CocktailPattern(
            pattern_id=pattern["pattern_id"],
            pattern_name=pattern["name"],
            confidence=round(confidence, 2),
            survival_rate=round(survival_rate, 3),
            days_to_crisis=int(scoring.get("days_to_crisis", 90)),
            category=pattern.get("category", ""),
        )
        for confidence, scoring, pattern, survival_rate in top3
    ]

    dominant = top3[0][2]["name"]
    min_days = min(int(scoring.get("days_to_crisis", 90)) for _, scoring, _, _ in top3)
    risk_summary = (
        f"COCKTAIL DETECTED: {n} co-occurring failure patterns. "
        f"Compound survival rate: {compound_survival*100:.0f}%. "
        f"Dominant: {dominant}. Crisis window: ~{min_days} days."
    )

    return CocktailMatch(
        patterns=cocktail_patterns,
        compound_survival_rate=round(compound_survival, 3),
        dominant_pattern=dominant,
        combined_days_to_crisis=min_days,
        risk_summary=risk_summary,
    )


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
        if best_match is not None and best_score < 0.40:
            import logging as _log
            _log.getLogger(__name__).info(
                "UNCHARTED: best match %d%% (%s) — below 40%% floor",
                int(best_score * 100), best_match.get("name", "?"),
            )
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

    # Persist to MongoDB for session memory — MCP primary, Motor fallback
    try:
        from backend.db.connection import get_db
        from backend.services.mcp_client import mcp
        from datetime import datetime, timezone
        doc = {
            "startup_name": metrics.startup_name,
            "checked_at": datetime.now(timezone.utc),
            "alert": True,
            "pattern_name": best_match["name"],
            "confidence": round(best_score, 2),
            "days_to_crisis": best_scoring.get("days_to_crisis", 90),
            "metrics_snapshot": metrics.model_dump(),
        }
        _saved = False
        if mcp.available:
            try:
                _saved = await mcp.insert_one("startup_analyses", doc)
            except Exception as _e:
                import logging as _log
                _log.getLogger(__name__).debug("MCP insert_one failed, using Motor: %s", _e)
        if not _saved:
            db = get_db()
            await db["startup_analyses"].insert_one(doc)
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
        trigger_breakdown=compute_trigger_breakdown(metrics, best_match),
    )
