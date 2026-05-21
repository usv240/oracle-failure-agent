from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from pydantic import BaseModel
from backend.db.schemas import MetricsInput
from backend.services.monitor import register_startup, get_watch_status, _check_all_watched, _post_slack

router = APIRouter()


@router.post("/watch")
async def watch_startup(metrics: MetricsInput):
    """Register a startup for continuous background monitoring."""
    result = await register_startup(metrics)
    return result


@router.get("/watch/{startup_name}")
async def watch_status(startup_name: str):
    """Get monitoring status and last result for a watched startup."""
    doc = await get_watch_status(startup_name)
    if not doc:
        raise HTTPException(status_code=404, detail="Startup not found in watch list")
    return doc


@router.post("/watch/{startup_name}/check-now")
async def check_now(startup_name: str):
    """Trigger an immediate re-analysis for a watched startup."""
    await _check_all_watched()
    doc = await get_watch_status(startup_name)
    return doc or {"message": "Checked"}


@router.post("/trigger-check")
async def cloud_scheduler_trigger(
    x_cloudscheduler_jobname: Optional[str] = Header(None),
    x_cloudscheduler_scheduletime: Optional[str] = Header(None),
):
    """
    Cloud Scheduler endpoint — called by Google Cloud Scheduler every 6 hours.
    Triggers a full re-analysis of all watched startups.

    Google Cloud Scheduler sends these headers automatically:
      X-CloudScheduler-JobName: <job name>
      X-CloudScheduler-ScheduleTime: <ISO timestamp>

    Configure in GCP:
      gcloud scheduler jobs create http oracle-monitor-check \
        --location=us-central1 \
        --schedule="0 */6 * * *" \
        --uri="https://<your-cloud-run-url>/api/metrics/trigger-check" \
        --http-method=POST
    """
    import logging
    logger = logging.getLogger(__name__)
    if x_cloudscheduler_jobname:
        logger.info("[CloudScheduler] Triggered by job: %s at %s",
                    x_cloudscheduler_jobname, x_cloudscheduler_scheduletime)
    else:
        logger.info("[CloudScheduler] Manual trigger-check called")

    await _check_all_watched()
    return {"triggered": True, "message": "Re-analysis complete for all watched startups."}


class SlackShareRequest(BaseModel):
    startup_name: str
    pattern_name: str
    confidence: float
    days_to_crisis: int
    survival_rate: float
    match_reasoning: Optional[str] = None


@router.post("/slack-share")
async def slack_share(body: SlackShareRequest):
    """Manually post an Oracle alert to the configured Slack webhook."""
    from backend.config import settings
    if not settings.SLACK_WEBHOOK_URL:
        raise HTTPException(status_code=400, detail="SLACK_WEBHOOK_URL not configured")

    from backend.services.monitor import _slack_alert_payload
    payload = _slack_alert_payload(
        startup_name=body.startup_name,
        pattern_name=body.pattern_name,
        confidence=body.confidence,
        days_to_crisis=body.days_to_crisis,
        survival_rate=body.survival_rate,
        match_reasoning=body.match_reasoning,
    )
    await _post_slack(payload)
    return {"posted": True}
