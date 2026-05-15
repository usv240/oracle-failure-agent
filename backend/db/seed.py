"""
Run this once to seed the failure patterns into MongoDB.
Usage: python -m backend.db.seed
"""
import asyncio
import json
from pathlib import Path
from backend.db.connection import get_db, close
from backend.services.gemini import embed


async def seed_patterns():
    db = get_db()
    collection = db["failure_patterns"]

    base = json.loads(Path("data/failure_patterns_seed.json").read_text(encoding="utf-8"))
    extra_path = Path("data/failure_patterns_extra.json")
    extra = json.loads(extra_path.read_text(encoding="utf-8")) if extra_path.exists() else []
    patterns = base + extra

    # Drop existing and re-seed for idempotency
    await collection.drop()

    # Generate embeddings for each pattern's narrative
    print(f"Generating embeddings for {len(patterns)} patterns...")
    for i, pattern in enumerate(patterns):
        embed_text = f"{pattern['name']}: {pattern['narrative']}"
        pattern["narrative_embedding"] = await embed(embed_text)
        print(f"  [{i+1}/{len(patterns)}] {pattern['pattern_id']} embedded")

    result = await collection.insert_many(patterns)
    print(f"[OK] Seeded {len(result.inserted_ids)} failure patterns with embeddings")

    # Create indexes
    await collection.create_index("pattern_id", unique=True)
    await collection.create_index("category")
    await collection.create_index([("stage_month_min", 1), ("stage_month_max", 1)])
    print("[OK] Indexes created")

    await close()


if __name__ == "__main__":
    asyncio.run(seed_patterns())
