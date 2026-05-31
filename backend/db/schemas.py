from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


# ── Incoming request models ──────────────────────────────────────────────────

class MetricsInput(BaseModel):
    startup_name: str = Field(..., min_length=1, max_length=100)
    current_month: int = Field(..., ge=1, le=120)
    mrr: float = Field(..., ge=0, le=1_000_000_000, description="Monthly Recurring Revenue in USD")
    mrr_growth_rate: float = Field(..., ge=-1.0, le=100.0, description="e.g. 0.18 = 18% monthly growth")
    churn_rate: float = Field(..., ge=0, le=1, description="e.g. 0.09 = 9% monthly churn")
    burn_rate: float = Field(..., ge=0, le=1_000_000_000, description="Monthly cash burn in USD")
    runway_months: int = Field(..., ge=0, le=600)
    headcount: int = Field(..., ge=1, le=1_000_000)
    nps: int = Field(..., ge=-100, le=100)
    cac: float = Field(..., ge=0, le=100_000_000, description="Customer Acquisition Cost in USD")
    ltv: float = Field(..., ge=0, le=100_000_000, description="Lifetime Value in USD")
    industry: str = Field(default="B2B SaaS", max_length=100)

    @field_validator("startup_name", "industry", mode="before")
    @classmethod
    def strip_strings(cls, v):
        return str(v).strip() if v else v


class DecisionAuditInput(BaseModel):
    startup_name: str = Field(..., min_length=1, max_length=100)
    current_month: int = Field(..., ge=1, le=120)
    decision: str = Field(..., min_length=5, max_length=2000)
    metrics: MetricsInput

    @field_validator("decision", "startup_name", mode="before")
    @classmethod
    def strip_decision_and_name(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class CounterfactualInput(BaseModel):
    startup_name: str = Field(..., min_length=1, max_length=100)
    outcome: str = Field(..., max_length=500)
    metrics_history: list[MetricsInput] = Field(..., max_length=24)


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
    match_reasoning: Optional[str] = None
    trigger_conditions: Optional[dict] = None
    trigger_breakdown: Optional[list] = None  # [{metric, threshold, current, met}] for UI
    output_file: Optional[str] = None


class RecoveryScenario(BaseModel):
    pattern_name: Optional[str] = None
    confidence: float = 0.0
    survival_rate: float = 0.0
    improvements: list[str] = []
    score_delta: int = 0


class EscapeIntervention(BaseModel):
    metric: str
    current_value: str
    target_value: str
    change_needed: str
    difficulty: str                 # "easy" | "medium" | "hard"
    estimated_confidence_drop: int  # pp knocked off the match confidence
    action: str                     # concrete one-liner for the founder
    impact_tier: str = "medium"     # "high" | "medium" | "low"


class EscapePlan(BaseModel):
    current_confidence: int
    escape_threshold: int = 60
    interventions: list[EscapeIntervention] = []
    combined_drop: int = 0          # pp drop if top-3 interventions executed
    escape_possible: bool = False


class CocktailPattern(BaseModel):
    pattern_id: str
    pattern_name: str
    confidence: float
    survival_rate: float
    days_to_crisis: int
    category: str


class CocktailMatch(BaseModel):
    patterns: list[CocktailPattern]
    compound_survival_rate: float
    dominant_pattern: str
    combined_days_to_crisis: int
    risk_summary: str


class AlertResponse(BaseModel):
    alert: bool
    startup_name: str
    pattern: Optional[PatternMatch] = None
    cocktail: Optional[CocktailMatch] = None
    oracle_score: Optional[int] = None
    score_band: Optional[str] = None
    recovery_scenario: Optional[RecoveryScenario] = None
    escape_plan: Optional[EscapePlan] = None
    cascade: Optional[dict] = None  # Failure cascade graph ($graphLookup result)
    uncharted: Optional[dict] = None  # Set when best match < 60%: {is_uncharted, best_confidence, closest_pattern}
    trajectory: Optional[dict] = None  # {direction, oracle_score_delta, oracle_score_velocity, ...}
    message: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AuditResponse(BaseModel):
    decision: str
    key_differentiator: str
    recommendation: str
    risk_level: str
    related_pattern: Optional[str] = None
    rationale: Optional[str] = None
    output_file: Optional[str] = None
    total_cases: int = 0
    success_cases: int = 0
    failure_cases: int = 0
