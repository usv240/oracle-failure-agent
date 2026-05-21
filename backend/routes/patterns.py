import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from backend.db.connection import get_db
from backend.services.mcp_client import mcp

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def list_patterns():
    """
    List all failure patterns.
    Primary path: MongoDB MCP server (mcp_find tool).
    Fallback: Motor direct driver.
    """
    if mcp.available:
        try:
            patterns = await mcp.find(
                "failure_patterns",
                filter_={},
                projection={"_id": 0, "narrative_embedding": 0},
                limit=200,
            )
            logger.info("[MCP] list_patterns via MCP — %d patterns", len(patterns))
            return {"patterns": patterns, "total": len(patterns), "source": "mcp"}
        except Exception as e:
            logger.warning("[MCP] list_patterns MCP error: %s — falling back to Motor", e)

    # Motor fallback
    db = get_db()
    patterns = await db["failure_patterns"].find(
        {}, {"_id": 0, "narrative_embedding": 0}
    ).to_list(length=200)
    return {"patterns": patterns, "total": len(patterns), "source": "motor"}


@router.get("/{pattern_id}")
async def get_pattern(pattern_id: str):
    """
    Get a specific failure pattern by ID.
    Primary path: MongoDB MCP server.
    Fallback: Motor direct driver.
    """
    if mcp.available:
        try:
            pattern = await mcp.find_one(
                "failure_patterns",
                filter_={"pattern_id": pattern_id},
                projection={"_id": 0, "narrative_embedding": 0},
            )
            if pattern:
                logger.info("[MCP] get_pattern %s via MCP", pattern_id)
                return pattern
        except Exception as e:
            logger.warning("[MCP] get_pattern MCP error: %s — falling back to Motor", e)

    # Motor fallback
    db = get_db()
    pattern = await db["failure_patterns"].find_one(
        {"pattern_id": pattern_id}, {"_id": 0, "narrative_embedding": 0}
    )
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return pattern


class PatternSubmission(BaseModel):
    pattern_name: str = Field(..., min_length=5, max_length=120)
    category:     str = Field(..., max_length=50)
    narrative:    str = Field(..., min_length=30, max_length=1500)
    company:      Optional[str] = Field(default=None, max_length=100)
    submitter_role: Optional[str] = Field(default=None, max_length=100)


@router.post("/submit")
async def submit_pattern(body: PatternSubmission):
    """
    Accept a community-submitted failure pattern for review.
    Stores in 'submitted_patterns' collection with status='pending'.
    """
    db = get_db()
    doc = {
        "pattern_name":   body.pattern_name.strip(),
        "category":       body.category,
        "narrative":      body.narrative.strip(),
        "company":        (body.company or "").strip() or None,
        "submitter_role": (body.submitter_role or "").strip() or None,
        "status":         "pending",
        "submitted_at":   datetime.now(timezone.utc),
    }
    result = await db["submitted_patterns"].insert_one(doc)
    return {
        "submitted": True,
        "id": str(result.inserted_id),
        "message": "Thank you — your pattern is under review and will be added to the library if validated.",
    }
