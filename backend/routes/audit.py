import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend.db.schemas import DecisionAuditInput, AuditResponse, MetricsInput
from backend.services.auditor import audit_decision
from backend.services.output_writer import write_audit
from backend.services.pattern_matcher import compute_oracle_score

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/evaluate", response_model=AuditResponse)
async def evaluate_decision(body: DecisionAuditInput):
    result = await audit_decision(body.decision, body.metrics)
    result.output_file = write_audit(result)
    return result


class PreMortemInput(BaseModel):
    startup_name: str = Field(..., min_length=1, max_length=100)
    decision: str = Field(..., min_length=10, max_length=2000, description="The decision to simulate, e.g. 'Hire 10 engineers and double burn rate'")
    metrics: MetricsInput


def _pre_mortem_verdict(current_score: int, horizons: list[dict], month6_pattern) -> str:
    final_score = horizons[-1]["oracle_score"] if horizons else current_score
    delta = final_score - current_score
    if month6_pattern and month6_pattern.confidence >= 0.75:
        return "HIGH RISK: This decision is projected to trigger a critical failure pattern within 6 months."
    elif month6_pattern and month6_pattern.confidence >= 0.60:
        return "CAUTION: This decision may activate a failure pattern within 6 months. Monitor closely."
    elif delta <= -20:
        return "CAUTION: This decision significantly degrades your Oracle Score over 6 months."
    elif delta >= 10:
        return "POSITIVE: This decision is projected to improve your startup health trajectory."
    else:
        return "NEUTRAL: This decision has limited impact on your failure risk trajectory."


@router.post("/pre-mortem")
async def oracle_pre_mortem(body: PreMortemInput):
    """
    Oracle Pre-Mortem: simulate how a strategic decision ripples through startup metrics.

    1. Gemini Flash projects metrics at months +1, +3, +6 given the decision.
    2. Oracle Score is computed at each horizon (deterministic, no Gemini needed).
    3. Pattern matcher runs on the month-6 projection to surface emergent failure patterns.

    Returns a risk trajectory (score at each horizon) + worst-case failure pattern at month 6.
    """
    from backend.services.gemini import generate_json_fast
    from backend.services.pattern_matcher import match_patterns

    prompt = f"""You are the Oracle Pre-Mortem agent. Given a startup's current metrics and a
proposed decision, project how key metrics will change at months +1, +3, and +6.

CURRENT METRICS (month {body.metrics.current_month}):
- MRR: ${body.metrics.mrr:,.0f} | Growth: {body.metrics.mrr_growth_rate*100:.1f}%/mo
- Churn: {body.metrics.churn_rate*100:.1f}%/mo
- Burn: ${body.metrics.burn_rate:,.0f}/mo | Runway: {body.metrics.runway_months} months
- Headcount: {body.metrics.headcount}
- NPS: {body.metrics.nps}
- CAC: ${body.metrics.cac:,.0f} | LTV: ${body.metrics.ltv:,.0f}
- Industry: {body.metrics.industry}

PROPOSED DECISION: {body.decision}

Project the realistic impact of this decision. Account for second-order effects:
- Hiring increases burn → reduces runway
- Enterprise sales has 3-6 month cycles → MRR impact is delayed
- Price changes affect churn and NPS within 1-2 months
- Marketing spend improves growth rate but also increases burn and CAC

Return JSON with EXACTLY this structure:
{{
  "month_1": {{
    "mrr": <number>, "mrr_growth_rate": <0.0-2.0 float>, "churn_rate": <0.0-1.0 float>,
    "burn_rate": <number>, "runway_months": <int>, "headcount": <int>,
    "nps": <int -100 to 100>, "cac": <number>, "ltv": <number>
  }},
  "month_3": {{same fields}},
  "month_6": {{same fields}},
  "key_risks": ["<risk 1>", "<risk 2>", "<risk 3>"],
  "key_opportunities": ["<opportunity 1>", "<opportunity 2>"]
}}

Use current values as baseline. Be realistic — not optimistic, not catastrophist.
All numeric fields must be numbers (not strings). runway_months, headcount, nps must be integers."""

    try:
        raw = await generate_json_fast(prompt)
        projected = json.loads(raw)
    except Exception as e:
        logger.error("[pre-mortem] Gemini projection failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Metric projection failed: {e}")

    # Compute Oracle Score at each horizon (pure math, instant)
    horizons = []
    for month_offset, key in [(1, "month_1"), (3, "month_3"), (6, "month_6")]:
        proj = projected.get(key, {})
        try:
            projected_metrics = MetricsInput(
                startup_name=body.metrics.startup_name,
                current_month=min(body.metrics.current_month + month_offset, 120),
                mrr=float(proj.get("mrr", body.metrics.mrr)),
                mrr_growth_rate=float(proj.get("mrr_growth_rate", body.metrics.mrr_growth_rate)),
                churn_rate=float(proj.get("churn_rate", body.metrics.churn_rate)),
                burn_rate=float(proj.get("burn_rate", body.metrics.burn_rate)),
                runway_months=int(proj.get("runway_months", body.metrics.runway_months)),
                headcount=int(proj.get("headcount", body.metrics.headcount)),
                nps=int(proj.get("nps", body.metrics.nps)),
                cac=float(proj.get("cac", body.metrics.cac)),
                ltv=float(proj.get("ltv", body.metrics.ltv)),
                industry=body.metrics.industry,
            )
            score, band = compute_oracle_score(projected_metrics, 0.0)
        except Exception:
            score, band = compute_oracle_score(body.metrics, 0.0)
        horizons.append({
            "month_offset": month_offset,
            "oracle_score": score,
            "score_band": band,
            "projected_metrics": proj,
        })

    # Run pattern matcher on month-6 projection — detect emergent failure patterns
    month6_proj = projected.get("month_6", {})
    month6_pattern = None
    try:
        month6_metrics = MetricsInput(
            startup_name=body.metrics.startup_name,
            current_month=min(body.metrics.current_month + 6, 120),
            mrr=float(month6_proj.get("mrr", body.metrics.mrr)),
            mrr_growth_rate=float(month6_proj.get("mrr_growth_rate", body.metrics.mrr_growth_rate)),
            churn_rate=float(month6_proj.get("churn_rate", body.metrics.churn_rate)),
            burn_rate=float(month6_proj.get("burn_rate", body.metrics.burn_rate)),
            runway_months=int(month6_proj.get("runway_months", body.metrics.runway_months)),
            headcount=int(month6_proj.get("headcount", body.metrics.headcount)),
            nps=int(month6_proj.get("nps", body.metrics.nps)),
            cac=float(month6_proj.get("cac", body.metrics.cac)),
            ltv=float(month6_proj.get("ltv", body.metrics.ltv)),
            industry=body.metrics.industry,
        )
        month6_pattern = await match_patterns(month6_metrics)
    except Exception as e:
        logger.warning("[pre-mortem] month-6 pattern match failed: %s", e)

    current_score, current_band = compute_oracle_score(body.metrics, 0.0)

    return {
        "startup_name": body.metrics.startup_name,
        "decision": body.decision,
        "current_score": current_score,
        "current_band": current_band,
        "trajectory": horizons,
        "month6_pattern_risk": month6_pattern.model_dump() if month6_pattern else None,
        "key_risks": projected.get("key_risks", []),
        "key_opportunities": projected.get("key_opportunities", []),
        "verdict": _pre_mortem_verdict(current_score, horizons, month6_pattern),
    }
