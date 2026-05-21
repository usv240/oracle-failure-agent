"""
Background monitoring service — The Oracle watches continuously.

Founders register their metrics once. The Oracle re-runs analysis every
MONITOR_INTERVAL_HOURS and writes new alerts to MongoDB if the pattern changes.
When an alert fires or worsens, it posts to a Slack webhook (if configured).

This turns ORACLE from a one-shot form into a persistent watching agent that
takes real-world action without being asked.
"""
import asyncio
import logging
from datetime import datetime, timezone

import httpx

from backend.db.connection import get_db
from backend.db.schemas import MetricsInput

logger = logging.getLogger(__name__)

MONITOR_INTERVAL_HOURS = 6
_monitor_task: asyncio.Task | None = None

def _get_app_url() -> str:
    from backend.config import settings
    return settings.APP_URL

CLOUD_RUN_URL = _get_app_url()


# ── Slack notification ───────────────────────────────────────────────────────

async def _post_slack(payload: dict) -> None:
    """POST a Block Kit payload to the configured Slack incoming webhook. Silent if not set."""
    from backend.config import settings
    url = settings.SLACK_WEBHOOK_URL
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(url, json=payload)
        logger.info("[Monitor] Slack notification sent")
    except Exception as e:
        logger.warning("[Monitor] Slack notification failed: %s", e)


def _slack_alert_payload(
    startup_name: str,
    pattern_name: str,
    confidence: float,
    days_to_crisis: int,
    survival_rate: float = 0.0,
    previous_confidence: float | None = None,
    match_reasoning: str | None = None,
) -> dict:
    """
    Build a Slack Block Kit payload for an Oracle alert.
    Uses attachments with color sidebar + rich blocks layout.
    """
    pct      = int(confidence * 100)
    surv_pct = int(survival_rate * 100)
    fail_pct = 100 - surv_pct

    if pct >= 88:
        risk_label = "CRITICAL"
        color      = "#ef4444"
        btn_style  = "danger"
    elif pct >= 75:
        risk_label = "HIGH RISK"
        color      = "#f97316"
        btn_style  = "danger"
    else:
        risk_label = "MODERATE RISK"
        color      = "#f59e0b"
        btn_style  = "primary"

    # Trend line
    trend_text = ""
    if previous_confidence is not None:
        prev_pct = int(previous_confidence * 100)
        arrow = "+" if pct > prev_pct else "-"
        delta = abs(pct - prev_pct)
        trend_text = f"  ({arrow}{delta}pp vs last check)"

    fallback = f"Oracle Alert — {startup_name} | {risk_label} | {pattern_name} at {pct}% match | ~{days_to_crisis} days to crisis"

    blocks: list[dict] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{startup_name}*  —  {risk_label}\n*{pattern_name}*{trend_text}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Match*\n{pct}%"},
                {"type": "mrkdwn", "text": f"*Days to crisis*\n~{days_to_crisis}"},
                {"type": "mrkdwn", "text": f"*Failed*\n{fail_pct}% historically"},
                {"type": "mrkdwn", "text": f"*Survived*\n{surv_pct}% with action"},
            ],
        },
    ]

    if match_reasoning:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": match_reasoning}],
        })

    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Full Analysis"},
                "url": CLOUD_RUN_URL,
                "style": btn_style,
            }
        ],
    })

    return {
        "text": fallback,  # notification fallback
        "attachments": [
            {
                "color": color,
                "fallback": fallback,
                "blocks": blocks,
            }
        ],
    }


# ── Core monitoring logic ────────────────────────────────────────────────────

async def register_startup(metrics: MetricsInput) -> dict:
    """Save or update a startup in the watched_startups collection."""
    db = get_db()
    doc = {
        "startup_name": metrics.startup_name,
        "metrics": metrics.model_dump(),
        "registered_at": datetime.now(timezone.utc),
        "last_checked": None,
        "last_alert": None,
        "check_count": 0,
        "watching": True,
    }
    await db["watched_startups"].update_one(
        {"startup_name": metrics.startup_name},
        {"$set": doc, "$setOnInsert": {"first_registered": datetime.now(timezone.utc)}},
        upsert=True,
    )
    logger.info("[Monitor] Registered '%s' for continuous monitoring", metrics.startup_name)
    return {
        "watching": True,
        "startup_name": metrics.startup_name,
        "message": f"Oracle is now watching {metrics.startup_name}. Re-analysis every {MONITOR_INTERVAL_HOURS} hours.",
    }


async def get_watch_status(startup_name: str) -> dict | None:
    """Get monitoring status for a startup."""
    db = get_db()
    doc = await db["watched_startups"].find_one(
        {"startup_name": startup_name},
        {"_id": 0, "metrics": 0},
    )
    return doc


async def _check_all_watched() -> None:
    """Re-run analysis for every watched startup. Posts Slack alert if pattern fires or worsens."""
    from backend.services.pattern_matcher import match_patterns
    db = get_db()

    startups = await db["watched_startups"].find({"watching": True}).to_list(length=100)
    if not startups:
        return

    logger.info("[Monitor] Checking %d watched startups", len(startups))

    for doc in startups:
        try:
            metrics = MetricsInput(**doc["metrics"])
            match = await match_patterns(metrics)

            # Get previous confidence to detect worsening
            prev_alert = doc.get("last_alert") or {}
            prev_confidence = prev_alert.get("confidence")

            alert_doc = {
                "startup_name": metrics.startup_name,
                "checked_at": datetime.now(timezone.utc),
                "alert": match is not None,
                "pattern_name": match.pattern_name if match else None,
                "confidence": match.confidence if match else 0.0,
                "days_to_crisis": match.days_to_crisis if match else None,
            }

            # Save to startup_analyses for session memory
            await db["startup_analyses"].insert_one(
                {**alert_doc, "metrics_snapshot": doc["metrics"]}
            )

            # Update watch doc
            await db["watched_startups"].update_one(
                {"startup_name": metrics.startup_name},
                {"$set": {
                    "last_checked": datetime.now(timezone.utc),
                    "last_alert": alert_doc,
                    "check_count": doc.get("check_count", 0) + 1,
                }},
            )

            level = "ALERT" if match else "SAFE"
            logger.info("[Monitor] %s — %s (%s)", metrics.startup_name, level,
                        match.pattern_name if match else "no pattern")

            # Post Slack notification when:
            #   1. New alert fires (was safe, now at risk)
            #   2. Pattern worsens significantly (confidence up ≥5pp)
            if match:
                was_safe = not prev_alert.get("alert", False)
                confidence_worse = (
                    prev_confidence is not None
                    and match.confidence - prev_confidence >= 0.05
                )
                if was_safe or confidence_worse:
                    payload = _slack_alert_payload(
                        startup_name=metrics.startup_name,
                        pattern_name=match.pattern_name,
                        confidence=match.confidence,
                        days_to_crisis=match.days_to_crisis,
                        survival_rate=match.survival_rate,
                        previous_confidence=prev_confidence if not was_safe else None,
                        match_reasoning=match.match_reasoning,
                    )
                    await _post_slack(payload)

        except Exception as e:
            logger.warning("[Monitor] Failed to check '%s': %s", doc.get("startup_name"), e)


# ── Lifecycle ────────────────────────────────────────────────────────────────

async def _monitor_loop() -> None:
    """Long-running background loop — runs every MONITOR_INTERVAL_HOURS."""
    logger.info("[Monitor] Background monitoring started (interval: %dh)", MONITOR_INTERVAL_HOURS)
    while True:
        await asyncio.sleep(MONITOR_INTERVAL_HOURS * 3600)
        try:
            await _check_all_watched()
        except Exception as e:
            logger.warning("[Monitor] Loop error: %s", e)


def start_monitor() -> None:
    """Start the background monitoring loop as an asyncio task."""
    global _monitor_task
    _monitor_task = asyncio.create_task(_monitor_loop(), name="oracle-monitor")
    logger.info("[Monitor] Watching task created")


async def stop_monitor() -> None:
    """Cancel the monitoring loop on shutdown."""
    global _monitor_task
    if _monitor_task:
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
