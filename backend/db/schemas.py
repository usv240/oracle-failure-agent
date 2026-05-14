from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── Incoming request models ──────────────────────────────────────────────────

class MetricsInput(BaseModel):
    startup_name: str
    current_month: int = Field(..., ge=1, le=120)
    mrr: float = Field(..., ge=0, description="Monthly Recurring Revenue in USD")
    mrr_growth_rate: float = Field(..., description="e.g. 0.18 = 18% monthly growth")
    churn_rate: float = Field(..., ge=0, le=1, description="e.g. 0.09 = 9% monthly churn")
    burn_rate: float = Field(..., ge=0, description="Monthly cash burn in USD")
    runway_months: int = Field(..., ge=0)
    headcount: int = Field(..., ge=1)
    nps: int = Field(..., ge=-100, le=100)
    cac: float = Field(..., ge=0, description="Customer Acquisition Cost in USD")
    ltv: float = Field(..., ge=0, description="Lifetime Value in USD")
    industry: str = "B2B SaaS"


class DecisionAuditInput(BaseModel):
    startup_name: str
    current_month: int
    decision: str
    metrics: MetricsInput


class CounterfactualInput(BaseModel):
    startup_name: str
    outcome: str
    metrics_history: list[MetricsInput]


# ── Response models ───────────────────────────────────────────────────────────

class WarningSig(BaseModel):
    signal: str
    days_detectable: Optional[int] = None
    status: str = "DETECTED"


class PatternMatch(BaseModel):
    pattern_id: str
    pattern_name: str
    confidence: float
    failure_count: int
    survival_count: int
    survival_rate: float
    narrative: str
    warning_signals_detected: list[WarningSig]
    survival_playbook: list[str]
    famous_failures: list[dict]
    days_to_crisis: int
    output_file: Optional[str] = None


class AlertResponse(BaseModel):
    alert: bool
    startup_name: str
    pattern: Optional[PatternMatch] = None
    message: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AuditResponse(BaseModel):
    decision: str
    total_cases: int
    success_cases: int
    failure_cases: int
    key_differentiator: str
    recommendation: str
    risk_level: str
    output_file: Optional[str] = None
