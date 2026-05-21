from fastapi import APIRouter, HTTPException
from backend.db.schemas import MetricsInput, AlertResponse, PatternMatch
from backend.services.adk_runner import run_analysis_via_adk
from backend.services.output_writer import write_alert
import traceback
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", response_model=AlertResponse)
async def analyze_metrics(metrics: MetricsInput):
    """
    Analyze startup metrics via the Google ADK agent.
    The ADK agent orchestrates: MongoDB Atlas Vector Search → Gemini scoring → result.
    """
    try:
        result = await run_analysis_via_adk(metrics)

        if not result.get("alert"):
            return AlertResponse(
                alert=False,
                startup_name=metrics.startup_name,
                message=result.get("message", "No dangerous failure patterns detected."),
            )

        pattern_data = result.get("pattern", {})
        match = PatternMatch(**pattern_data)
        output_file = write_alert(match, metrics)
        match.output_file = output_file

        return AlertResponse(
            alert=True,
            startup_name=metrics.startup_name,
            pattern=match,
            message=result.get("message", f"Pattern detected at {int(match.confidence*100)}%."),
        )
    except Exception as e:
        logger.error("ERROR in analyze_metrics:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
