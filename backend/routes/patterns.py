import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from backend.db.connection import get_db
from backend.services.mcp_client import mcp

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/analytics")
async def pattern_analytics():
    """
    Multi-dimensional pattern library analytics via a single MongoDB $facet aggregation.

    Returns four lenses in one query:
      - by_category:       pattern count + avg failure rate per category
      - by_stage:          $bucket distribution across startup lifecycle months
      - deadliest_patterns: top-5 patterns by raw failure rate
      - overview:          library-wide totals and aggregate survival rate

    Uses MCP aggregate when available; Motor fallback otherwise.
    """
    _survival_rate_expr = {
        "$cond": [
            {"$gt": [{"$add": ["$failure_count", "$survival_count"]}, 0]},
            {
                "$divide": [
                    "$survival_count",
                    {"$add": ["$failure_count", "$survival_count"]},
                ]
            },
            0,
        ]
    }
    _failure_rate_expr = {
        "$cond": [
            {"$gt": [{"$add": ["$failure_count", "$survival_count"]}, 0]},
            {
                "$divide": [
                    "$failure_count",
                    {"$add": ["$failure_count", "$survival_count"]},
                ]
            },
            0,
        ]
    }

    pipeline: list[dict] = [
        {
            "$facet": {
                "by_category": [
                    {
                        "$group": {
                            "_id": "$category",
                            "count": {"$sum": 1},
                            "avg_failure_rate": {"$avg": _failure_rate_expr},
                            "total_cases": {
                                "$sum": {"$add": ["$failure_count", "$survival_count"]}
                            },
                        }
                    },
                    {"$sort": {"count": -1}},
                    {
                        "$project": {
                            "_id": 0,
                            "category": "$_id",
                            "count": 1,
                            "avg_failure_rate": {"$round": ["$avg_failure_rate", 3]},
                            "total_cases": 1,
                        }
                    },
                ],
                "by_stage": [
                    {
                        "$bucket": {
                            "groupBy": "$stage_month_min",
                            "boundaries": [0, 6, 12, 18, 24, 36],
                            "default": "36+",
                            "output": {
                                "count": {"$sum": 1},
                                "avg_survival_rate": {"$avg": _survival_rate_expr},
                            },
                        }
                    },
                    {
                        "$project": {
                            "month_range_start": "$_id",
                            "count": 1,
                            "avg_survival_rate": {"$round": ["$avg_survival_rate", 3]},
                        }
                    },
                ],
                "deadliest_patterns": [
                    {
                        "$addFields": {
                            "failure_rate": _failure_rate_expr,
                        }
                    },
                    {"$sort": {"failure_rate": -1}},
                    {"$limit": 5},
                    {
                        "$project": {
                            "_id": 0,
                            "pattern_id": 1,
                            "name": 1,
                            "category": 1,
                            "failure_rate": {"$round": ["$failure_rate", 3]},
                            "failure_count": 1,
                            "survival_count": 1,
                        }
                    },
                ],
                "overview": [
                    {
                        "$group": {
                            "_id": None,
                            "total_patterns": {"$sum": 1},
                            "total_cases": {
                                "$sum": {"$add": ["$failure_count", "$survival_count"]}
                            },
                            "total_failures": {"$sum": "$failure_count"},
                            "avg_survival_rate": {"$avg": _survival_rate_expr},
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "total_patterns": 1,
                            "total_cases": 1,
                            "total_failures": 1,
                            "avg_survival_rate": {"$round": ["$avg_survival_rate", 3]},
                        }
                    },
                ],
            }
        }
    ]

    if mcp.available:
        try:
            results = await mcp.aggregate("failure_patterns", pipeline)
            if results:
                logger.info("[MCP] pattern_analytics via MCP $facet")
                return results[0] if isinstance(results, list) else results
        except Exception as e:
            logger.warning("[MCP] pattern_analytics MCP error: %s — falling back to Motor", e)

    db = get_db()
    results = await db["failure_patterns"].aggregate(pipeline).to_list(length=1)
    return results[0] if results else {}


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


@router.get("/{pattern_id}/similar")
async def similar_patterns(pattern_id: str):
    """
    Find patterns similar to the given one using Atlas Search moreLikeThis operator.
    Returns up to 5 similar patterns ranked by semantic + lexical similarity.

    Primary: Atlas Search moreLikeThis (index: 'default') on narrative + name fields.
    Fallback: Motor category filter (same category, different pattern_id).
    """
    db = get_db()
    source = await db["failure_patterns"].find_one(
        {"pattern_id": pattern_id},
        {"_id": 0, "pattern_id": 1, "name": 1, "narrative": 1, "category": 1},
    )
    if not source:
        raise HTTPException(status_code=404, detail="Pattern not found")

    try:
        pipeline = [
            {
                "$search": {
                    "index": "default",
                    "moreLikeThis": {
                        "like": [
                            {
                                "narrative": source["narrative"],
                                "name": source["name"],
                            }
                        ]
                    },
                }
            },
            {"$match": {"pattern_id": {"$ne": pattern_id}}},
            {"$limit": 5},
            {
                "$project": {
                    "_id": 0,
                    "narrative_embedding": 0,
                    "warning_signals": 0,
                    "survival_playbook": 0,
                    "famous_failures": 0,
                    "trigger_conditions": 0,
                }
            },
        ]
        results = await db["failure_patterns"].aggregate(pipeline).to_list(length=5)
        if results:
            logger.info("[patterns] moreLikeThis returned %d similar patterns for %s", len(results), pattern_id)
            return {"similar": results, "source_pattern_id": pattern_id, "method": "moreLikeThis"}
    except Exception as e:
        logger.warning("[patterns] moreLikeThis failed: %s — using category fallback", e)

    similar = await db["failure_patterns"].find(
        {"category": source["category"], "pattern_id": {"$ne": pattern_id}},
        {
            "_id": 0, "narrative_embedding": 0, "warning_signals": 0,
            "survival_playbook": 0, "famous_failures": 0, "trigger_conditions": 0,
        },
    ).limit(5).to_list(length=5)
    return {"similar": similar, "source_pattern_id": pattern_id, "method": "category_fallback"}


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
