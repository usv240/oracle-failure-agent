"""
Read-only diagnostic: which (industry, month) cohorts actually have >=3 members?

Mirrors the exact filter in backend/routes/cascade.py cohort_intelligence:
  industry: regex (case-insensitive) substring match
  current_month: within +/-6 of the chosen month
  needs >= 3 to render (else empty state)

Run: python scripts/diag_cohorts.py
"""
import asyncio
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db.connection import get_db, close


async def main():
    db = get_db()
    coll = db["startup_analyses"]

    total = await coll.count_documents({})
    print(f"\nTotal docs in startup_analyses: {total}\n")

    # Pull just the fields we need
    docs = await coll.find(
        {}, {"industry": 1, "current_month": 1, "oracle_score": 1, "_id": 0}
    ).to_list(length=100000)

    # Group months by exact industry label
    by_industry = defaultdict(list)
    for d in docs:
        ind = d.get("industry")
        m = d.get("current_month")
        if ind is None or m is None:
            continue
        by_industry[ind].append(m)

    print("=== Per-industry month spread (exact labels) ===")
    for ind in sorted(by_industry, key=lambda k: -len(by_industry[k])):
        months = sorted(by_industry[ind])
        print(f"  {ind:24s} n={len(months):3d}  months={months}")

    print("\n=== Cohorts that RENDER (>=3 within month +/-6) ===")
    print("    (industry uses substring match, so labels can overlap)\n")
    industries = sorted(by_industry.keys())
    found_any = False
    for ind in industries:
        # all docs whose industry CONTAINS this label (substring, case-insensitive)
        matching_months = []
        for other_ind, months in by_industry.items():
            if ind.lower() in other_ind.lower():
                matching_months.extend(months)
        if not matching_months:
            continue
        # find center months (1..120) that capture >=3
        best = []
        lo, hi = min(matching_months), max(matching_months)
        for center in range(max(1, lo - 6), hi + 7):
            cnt = sum(1 for m in matching_months if center - 6 <= m <= center + 6)
            if cnt >= 3:
                best.append((center, cnt))
        if best:
            found_any = True
            # report the densest center and a clean recommended center
            densest = max(best, key=lambda x: x[1])
            centers = [c for c, _ in best]
            print(f"  {ind:24s} -> enter Month {densest[0]:2d}  "
                  f"(gives {densest[1]} in cohort) | any month in {min(centers)}-{max(centers)} works")
    if not found_any:
        print("  (none — not enough data in any cohort)")

    await close()


if __name__ == "__main__":
    asyncio.run(main())
