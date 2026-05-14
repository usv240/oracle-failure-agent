"""
Run this once to seed the failure patterns into MongoDB.
Usage: python -m backend.db.seed
"""
import asyncio
import json
from pathlib import Path
from backend.db.connection import get_db, close


async def seed_patterns():
    db = get_db()
    collection = db["failure_patterns"]

    base = json.loads(Path("data/failure_patterns_seed.json").read_text(encoding="utf-8"))
    extra_path = Path("data/failure_patterns_extra.json")
    extra = json.loads(extra_path.read_text(encoding="utf-8")) if extra_path.exists() else []
    patterns = base + extra

    # Drop existing and re-seed for idempotency
    await collection.drop()

    result = await collection.insert_many(patterns)
    print(f"✅ Seeded {len(result.inserted_ids)} failure patterns")

    # Create indexes
    await collection.create_index("pattern_id", unique=True)
    await collection.create_index("category")
    await collection.create_index([("stage_month_min", 1), ("stage_month_max", 1)])
    print("✅ Indexes created")

    await close()


if __name__ == "__main__":
    asyncio.run(seed_patterns())
