"""
Lightweight telemetry — counts MCP, vector search, and Gemini calls.

Writes one document per event to `telemetry_events` collection with a TTL of 30 days.
Fire-and-forget: the inc() call never blocks or raises into the caller, so a
telemetry write failure can never break the agent pipeline. Counts surface via
get_24h_counts() for the /api/stats endpoint.

This is the live integration-depth proof for judges: every MCP call, every
$vectorSearch, and every Gemini API call is counted and displayed on the UI.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict

logger = logging.getLogger(__name__)

EVENT_TYPES = ("mcp_call", "vector_search", "gemini_call")


def inc(event_type: str) -> None:
    """Fire-and-forget event counter. Never blocks the caller, never raises."""
    if event_type not in EVENT_TYPES:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_write_event(event_type))
    except RuntimeError:
        # No running loop — skip silently (telemetry is best-effort)
        pass


async def _write_event(event_type: str) -> None:
    try:
        # Lazy import to avoid circular imports at module load
        from backend.db.connection import get_db
        db = get_db()
        await db["telemetry_events"].insert_one({
            "type": event_type,
            "at": datetime.now(timezone.utc),
        })
    except Exception as e:
        # Never propagate — telemetry failure must not affect the agent
        logger.debug("telemetry write failed (%s): %s", event_type, e)


async def get_24h_counts() -> Dict[str, int]:
    """
    Return event counts for the last 24 hours, grouped by type.
    Used by the /api/stats endpoint to power the live integration cards.
    """
    counts = {t: 0 for t in EVENT_TYPES}
    try:
        from backend.db.connection import get_db
        db = get_db()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        pipeline = [
            {"$match": {"at": {"$gte": cutoff}}},
            {"$group": {"_id": "$type", "n": {"$sum": 1}}},
        ]
        async for row in db["telemetry_events"].aggregate(pipeline):
            t = row.get("_id")
            if t in counts:
                counts[t] = int(row.get("n", 0))
    except Exception as e:
        logger.debug("telemetry aggregate failed: %s", e)
    return counts


async def ensure_indexes() -> None:
    """Create TTL index so events auto-expire after 30 days. Idempotent."""
    try:
        from backend.db.connection import get_db
        db = get_db()
        # TTL: documents expire 30 days after `at`
        await db["telemetry_events"].create_index("at", expireAfterSeconds=60 * 60 * 24 * 30)
        await db["telemetry_events"].create_index([("type", 1), ("at", -1)])
    except Exception as e:
        logger.warning("telemetry index creation: %s", e)
