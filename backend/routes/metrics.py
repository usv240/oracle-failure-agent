from fastapi import APIRouter, HTTPException
from backend.db.schemas import MetricsInput, AlertResponse
from backend.services.pattern_matcher import match_patterns
from backend.services.output_writer import write_alert
import traceback
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", response_model=AlertResponse)
async def analyze_metrics(metrics: MetricsInput):
    try:
        match = await match_patterns(metrics)

        if match is None:
            return AlertResponse(
                alert=False,
                startup_name=metrics.startup_name,
                message="No dangerous failure patterns detected. Keep monitoring.",
            )

        output_file = write_alert(match, metrics)
        match.output_file = output_file

        return AlertResponse(
            alert=True,
            startup_name=metrics.startup_name,
            pattern=match,
            message=f"Pattern detected with {int(match.confidence*100)}% confidence.",
        )
    except Exception as e:
        logger.error("ERROR in analyze_metrics:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
