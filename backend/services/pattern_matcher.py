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


async def _candidate_patterns(metrics: MetricsInput) -> list[dict]:
    """
    First-pass filter: pull patterns whose numeric trigger conditions
    overlap with the startup's current metrics.
    Returns up to 5 candidates.
    """
    db = get_db()
    burn_mult = _burn_multiple(metrics)
    ltv_cac = _ltv_cac_ratio(metrics)

    # First-pass filter: stage month range + any one trigger condition signals a match.
    # Each condition is separate in $or so a pattern only needs ONE field defined to qualify.
    query = {
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

    cursor = get_db()["failure_patterns"].find(query).limit(3)
    return await cursor.to_list(length=3)


async def _score_with_gemini(metrics: MetricsInput, pattern: dict) -> dict:
    """
    Ask Gemini to score the match confidence and extract detected signals.
    Returns JSON with: confidence, detected_signals, days_to_crisis, narrative_summary.
    """
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
Known warning signals: {json.dumps([s['signal'] for s in pattern['warning_signals']])}

TASK: Return JSON with exactly these fields:
{{
  "confidence": <float 0.0-1.0 — how closely do the metrics match this pattern?>,
  "detected_signals": [
    {{"signal": "<signal text>", "status": "DETECTED|EMERGING|NOT_YET", "days_detectable": <int or null>}}
  ],
  "days_to_crisis": <estimated days to crisis if no action — integer>,
  "match_reasoning": "<1-2 sentence explanation of why this is or isn't a strong match>"
}}

Be rigorous. Only return high confidence (>0.75) if the metrics clearly match multiple trigger conditions.
"""
    raw = await gemini.generate_json_fast(prompt)
    return json.loads(raw)


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
    )
