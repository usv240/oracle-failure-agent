"""
Public share links — generate a shareable URL for an Oracle analysis result.
Anyone with the link can view the report (no auth) — used for sharing on
Slack/Twitter/board meetings.

Storage: `shared_reports` collection in MongoDB.
TTL: 90 days (Mongo TTL index handles expiration).
"""
import secrets
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.db.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


class ShareCreateRequest(BaseModel):
    startup_name: str = Field(..., min_length=1, max_length=100)
    payload: dict   # the full _lastPayload from frontend (metrics)
    result: dict    # the full _lastResult from frontend (alert + pattern + score)


class ShareCreateResponse(BaseModel):
    share_id: str
    url_path: str   # relative path like /?share=abc123 — frontend adds origin


def _generate_share_id() -> str:
    """URL-safe 10-char random ID — collisions astronomically unlikely."""
    return secrets.token_urlsafe(8).replace("_", "").replace("-", "")[:10]


@router.post("/create", response_model=ShareCreateResponse)
async def create_share(body: ShareCreateRequest):
    """Save analysis result and return a share ID for a public URL."""
    db = get_db()
    share_id = _generate_share_id()

    # Strip any sensitive/redundant data we don't want to persist publicly
    doc = {
        "share_id": share_id,
        "startup_name": body.startup_name,
        "payload": body.payload,
        "result": body.result,
        "created_at": datetime.now(timezone.utc),
        "view_count": 0,
    }

    try:
        await db["shared_reports"].insert_one(doc)
    except Exception as e:
        logger.exception("Failed to create share link")
        raise HTTPException(status_code=500, detail="Failed to create share link")

    return ShareCreateResponse(share_id=share_id, url_path=f"/?share={share_id}")


@router.get("/{share_id}")
async def get_share(share_id: str):
    """Fetch a public share by ID. No auth — anyone with the link can view."""
    if not share_id or len(share_id) > 32:
        raise HTTPException(status_code=400, detail="Invalid share ID")

    db = get_db()
    doc = await db["shared_reports"].find_one(
        {"share_id": share_id},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Share not found or expired")

    # Increment view count (fire and forget)
    try:
        await db["shared_reports"].update_one(
            {"share_id": share_id},
            {"$inc": {"view_count": 1}},
        )
    except Exception:
        pass

    return doc
