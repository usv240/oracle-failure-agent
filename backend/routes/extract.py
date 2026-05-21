"""
Transcript extraction — paste any startup text, Oracle extracts the 11 metrics.

Accepts: pitch decks, YC applications, investor updates, board decks, founder posts.
Returns: MetricsInput-compatible dict ready to pre-fill the analysis form.
"""
import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend.services import gemini

logger = logging.getLogger(__name__)
router = APIRouter()


class TranscriptRequest(BaseModel):
    text: str = Field(..., min_length=30, max_length=10000,
                      description="Any startup text — pitch deck, investor update, YC app, etc.")


@router.post("/extract-metrics")
async def extract_metrics_from_transcript(body: TranscriptRequest):
    """
    Extract startup metrics from free-form text using Gemini 3 Flash.
    Returns best-effort estimates for all 11 Oracle input fields.
    """
    prompt = f"""
You are an expert startup analyst. Read the following text about a startup and extract
or estimate the 11 key metrics required for failure pattern analysis.

TEXT:
{body.text}

Extract and return JSON with exactly these fields. Use your best estimate from context
clues if a number isn't stated directly (e.g. estimate MRR from ARR, estimate churn
from retention language, estimate NPS from sentiment). Never leave a field null.

{{
  "startup_name": "<company name, or 'Unknown Startup' if not found>",
  "current_month": <months since founding or product launch — integer 1-120, estimate from context>,
  "mrr": <monthly recurring revenue in USD — float, convert from ARR/weekly if needed>,
  "mrr_growth_rate": <monthly growth rate as decimal e.g. 0.15 = 15% — estimate from language like 'growing fast' or 'flat'>,
  "churn_rate": <monthly churn as decimal e.g. 0.05 = 5%>,
  "burn_rate": <monthly cash burn in USD>,
  "runway_months": <months of runway remaining — integer>,
  "headcount": <number of employees — integer>,
  "nps": <Net Promoter Score -100 to 100 — estimate from sentiment if not stated>,
  "cac": <Customer Acquisition Cost in USD>,
  "ltv": <Lifetime Value in USD>,
  "industry": "<e.g. B2B SaaS, Consumer, Marketplace, Fintech, Healthtech>",
  "_extraction_notes": "<brief note on which values were stated vs estimated>"
}}

If a metric truly cannot be estimated, use these defaults:
  mrr_growth_rate: 0.10, churn_rate: 0.05, nps: 30, cac: 500, ltv: 3000

Be specific with numbers. Do not return 0 for stated-but-zero fields.
"""

    try:
        raw = await gemini.generate_json(prompt)
        data = json.loads(raw)
    except Exception as e:
        logger.exception("Transcript extraction failed")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")

    # Remove internal annotation before returning
    notes = data.pop("_extraction_notes", "")

    # Clamp values to valid ranges
    data["churn_rate"] = max(0.0, min(1.0, float(data.get("churn_rate", 0.05))))
    data["mrr_growth_rate"] = max(-1.0, min(100.0, float(data.get("mrr_growth_rate", 0.10))))
    data["nps"] = max(-100, min(100, int(data.get("nps", 30))))
    data["runway_months"] = max(0, min(600, int(data.get("runway_months", 12))))
    data["headcount"] = max(1, int(data.get("headcount", 5)))

    return {**data, "extraction_notes": notes, "source": "transcript"}
