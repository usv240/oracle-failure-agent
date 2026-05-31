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

    # Generate embeddings using Voyage AI batch API to stay within free-tier limits:
    # 3 RPM + 10K TPM → batch 30 patterns per call, 65s sleep between batches
    print(f"Generating embeddings for {len(patterns)} patterns via Voyage AI (batched)...")
    from backend.config import settings
    batch_size = 30

    if settings.VOYAGE_API_KEY:
        import voyageai
        import time
        vo = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)
        batches = [patterns[i:i+batch_size] for i in range(0, len(patterns), batch_size)]

        for b_idx, batch in enumerate(batches):
            if b_idx > 0:
                print(f"  [Rate limit] Waiting 65s before next batch...")
                await asyncio.sleep(65)
            texts = [f"{p['name']}: {p['narrative']}" for p in batch]
            try:
                result = await vo.embed(texts=texts, model=settings.VOYAGE_MODEL, input_type="document")
                for p, emb in zip(batch, result.embeddings):
                    p["narrative_embedding"] = emb
                start = b_idx * batch_size
                print(f"  [Voyage AI] Batch {b_idx+1}/{len(batches)}: F-{start+1:03d}–F-{start+len(batch):03d} embedded (1024-dim)")
            except Exception as e:
                print(f"  [Voyage AI] Batch {b_idx+1} failed ({e}), falling back to text-embedding-004")
                for i, p in enumerate(batch):
                    embed_text = f"{p['name']}: {p['narrative']}"
                    p["narrative_embedding"] = await embed(embed_text, input_type="document")
                    print(f"    [{b_idx*batch_size+i+1}/{len(patterns)}] {p['pattern_id']} embedded (1024-dim)")
    else:
        for i, pattern in enumerate(patterns):
            embed_text = f"{pattern['name']}: {pattern['narrative']}"
            pattern["narrative_embedding"] = await embed(embed_text, input_type="document")
            print(f"  [{i+1}/{len(patterns)}] {pattern['pattern_id']} embedded")

    result = await collection.insert_many(patterns)
    print(f"[OK] Seeded {len(result.inserted_ids)} failure patterns with embeddings")

    # Indexes on failure_patterns
    await collection.create_index("pattern_id", unique=True)
    await collection.create_index("category")
    await collection.create_index([("stage_month_min", 1), ("stage_month_max", 1)])
    print("[OK] failure_patterns indexes created")

    # Indexes on watched_startups (monitoring)
    watched = db["watched_startups"]
    await watched.create_index("startup_name", unique=True)
    await watched.create_index([("watching", 1), ("last_checked", 1)])
    print("[OK] watched_startups indexes created")

    # Indexes on startup_analyses (session memory)
    analyses = db["startup_analyses"]
    await analyses.create_index([("startup_name", 1), ("checked_at", -1)])
    await analyses.create_index("checked_at")
    print("[OK] startup_analyses indexes created")

    await close()


if __name__ == "__main__":
    asyncio.run(seed_patterns())
