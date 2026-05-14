from fastapi import APIRouter
from backend.db.connection import get_db

router = APIRouter()


@router.get("/")
async def list_patterns():
    db = get_db()
    patterns = await db["failure_patterns"].find(
        {}, {"_id": 0, "pattern_id": 1, "name": 1, "category": 1,
             "failure_count": 1, "survival_count": 1}
    ).to_list(length=100)
    return {"patterns": patterns, "total": len(patterns)}


@router.get("/{pattern_id}")
async def get_pattern(pattern_id: str):
    db = get_db()
    pattern = await db["failure_patterns"].find_one(
        {"pattern_id": pattern_id}, {"_id": 0}
    )
    if not pattern:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Pattern not found")
    return pattern
