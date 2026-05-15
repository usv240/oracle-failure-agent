"""Decision auditor — evaluates a proposed decision against historical patterns.

Pattern fetch uses MongoDB MCP server (primary) with Motor fallback.
"""
import json
import logging
from backend.db.connection import get_db
from backend.db.schemas import MetricsInput, AuditResponse
from backend.services import gemini
from backend.services.pattern_matcher import _burn_multiple, _ltv_cac_ratio
from backend.services.mcp_client import mcp

logger = logging.getLogger(__name__)


async def _fetch_patterns_for_audit() -> list[dict]:
    """
    Fetch failure patterns for decision auditing.
    Primary: MongoDB MCP (uses mcp_find / find tool).
    Fallback: Motor direct driver.
    """
    if mcp.available:
        try:
            patterns = await mcp.find(
                "failure_patterns",
                projection={"_id": 0, "narrative_embedding": 0, "warning_signals": 0,
                            "survival_playbook": 0, "famous_failures": 0},
                limit=100,
            )
            logger.info("[MCP] audit fetched %d patterns via MCP", len(patterns))
            return patterns
        except Exception as e:
            logger.warning("[MCP] audit pattern fetch failed: %s — falling back to Motor", e)

    # Motor fallback
    db = get_db()
    patterns = await db["failure_patterns"].find(
        {},
        {"_id": 0, "narrative_embedding": 0, "warning_signals": 0,
         "survival_playbook": 0, "famous_failures": 0}
    ).to_list(length=100)
    logger.info("[Motor] audit fetched %d patterns via Motor fallback", len(patterns))
    return patterns


async def audit_decision(decision: str, metrics: MetricsInput) -> AuditResponse:
    # Fetch patterns via MCP (or Motor fallback)
    patterns = await _fetch_patterns_for_audit()

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

KNOWN FAILURE PATTERNS ({len(patterns)} documented patterns):
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
