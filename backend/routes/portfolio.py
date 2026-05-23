"""
VC Portfolio Mode — analyze multiple startups in parallel and return ranked risk list.
"""
import asyncio
import logging
from fastapi import APIRouter
from pydantic import BaseModel, Field
from backend.db.schemas import MetricsInput
from backend.services.pattern_matcher import _candidate_patterns, _score_with_gemini

logger = logging.getLogger(__name__)
router = APIRouter()


class PortfolioRequest(BaseModel):
    startups: list[MetricsInput] = Field(..., min_length=1, max_length=20)


class PortfolioCompanyResult(BaseModel):
    startup_name: str
    risk_level: str          # CRITICAL | HIGH | MODERATE | SAFE
    confidence: float
    pattern_name: str | None = None
    days_to_crisis: int | None = None
    survival_rate: float | None = None
    match_reasoning: str | None = None
    error: str | None = None


class PortfolioResponse(BaseModel):
    total: int
    critical: int
    high_risk: int
    moderate: int
    safe: int
    companies: list[PortfolioCompanyResult]


async def _analyze_single(metrics: MetricsInput) -> PortfolioCompanyResult:
    try:
        candidates = await _candidate_patterns(metrics)
        if not candidates:
            return PortfolioCompanyResult(
                startup_name=metrics.startup_name,
                risk_level="SAFE",
                confidence=0.0,
            )

        scorings = await asyncio.gather(
            *[_score_with_gemini(metrics, p) for p in candidates[:3]],
            return_exceptions=True,
        )

        best_score = 0.0
        best_pattern = None
        best_scoring = None
        for pattern, scoring in zip(candidates[:3], scorings):
            if isinstance(scoring, Exception):
                continue
            score = scoring.get("confidence", 0.0)
            if score > best_score:
                best_score = score
                best_pattern = pattern
                best_scoring = scoring

        if best_score < 0.60 or best_pattern is None:
            return PortfolioCompanyResult(
                startup_name=metrics.startup_name,
                risk_level="SAFE",
                confidence=round(best_score, 2),
            )

        pct = best_score * 100
        if pct >= 88:
            risk_level = "CRITICAL"
        elif pct >= 75:
            risk_level = "HIGH"
        elif pct >= 60:
            risk_level = "MODERATE"
        else:
            risk_level = "SAFE"

        total = best_pattern["failure_count"] + best_pattern["survival_count"]
        survival_rate = best_pattern["survival_count"] / total if total > 0 else 0.0

        return PortfolioCompanyResult(
            startup_name=metrics.startup_name,
            risk_level=risk_level,
            confidence=round(best_score, 2),
            pattern_name=best_pattern["name"],
            days_to_crisis=best_scoring.get("days_to_crisis"),
            survival_rate=round(survival_rate, 3),
            match_reasoning=best_scoring.get("match_reasoning"),
        )
    except Exception as e:
        logger.error("Portfolio analysis failed for %s: %s", metrics.startup_name, e)
        return PortfolioCompanyResult(
            startup_name=metrics.startup_name,
            risk_level="SAFE",
            confidence=0.0,
            error=str(e),
        )


async def _analyze_with_stagger(metrics: MetricsInput, idx: int) -> PortfolioCompanyResult:
    """Stagger concurrent embed calls by 300ms per company to avoid Voyage AI rate limits."""
    if idx > 0:
        await asyncio.sleep(idx * 0.3)
    return await _analyze_single(metrics)


@router.post("/analyze", response_model=PortfolioResponse)
async def analyze_portfolio(body: PortfolioRequest):
    """
    Analyze a portfolio of startups in parallel (staggered to respect embed rate limits).
    Returns each company's risk level, matched pattern, and days to crisis — ranked by risk.
    """
    results = await asyncio.gather(
        *[_analyze_with_stagger(m, i) for i, m in enumerate(body.startups)]
    )
    results = sorted(results, key=lambda r: r.confidence, reverse=True)

    risk_order = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2, "SAFE": 3}
    results = sorted(results, key=lambda r: risk_order.get(r.risk_level, 4))

    return PortfolioResponse(
        total=len(results),
        critical=sum(1 for r in results if r.risk_level == "CRITICAL"),
        high_risk=sum(1 for r in results if r.risk_level == "HIGH"),
        moderate=sum(1 for r in results if r.risk_level == "MODERATE"),
        safe=sum(1 for r in results if r.risk_level == "SAFE"),
        companies=results,
    )
