"""Decision auditor — evaluates a proposed decision against historical patterns."""
import json
from backend.db.connection import get_db
from backend.db.schemas import MetricsInput, AuditResponse
from backend.services import gemini
from backend.services.pattern_matcher import _burn_multiple, _ltv_cac_ratio


async def audit_decision(decision: str, metrics: MetricsInput) -> AuditResponse:
    db = get_db()

    # Fetch all patterns to reason over
    patterns = await db["failure_patterns"].find({}).to_list(length=50)
    pattern_names = [
        f"- {p['pattern_id']}: {p['name']} — {p['narrative'][:120]}..."
        for p in patterns
    ]

    prompt = f"""
You are an advisor with deep knowledge of startup failure patterns.
A founder is considering making the following decision. Evaluate it against
historical failure data.

DECISION: "{decision}"

CURRENT STARTUP STATE:
- Month: {metrics.current_month}
- MRR: ${metrics.mrr:,.0f} (growing {metrics.mrr_growth_rate*100:.1f}%/month)
- Churn: {metrics.churn_rate*100:.1f}%/month
- Burn: ${metrics.burn_rate:,.0f}/month | Runway: {metrics.runway_months} months
- Headcount: {metrics.headcount}
- NPS: {metrics.nps}
- LTV:CAC: {_ltv_cac_ratio(metrics):.1f}x
- Burn multiple: {_burn_multiple(metrics):.1f}x

KNOWN FAILURE PATTERNS (for context):
{chr(10).join(pattern_names)}

Evaluate this decision and return JSON with exactly these fields:
{{
  "total_cases": <int — estimated historical cases with similar decision at similar stage>,
  "success_cases": <int>,
  "failure_cases": <int>,
  "key_differentiator": "<what separated success cases from failure cases — 1 sentence>",
  "recommendation": "<specific recommendation — 2-3 sentences>",
  "risk_level": "<LOW|MEDIUM|HIGH|CRITICAL>",
  "related_pattern": "<pattern_id of most relevant failure pattern, or null>",
  "rationale": "<1 paragraph explaining the risk assessment>"
}}

Be honest. If the decision is risky given the current metrics, say so clearly.
"""

    raw = await gemini.generate_json_fast(prompt)
    result = json.loads(raw)

    return AuditResponse(
        decision=decision,
        total_cases=result.get("total_cases", 0),
        success_cases=result.get("success_cases", 0),
        failure_cases=result.get("failure_cases", 0),
        key_differentiator=result.get("key_differentiator", ""),
        recommendation=result.get("recommendation", ""),
        risk_level=result.get("risk_level", "MEDIUM"),
    )
