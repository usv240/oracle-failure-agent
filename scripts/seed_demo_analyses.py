"""
Seed demo analyses into startup_analyses for cohort intelligence.

Inserts a curated set of historical analyses so $bucket + $facet
cohort percentile has data to work with immediately.

Run: python scripts/seed_demo_analyses.py
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 30 representative analyses spanning B2B SaaS, Fintech, Consumer
# Covers a range of health outcomes for realistic cohort distribution
DEMO_ANALYSES = [
    # ── CRITICAL startups (oracle_score 5–25) ──────────────────────────
    {"startup_name": "Quibi",         "industry": "Consumer",  "current_month": 8,  "oracle_score": 8,  "alert": True,  "pattern_id": "F-003", "pattern_name": "Product-Market Fit Mirage",     "confidence": 0.95, "days_to_crisis": 45,  "churn_rate": 0.22, "runway_months": 8,  "survival_rate": 0.06},
    {"startup_name": "WeWork",        "industry": "Real Estate SaaS", "current_month": 22, "oracle_score": 11, "alert": True, "pattern_id": "F-001", "pattern_name": "Premature Scaling with Hidden Churn", "confidence": 0.91, "days_to_crisis": 30, "churn_rate": 0.16, "runway_months": 14, "survival_rate": 0.09},
    {"startup_name": "Theranos",      "industry": "Healthcare", "current_month": 36, "oracle_score": 5,  "alert": True,  "pattern_id": "F-083", "pattern_name": "Cohort Decay Acceleration",     "confidence": 0.90, "days_to_crisis": 20,  "churn_rate": 0.45, "runway_months": 4,  "survival_rate": 0.04},
    {"startup_name": "Homejoy",       "industry": "Marketplace","current_month": 18, "oracle_score": 12, "alert": True,  "pattern_id": "F-013", "pattern_name": "Negative NRR Death Spiral",    "confidence": 0.87, "days_to_crisis": 35,  "churn_rate": 0.28, "runway_months": 6,  "survival_rate": 0.07},
    {"startup_name": "Vine",          "industry": "Consumer",  "current_month": 14, "oracle_score": 15, "alert": True,  "pattern_id": "F-016", "pattern_name": "Distribution Without Retention","confidence": 0.84, "days_to_crisis": 50,  "churn_rate": 0.19, "runway_months": 9,  "survival_rate": 0.08},
    {"startup_name": "Jawbone",       "industry": "Hardware",  "current_month": 28, "oracle_score": 9,  "alert": True,  "pattern_id": "F-017", "pattern_name": "Burn Multiple Death Spiral",    "confidence": 0.89, "days_to_crisis": 25,  "churn_rate": 0.31, "runway_months": 5,  "survival_rate": 0.06},
    {"startup_name": "Juicero",       "industry": "Consumer",  "current_month": 10, "oracle_score": 7,  "alert": True,  "pattern_id": "F-004", "pattern_name": "CAC Exceeds LTV at Scale",     "confidence": 0.88, "days_to_crisis": 30,  "churn_rate": 0.38, "runway_months": 7,  "survival_rate": 0.05},
    {"startup_name": "Rdio",          "industry": "Consumer",  "current_month": 20, "oracle_score": 13, "alert": True,  "pattern_id": "F-012", "pattern_name": "Well-Funded Competitor Entry", "confidence": 0.83, "days_to_crisis": 60,  "churn_rate": 0.21, "runway_months": 10, "survival_rate": 0.08},

    # ── HIGH RISK startups (oracle_score 26–45) ─────────────────────────
    {"startup_name": "Fab.com",       "industry": "E-Commerce","current_month": 16, "oracle_score": 28, "alert": True,  "pattern_id": "F-041", "pattern_name": "Discount Addiction",           "confidence": 0.74, "days_to_crisis": 75,  "churn_rate": 0.14, "runway_months": 11, "survival_rate": 0.12},
    {"startup_name": "Yik Yak",       "industry": "Consumer",  "current_month": 12, "oracle_score": 31, "alert": True,  "pattern_id": "F-031", "pattern_name": "Engineering Velocity Collapse","confidence": 0.72, "days_to_crisis": 80,  "churn_rate": 0.12, "runway_months": 13, "survival_rate": 0.14},
    {"startup_name": "Pebble",        "industry": "Hardware",  "current_month": 24, "oracle_score": 34, "alert": True,  "pattern_id": "F-007", "pattern_name": "Bridge Round Death Spiral",    "confidence": 0.71, "days_to_crisis": 90,  "churn_rate": 0.10, "runway_months": 7,  "survival_rate": 0.15},
    {"startup_name": "AcmeSaaS",      "industry": "B2B SaaS",  "current_month": 12, "oracle_score": 36, "alert": True,  "pattern_id": "F-001", "pattern_name": "Premature Scaling with Hidden Churn", "confidence": 0.68, "days_to_crisis": 90, "churn_rate": 0.09, "runway_months": 9, "survival_rate": 0.09},
    {"startup_name": "FinStartup Co", "industry": "Fintech",   "current_month": 14, "oracle_score": 38, "alert": True,  "pattern_id": "F-002", "pattern_name": "Runway Optimism Bias",         "confidence": 0.66, "days_to_crisis": 95,  "churn_rate": 0.08, "runway_months": 8,  "survival_rate": 0.14},
    {"startup_name": "CloudOps Pro",  "industry": "B2B SaaS",  "current_month": 18, "oracle_score": 42, "alert": True,  "pattern_id": "F-011", "pattern_name": "Hiring Ahead of Revenue",      "confidence": 0.65, "days_to_crisis": 100, "churn_rate": 0.07, "runway_months": 10, "survival_rate": 0.16},
    {"startup_name": "HealthAI Inc",  "industry": "Healthcare","current_month": 10, "oracle_score": 44, "alert": True,  "pattern_id": "F-054", "pattern_name": "Talent Density Collapse",      "confidence": 0.63, "days_to_crisis": 105, "churn_rate": 0.06, "runway_months": 12, "survival_rate": 0.18},

    # ── WATCH / MODERATE startups (oracle_score 46–65) ──────────────────
    {"startup_name": "GrowthTech",   "industry": "B2B SaaS",  "current_month": 15, "oracle_score": 48, "alert": False, "churn_rate": 0.06, "runway_months": 14, "survival_rate": None},
    {"startup_name": "PayFlow",      "industry": "Fintech",   "current_month": 11, "oracle_score": 52, "alert": False, "churn_rate": 0.05, "runway_months": 16, "survival_rate": None},
    {"startup_name": "DataCore",     "industry": "B2B SaaS",  "current_month": 13, "oracle_score": 55, "alert": False, "churn_rate": 0.05, "runway_months": 15, "survival_rate": None},
    {"startup_name": "MedTrack",     "industry": "Healthcare","current_month": 9,  "oracle_score": 58, "alert": False, "churn_rate": 0.04, "runway_months": 18, "survival_rate": None},
    {"startup_name": "RetailAI",     "industry": "E-Commerce","current_month": 16, "oracle_score": 61, "alert": False, "churn_rate": 0.04, "runway_months": 20, "survival_rate": None},

    # ── HEALTHY startups (oracle_score 66–100) ───────────────────────────
    {"startup_name": "Notion",       "industry": "B2B SaaS",  "current_month": 14, "oracle_score": 74, "alert": False, "churn_rate": 0.02, "runway_months": 24, "survival_rate": None},
    {"startup_name": "Stripe",       "industry": "Fintech",   "current_month": 20, "oracle_score": 89, "alert": False, "churn_rate": 0.01, "runway_months": 36, "survival_rate": None},
    {"startup_name": "Figma",        "industry": "B2B SaaS",  "current_month": 18, "oracle_score": 82, "alert": False, "churn_rate": 0.02, "runway_months": 30, "survival_rate": None},
    {"startup_name": "Linear",       "industry": "B2B SaaS",  "current_month": 12, "oracle_score": 77, "alert": False, "churn_rate": 0.02, "runway_months": 22, "survival_rate": None},
    {"startup_name": "Vercel",       "industry": "B2B SaaS",  "current_month": 16, "oracle_score": 85, "alert": False, "churn_rate": 0.01, "runway_months": 28, "survival_rate": None},
    {"startup_name": "Plaid",        "industry": "Fintech",   "current_month": 22, "oracle_score": 88, "alert": False, "churn_rate": 0.01, "runway_months": 32, "survival_rate": None},
    {"startup_name": "Scale AI",     "industry": "B2B SaaS",  "current_month": 15, "oracle_score": 79, "alert": False, "churn_rate": 0.02, "runway_months": 26, "survival_rate": None},
    {"startup_name": "Airtable",     "industry": "B2B SaaS",  "current_month": 11, "oracle_score": 72, "alert": False, "churn_rate": 0.03, "runway_months": 21, "survival_rate": None},
    {"startup_name": "Loom",         "industry": "B2B SaaS",  "current_month": 13, "oracle_score": 68, "alert": False, "churn_rate": 0.03, "runway_months": 19, "survival_rate": None},
    {"startup_name": "Miro",         "industry": "B2B SaaS",  "current_month": 17, "oracle_score": 81, "alert": False, "churn_rate": 0.02, "runway_months": 25, "survival_rate": None},
]


async def seed():
    conn = os.getenv("MONGODB_URI") or os.getenv("MDB_MCP_CONNECTION_STRING")
    if not conn:
        raise SystemExit("MONGODB_URI / MDB_MCP_CONNECTION_STRING not set")

    client = AsyncIOMotorClient(conn)
    db = client["oracle_db"]
    coll = db["startup_analyses"]

    inserted = 0
    skipped = 0
    now = datetime.utcnow()

    for i, analysis in enumerate(DEMO_ANALYSES):
        # Spread analyses over the last 90 days for realistic time distribution
        checked_at = now - timedelta(days=90 - i * 3)

        doc = {
            "startup_name": analysis["startup_name"],
            "industry": analysis["industry"],
            "current_month": analysis["current_month"],
            "oracle_score": analysis["oracle_score"],
            "alert": analysis["alert"],
            "checked_at": checked_at,
            "churn_rate": analysis.get("churn_rate"),
            "runway_months": analysis.get("runway_months"),
            "survival_rate": analysis.get("survival_rate"),
            "confidence": analysis.get("confidence"),
            "days_to_crisis": analysis.get("days_to_crisis"),
            "pattern_id": analysis.get("pattern_id"),
            "pattern_name": analysis.get("pattern_name"),
            "source": "seed",
        }

        # Upsert to avoid duplicates on re-run
        result = await coll.update_one(
            {"startup_name": analysis["startup_name"], "source": "seed"},
            {"$setOnInsert": doc},
            upsert=True,
        )
        if result.upserted_id:
            logger.info("[seed] %-20s → inserted (score=%d, alert=%s)",
                        analysis["startup_name"], analysis["oracle_score"], analysis["alert"])
            inserted += 1
        else:
            logger.info("[seed] %-20s → already exists, skip", analysis["startup_name"])
            skipped += 1

    logger.info("[seed] Done — %d inserted, %d skipped", inserted, skipped)
    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
