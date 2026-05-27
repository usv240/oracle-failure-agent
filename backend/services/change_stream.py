"""
MongoDB Change Stream watcher — real-time alert detection.

Watches the startup_analyses collection for new alert=True inserts and fires
instant Slack notifications. This complements the 6h polling monitor with
event-driven detection that fires within seconds of a new alert being written.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

_watch_task: Optional[asyncio.Task] = None


async def _watch_loop() -> None:
    """Long-running coroutine that tails startup_analyses via a MongoDB Change Stream."""
    from backend.db.connection import get_db
    from backend.services.monitor import _post_slack, _slack_alert_payload

    db = get_db()
    collection = db["startup_analyses"]

    # React to ALL inserts (alert True or False) — we need both for cascade self-update
    pipeline = [{"$match": {"operationType": "insert"}}]

    logger.info("[ChangeStream] Watching startup_analyses for alert inserts...")

    while True:
        try:
            async with collection.watch(pipeline, full_document="default") as stream:
                async for change in stream:
                    doc = change.get("fullDocument", {})
                    startup_name = doc.get("startup_name", "Unknown")
                    pattern_name = doc.get("pattern_name", "Unknown Pattern")
                    confidence = float(doc.get("confidence", 0.0))
                    days_to_crisis = int(doc.get("days_to_crisis") or 90)
                    is_alert = bool(doc.get("alert", False))

                    if is_alert:
                        logger.info(
                            "[ChangeStream] ALERT insert: %s — %s (%.0f%%)",
                            startup_name, pattern_name, confidence * 100,
                        )

                        try:
                            payload = _slack_alert_payload(
                                startup_name=startup_name,
                                pattern_name=pattern_name,
                                confidence=confidence,
                                days_to_crisis=days_to_crisis,
                                survival_rate=float(doc.get("survival_rate", 0.0)),
                            )
                            await _post_slack(payload)
                        except Exception as slack_err:
                            logger.warning("[ChangeStream] Slack notify failed: %s", slack_err)

                    # ── Self-improving cascade: detect real-world pattern transitions ──
                    # If this startup previously had a DIFFERENT pattern alert in the last
                    # 90 days, that's a confirmed cascade transition in the wild.
                    if is_alert:
                        asyncio.create_task(
                            _check_cascade_transition(db, doc),
                            name=f"cascade-self-update-{startup_name[:20]}",
                        )

        except asyncio.CancelledError:
            logger.info("[ChangeStream] Watcher cancelled — shutting down")
            return
        # noqa
        except Exception as e:
            # Change streams require a replica set; on Atlas this is always available.
            # On local standalone MongoDB this will fail — we retry with backoff.
            logger.warning("[ChangeStream] Watch error: %s — retrying in 30s", e)
            await asyncio.sleep(30)


def start_change_stream() -> None:
    """Start the Change Stream watcher as a background asyncio task."""
    global _watch_task
    _watch_task = asyncio.create_task(_watch_loop(), name="oracle-change-stream")
    logger.info("[ChangeStream] Change stream watcher started")


async def stop_change_stream() -> None:
    """Cancel the Change Stream watcher on shutdown."""
    global _watch_task
    if _watch_task and not _watch_task.done():
        _watch_task.cancel()
        try:
            await _watch_task
        except asyncio.CancelledError:
            pass
    logger.info("[ChangeStream] Change stream watcher stopped")


async def _check_cascade_transition(db, doc: dict) -> None:
    """
    Self-improving cascade graph: detect real-world pattern transitions.

    When a startup fires a NEW alert with pattern B, check if it had a
    DIFFERENT pattern A in the last 90 days. If yes → confirmed A→B transition.
    Update observed_count and recompute probability via Bayesian blend.
    """
    startup_name = doc.get("startup_name")
    new_pattern_id = doc.get("pattern_id")
    checked_at = doc.get("checked_at", datetime.utcnow())

    if not startup_name or not new_pattern_id:
        return

    try:
        cutoff = checked_at - timedelta(days=90) if isinstance(checked_at, datetime) else datetime.utcnow() - timedelta(days=90)

        prior = await db["startup_analyses"].find_one(
            {
                "startup_name": startup_name,
                "alert": True,
                "checked_at": {"$gte": cutoff, "$lt": checked_at},
                "pattern_id": {"$exists": True, "$ne": new_pattern_id},
            },
            sort=[("checked_at", -1)],
        )

        if not prior:
            return

        from_pattern_id = prior.get("pattern_id")
        days_between = (checked_at - prior["checked_at"]).days if isinstance(checked_at, datetime) and isinstance(prior.get("checked_at"), datetime) else 45

        logger.info(
            "[ChangeStream] Confirmed cascade transition: %s → %s (%s, %d days)",
            from_pattern_id, new_pattern_id, startup_name, days_between,
        )

        # Delegate to cascade service to update probabilities
        from backend.services.cascade import record_observed_transition
        await record_observed_transition(from_pattern_id, new_pattern_id, days_between)

    except Exception as e:
        logger.warning("[ChangeStream] Cascade self-update error: %s", e)
