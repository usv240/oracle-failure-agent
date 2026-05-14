"""
Failure Oracle — Google ADK Agent
Wraps pattern matching and decision audit as ADK tools.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from backend.db.schemas import MetricsInput
from backend.services.pattern_matcher import match_patterns
from backend.services.auditor import audit_decision
from backend.db.connection import get_db
import asyncio


async def analyze_startup_metrics(
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
) -> dict:
    """
    Analyze startup metrics against the failure pattern library.
    Uses MongoDB Atlas Vector Search to find semantically similar failure patterns,
    then Gemini scores the match confidence.

    Returns the best matching failure pattern with confidence score,
    warning signals, survival playbook, and estimated days to crisis.
    """
    metrics = MetricsInput(
        startup_name=startup_name,
        current_month=current_month,
        mrr=mrr,
        mrr_growth_rate=mrr_growth_rate,
        churn_rate=churn_rate,
        burn_rate=burn_rate,
        runway_months=runway_months,
        headcount=headcount,
        nps=nps,
        cac=cac,
        ltv=ltv,
        industry=industry,
    )
    result = await match_patterns(metrics)
    if result is None:
        return {
            "alert": False,
            "message": "No dangerous failure patterns detected. Keep monitoring.",
        }
    return {
        "alert": True,
        "pattern_id": result.pattern_id,
        "pattern_name": result.pattern_name,
        "confidence": result.confidence,
        "narrative": result.narrative,
        "warning_signals": [s.signal for s in result.warning_signals_detected],
        "survival_playbook": result.survival_playbook,
        "days_to_crisis": result.days_to_crisis,
        "failure_count": result.failure_count,
        "survival_count": result.survival_count,
    }


async def audit_founder_decision(
    decision: str,
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
) -> dict:
    """
    Evaluate a founder's proposed decision against historical failure cases.
    Returns risk level, historical success/failure rates, and specific recommendation.
    """
    metrics = MetricsInput(
        startup_name=startup_name,
        current_month=current_month,
        mrr=mrr,
        mrr_growth_rate=mrr_growth_rate,
        churn_rate=churn_rate,
        burn_rate=burn_rate,
        runway_months=runway_months,
        headcount=headcount,
        nps=nps,
        cac=cac,
        ltv=ltv,
    )
    result = await audit_decision(decision, metrics)
    return {
        "decision": result.decision,
        "risk_level": result.risk_level,
        "total_cases": result.total_cases,
        "success_cases": result.success_cases,
        "failure_cases": result.failure_cases,
        "key_differentiator": result.key_differentiator,
        "recommendation": result.recommendation,
    }


async def list_failure_patterns(category: str = "") -> dict:
    """
    List failure patterns from the MongoDB library.
    Optionally filter by category (e.g. 'premature_scaling', 'fundraising',
    'product_market_fit', 'unit_economics', 'team', 'competition').
    """
    db = get_db()
    query = {"category": category} if category else {}
    cursor = db["failure_patterns"].find(query, {"narrative_embedding": 0}).limit(30)
    patterns = await cursor.to_list(length=30)
    return {
        "count": len(patterns),
        "patterns": [
            {
                "id": p["pattern_id"],
                "name": p["name"],
                "category": p["category"],
                "failure_count": p["failure_count"],
                "survival_count": p["survival_count"],
            }
            for p in patterns
        ],
    }


# System prompt
SYSTEM_PROMPT = open(
    os.path.join(os.path.dirname(__file__), "system_prompt.txt")
).read()

# ADK Agent definition
failure_oracle_agent = Agent(
    name="failure_oracle",
    model="gemini-2.5-flash",
    description=(
        "AI agent that detects startup failure patterns in real-time. "
        "Uses MongoDB Atlas Vector Search over 30 documented failure patterns "
        "to warn founders before a crisis becomes fatal."
    ),
    instruction=SYSTEM_PROMPT,
    tools=[
        FunctionTool(analyze_startup_metrics),
        FunctionTool(audit_founder_decision),
        FunctionTool(list_failure_patterns),
    ],
)

# Entry point for ADK CLI: adk run agent/agent.py
root_agent = failure_oracle_agent
