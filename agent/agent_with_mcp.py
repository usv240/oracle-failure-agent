"""
Failure Oracle — ADK Agent with MongoDB MCP integration.
Uses the MongoDB Atlas MCP server as a tool for direct database queries,
alongside Gemini for semantic pattern scoring.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
from backend.services.pattern_matcher import match_patterns
from backend.services.auditor import audit_decision
from backend.db.schemas import MetricsInput


MONGODB_URI = os.environ.get("MONGODB_URI", "")

# MongoDB Atlas MCP server — provides direct MongoDB tool access
mongodb_mcp = MCPToolset(
    connection_params=StdioServerParameters(
        command="npx",
        args=["-y", "@mongodb-js/mcp-server-mongodb", "--connectionString", MONGODB_URI],
    )
)


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
    Analyze startup metrics against the MongoDB failure pattern library.
    Uses Atlas Vector Search (semantic) + Gemini confidence scoring.
    Returns the best matching failure pattern with survival playbook.
    """
    metrics = MetricsInput(
        startup_name=startup_name, current_month=current_month,
        mrr=mrr, mrr_growth_rate=mrr_growth_rate, churn_rate=churn_rate,
        burn_rate=burn_rate, runway_months=runway_months, headcount=headcount,
        nps=nps, cac=cac, ltv=ltv, industry=industry,
    )
    result = await match_patterns(metrics)
    if result is None:
        return {"alert": False, "message": "No dangerous failure patterns detected."}
    return {
        "alert": True,
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
    """Evaluate a proposed decision against historical failure cases."""
    metrics = MetricsInput(
        startup_name=startup_name, current_month=current_month,
        mrr=mrr, mrr_growth_rate=mrr_growth_rate, churn_rate=churn_rate,
        burn_rate=burn_rate, runway_months=runway_months, headcount=headcount,
        nps=nps, cac=cac, ltv=ltv,
    )
    result = await audit_decision(decision, metrics)
    return {
        "risk_level": result.risk_level,
        "total_cases": result.total_cases,
        "success_cases": result.success_cases,
        "failure_cases": result.failure_cases,
        "key_differentiator": result.key_differentiator,
        "recommendation": result.recommendation,
    }


SYSTEM_PROMPT = open(os.path.join(os.path.dirname(__file__), "system_prompt.txt")).read()

# Agent with both custom tools AND MongoDB MCP tools
failure_oracle_agent = Agent(
    name="failure_oracle",
    model="gemini-2.5-flash",
    description=(
        "Detects startup failure patterns using MongoDB Atlas Vector Search "
        "and Gemini semantic scoring. Warns founders before a crisis becomes fatal."
    ),
    instruction=SYSTEM_PROMPT,
    tools=[
        FunctionTool(analyze_startup_metrics),
        FunctionTool(audit_founder_decision),
        mongodb_mcp,   # MongoDB MCP gives the agent direct DB query capability
    ],
)

root_agent = failure_oracle_agent
