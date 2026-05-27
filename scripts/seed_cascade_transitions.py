"""
Seed failure cascade transition graph into MongoDB failure_patterns collection.

Each transition models a historically observed failure mode cascade:
  Pattern A (confidence ≥0.60) → Pattern B fires in avg_days days
  with trigger_condition based on specific metric thresholds.

Run:  python scripts/seed_cascade_transitions.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Transition graph ──────────────────────────────────────────────────────────
# Each entry: (from_pattern_id, list_of_transitions)
# trigger_metric + trigger_threshold + trigger_direction encode the exact condition
# that moves a startup from pattern A to pattern B.
TRANSITIONS: dict[str, list[dict]] = {

    # ── Premature Scaling with Hidden Churn ───────────────────────────────────
    "F-001": [
        {
            "to_pattern_id": "F-017",
            "probability": 0.71,
            "avg_days": 45,
            "trigger_metric": "burn_multiple",
            "trigger_threshold": 3.0,
            "trigger_direction": "above",
            "mechanism": "Premature headcount growth drives burn past 3× net new MRR, triggering a death-spiral where each new hire requires faster growth to justify, which requires more hires.",
        },
        {
            "to_pattern_id": "F-054",
            "probability": 0.58,
            "avg_days": 60,
            "trigger_metric": "headcount",
            "trigger_threshold": 20,
            "trigger_direction": "above",
            "mechanism": "Rapid scaling dilutes culture and talent density — wrong hires at speed become entrenched before the problem is visible.",
        },
        {
            "to_pattern_id": "F-007",
            "probability": 0.63,
            "avg_days": 90,
            "trigger_metric": "runway_months",
            "trigger_threshold": 6,
            "trigger_direction": "below",
            "mechanism": "Cash consumed by premature scale forces emergency bridge round, often at punishing dilution and with board-imposed constraints.",
        },
    ],

    # ── Burn Multiple Death Spiral ────────────────────────────────────────────
    "F-017": [
        {
            "to_pattern_id": "F-007",
            "probability": 0.77,
            "avg_days": 45,
            "trigger_metric": "runway_months",
            "trigger_threshold": 5,
            "trigger_direction": "below",
            "mechanism": "High burn multiple rapidly consumes runway below 5 months, forcing a distressed bridge round with unfavorable terms.",
        },
        {
            "to_pattern_id": "F-054",
            "probability": 0.62,
            "avg_days": 30,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.10,
            "trigger_direction": "above",
            "mechanism": "As layoff rumors circulate, top performers leave proactively — talent density collapses before any official restructuring.",
        },
        {
            "to_pattern_id": "F-034",
            "probability": 0.49,
            "avg_days": 75,
            "trigger_metric": "nps",
            "trigger_threshold": 20,
            "trigger_direction": "below",
            "mechanism": "Months of burn-rate crisis with no clear resolution erodes founder confidence — burnout spiral begins.",
        },
    ],

    # ── Product-Market Fit Mirage ─────────────────────────────────────────────
    "F-003": [
        {
            "to_pattern_id": "F-013",
            "probability": 0.74,
            "avg_days": 30,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.08,
            "trigger_direction": "above",
            "mechanism": "PMF mirage manifests first as expanding churn — customers who seemed enthusiastic stop renewing once the initial novelty fades.",
        },
        {
            "to_pattern_id": "F-017",
            "probability": 0.67,
            "avg_days": 60,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.05,
            "trigger_direction": "below",
            "mechanism": "Without real PMF, growth slows while burn continues — burn multiple explodes as the team thrashes for the right ICP.",
        },
        {
            "to_pattern_id": "F-006",
            "probability": 0.55,
            "avg_days": 90,
            "trigger_metric": "nps",
            "trigger_threshold": 15,
            "trigger_direction": "below",
            "mechanism": "Low NPS confirms lack of PMF — founders pivot without clear signal, wasting 3-6 months re-building.",
        },
    ],

    # ── Negative Net Revenue Retention ───────────────────────────────────────
    "F-013": [
        {
            "to_pattern_id": "F-017",
            "probability": 0.82,
            "avg_days": 30,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.12,
            "trigger_direction": "above",
            "mechanism": "Negative NRR means existing revenue base is shrinking — new ARR must just cover churn before it can drive growth, pushing burn multiple toward infinity.",
        },
        {
            "to_pattern_id": "F-007",
            "probability": 0.68,
            "avg_days": 60,
            "trigger_metric": "runway_months",
            "trigger_threshold": 6,
            "trigger_direction": "below",
            "mechanism": "Compounding revenue contraction accelerates runway burn — board demands emergency raise before metrics get worse.",
        },
        {
            "to_pattern_id": "F-034",
            "probability": 0.43,
            "avg_days": 90,
            "trigger_metric": "nps",
            "trigger_threshold": 10,
            "trigger_direction": "below",
            "mechanism": "Watching revenue evaporate despite team effort is a leading founder burnout trigger.",
        },
    ],

    # ── CAC Exceeds LTV at Scale ──────────────────────────────────────────────
    "F-004": [
        {
            "to_pattern_id": "F-017",
            "probability": 0.79,
            "avg_days": 30,
            "trigger_metric": "ltv_cac_ratio",
            "trigger_threshold": 1.0,
            "trigger_direction": "below",
            "mechanism": "LTV:CAC <1 means every acquired customer destroys value — burn multiple skyrockets as the acquisition machine compounds losses.",
        },
        {
            "to_pattern_id": "F-041",
            "probability": 0.64,
            "avg_days": 45,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.10,
            "trigger_direction": "above",
            "mechanism": "To compensate for poor unit economics, team resorts to discounting — which trains customers to wait for deals and permanently depresses LTV.",
        },
        {
            "to_pattern_id": "F-007",
            "probability": 0.58,
            "avg_days": 75,
            "trigger_metric": "runway_months",
            "trigger_threshold": 6,
            "trigger_direction": "below",
            "mechanism": "Burning capital acquiring customers at a loss collapses runway, forcing distressed fundraising.",
        },
    ],

    # ── Hiring Ahead of Revenue ───────────────────────────────────────────────
    "F-011": [
        {
            "to_pattern_id": "F-017",
            "probability": 0.73,
            "avg_days": 45,
            "trigger_metric": "burn_multiple",
            "trigger_threshold": 2.5,
            "trigger_direction": "above",
            "mechanism": "Salary costs from premature hires push burn multiple above 2.5×, and the new team hasn't had time to generate incremental revenue.",
        },
        {
            "to_pattern_id": "F-054",
            "probability": 0.61,
            "avg_days": 60,
            "trigger_metric": "headcount",
            "trigger_threshold": 15,
            "trigger_direction": "above",
            "mechanism": "Hiring fast before culture and processes are set introduces talent density collapse — velocity drops while costs rise.",
        },
        {
            "to_pattern_id": "F-066",
            "probability": 0.47,
            "avg_days": 90,
            "trigger_metric": "headcount",
            "trigger_threshold": 25,
            "trigger_direction": "above",
            "mechanism": "Late hires brought in at market rates create compensation disparity with early employees — two-tier compensation conflict follows.",
        },
    ],

    # ── Runway Optimism Bias ──────────────────────────────────────────────────
    "F-002": [
        {
            "to_pattern_id": "F-007",
            "probability": 0.72,
            "avg_days": 60,
            "trigger_metric": "runway_months",
            "trigger_threshold": 5,
            "trigger_direction": "below",
            "mechanism": "Optimism about fundraising timelines means teams act too slowly — by the time reality sets in, runway is already below 5 months.",
        },
        {
            "to_pattern_id": "F-064",
            "probability": 0.55,
            "avg_days": 90,
            "trigger_metric": "runway_months",
            "trigger_threshold": 3,
            "trigger_direction": "below",
            "mechanism": "Desperate for cash before zero, founders accept convertible notes from multiple sources — note stack creates cap table complexity.",
        },
        {
            "to_pattern_id": "F-034",
            "probability": 0.44,
            "avg_days": 75,
            "trigger_metric": "runway_months",
            "trigger_threshold": 4,
            "trigger_direction": "below",
            "mechanism": "Carrying false hope while secretly aware of looming death is a primary founder burnout catalyst.",
        },
    ],

    # ── Bridge Round Death Spiral ─────────────────────────────────────────────
    "F-007": [
        {
            "to_pattern_id": "F-064",
            "probability": 0.67,
            "avg_days": 60,
            "trigger_metric": "runway_months",
            "trigger_threshold": 3,
            "trigger_direction": "below",
            "mechanism": "When bridge terms disappoint, founders stack additional convertible notes — each note adds anti-dilution clauses that make the next raise harder.",
        },
        {
            "to_pattern_id": "F-051",
            "probability": 0.52,
            "avg_days": 45,
            "trigger_metric": "nps",
            "trigger_threshold": 20,
            "trigger_direction": "below",
            "mechanism": "Board pressure during a crisis round often forces a CEO-to-operator transition — founder loses control at the worst moment.",
        },
        {
            "to_pattern_id": "F-026",
            "probability": 0.41,
            "avg_days": 30,
            "trigger_metric": "runway_months",
            "trigger_threshold": 12,
            "trigger_direction": "above",
            "mechanism": "When bridge succeeds and buys time, the urgency that was forcing focus dissipates — overfunded paralysis sets in.",
        },
    ],

    # ── Talent Density Collapse ───────────────────────────────────────────────
    "F-054": [
        {
            "to_pattern_id": "F-031",
            "probability": 0.74,
            "avg_days": 30,
            "trigger_metric": "nps",
            "trigger_threshold": 25,
            "trigger_direction": "below",
            "mechanism": "Wrong hires shipping mediocre features destroys product quality — NPS drops as engineering velocity collapses.",
        },
        {
            "to_pattern_id": "F-034",
            "probability": 0.55,
            "avg_days": 60,
            "trigger_metric": "headcount",
            "trigger_threshold": 10,
            "trigger_direction": "above",
            "mechanism": "Founder forced to manage underperformers instead of building — executive context-switch leads to burnout.",
        },
        {
            "to_pattern_id": "F-005",
            "probability": 0.46,
            "avg_days": 75,
            "trigger_metric": "nps",
            "trigger_threshold": 20,
            "trigger_direction": "below",
            "mechanism": "Declining product quality forces co-founders to disagree on who to blame and what to cut — conflict at inflection.",
        },
    ],

    # ── Co-Founder Conflict at Inflection ────────────────────────────────────
    "F-005": [
        {
            "to_pattern_id": "F-051",
            "probability": 0.71,
            "avg_days": 45,
            "trigger_metric": "nps",
            "trigger_threshold": 25,
            "trigger_direction": "below",
            "mechanism": "Board intervenes during co-founder conflict — one founder forced into COO or departure, destabilising company.",
        },
        {
            "to_pattern_id": "F-034",
            "probability": 0.63,
            "avg_days": 30,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.05,
            "trigger_direction": "below",
            "mechanism": "Co-founder conflict drains energy — the remaining founder absorbs double workload, burnout follows.",
        },
        {
            "to_pattern_id": "F-022",
            "probability": 0.49,
            "avg_days": 60,
            "trigger_metric": "headcount",
            "trigger_threshold": 5,
            "trigger_direction": "below",
            "mechanism": "One co-founder's departure creates a knowledge gap around their domain — company has single point of failure.",
        },
    ],

    # ── Founder Burnout Spiral ────────────────────────────────────────────────
    "F-034": [
        {
            "to_pattern_id": "F-022",
            "probability": 0.71,
            "avg_days": 30,
            "trigger_metric": "nps",
            "trigger_threshold": 20,
            "trigger_direction": "below",
            "mechanism": "Burned-out founder holds all key relationships and decisions — when they become unavailable, single point of failure is exposed.",
        },
        {
            "to_pattern_id": "F-051",
            "probability": 0.58,
            "avg_days": 45,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.03,
            "trigger_direction": "below",
            "mechanism": "Board loses confidence in founder who is visibly struggling — leadership transition pressure builds.",
        },
        {
            "to_pattern_id": "F-006",
            "probability": 0.42,
            "avg_days": 60,
            "trigger_metric": "nps",
            "trigger_threshold": 15,
            "trigger_direction": "below",
            "mechanism": "Desperate to create momentum and escape burnout, founder makes a reactive pivot without PMF signal.",
        },
    ],

    # ── Engineering Velocity Collapse ─────────────────────────────────────────
    "F-031": [
        {
            "to_pattern_id": "F-043",
            "probability": 0.67,
            "avg_days": 30,
            "trigger_metric": "nps",
            "trigger_threshold": 25,
            "trigger_direction": "below",
            "mechanism": "Slow engineering means falling behind competitors — team adds features to match parity rather than building differentiation.",
        },
        {
            "to_pattern_id": "F-019",
            "probability": 0.74,
            "avg_days": 45,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.05,
            "trigger_direction": "below",
            "mechanism": "Shortcuts taken to ship fast accumulate as technical debt — collapse is exponential once debt interest exceeds velocity.",
        },
        {
            "to_pattern_id": "F-079",
            "probability": 0.51,
            "avg_days": 60,
            "trigger_metric": "headcount",
            "trigger_threshold": 10,
            "trigger_direction": "above",
            "mechanism": "Each new engineer added to a slow codebase makes it slower — complexity creep accelerates as architectural clarity degrades.",
        },
    ],

    # ── Distribution Without Retention ───────────────────────────────────────
    "F-016": [
        {
            "to_pattern_id": "F-013",
            "probability": 0.76,
            "avg_days": 30,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.10,
            "trigger_direction": "above",
            "mechanism": "Acquiring users without retention means the bucket is full of holes — NRR turns negative as the churned base grows.",
        },
        {
            "to_pattern_id": "F-017",
            "probability": 0.64,
            "avg_days": 60,
            "trigger_metric": "cac",
            "trigger_threshold": 2000,
            "trigger_direction": "above",
            "mechanism": "Retention failure forces ever-increasing spend on acquisition to replace churned users — CAC rises while LTV shrinks.",
        },
        {
            "to_pattern_id": "F-059",
            "probability": 0.47,
            "avg_days": 45,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.08,
            "trigger_direction": "below",
            "mechanism": "Team mistakes lack of retention for lack of awareness — doubles down on brand/top-of-funnel spend before fixing product.",
        },
    ],

    # ── Cohort Decay Acceleration ─────────────────────────────────────────────
    "F-083": [
        {
            "to_pattern_id": "F-013",
            "probability": 0.81,
            "avg_days": 30,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.12,
            "trigger_direction": "above",
            "mechanism": "Accelerating cohort decay directly produces negative NRR — each successive cohort churns faster than the previous.",
        },
        {
            "to_pattern_id": "F-017",
            "probability": 0.66,
            "avg_days": 45,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.05,
            "trigger_direction": "below",
            "mechanism": "Declining cohort health means new ARR barely offsets churn — gross new ARR looks fine but net is catastrophic.",
        },
        {
            "to_pattern_id": "F-007",
            "probability": 0.54,
            "avg_days": 75,
            "trigger_metric": "runway_months",
            "trigger_threshold": 6,
            "trigger_direction": "below",
            "mechanism": "Investors spot the cohort decay charts before the team acknowledges them — funding market closes, bridge required.",
        },
    ],

    # ── Well-Funded Competitor Entry ──────────────────────────────────────────
    "F-012": [
        {
            "to_pattern_id": "F-028",
            "probability": 0.69,
            "avg_days": 45,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.08,
            "trigger_direction": "below",
            "mechanism": "Well-funded competitor acquires pricing power — incumbent forced to match rates, triggering race-to-the-bottom pricing.",
        },
        {
            "to_pattern_id": "F-041",
            "probability": 0.61,
            "avg_days": 30,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.08,
            "trigger_direction": "above",
            "mechanism": "Customers evaluate the competitor — sales team offers discounts to retain them, cementing discount addiction.",
        },
        {
            "to_pattern_id": "F-017",
            "probability": 0.53,
            "avg_days": 60,
            "trigger_metric": "burn_multiple",
            "trigger_threshold": 2.5,
            "trigger_direction": "above",
            "mechanism": "Defensive spend (more sales, more marketing, more features) to fight the competitor drives burn multiple above sustainable levels.",
        },
    ],

    # ── Discount Addiction ────────────────────────────────────────────────────
    "F-041": [
        {
            "to_pattern_id": "F-004",
            "probability": 0.73,
            "avg_days": 30,
            "trigger_metric": "ltv_cac_ratio",
            "trigger_threshold": 1.5,
            "trigger_direction": "below",
            "mechanism": "Systematic discounting erodes LTV while CAC stays fixed — unit economics collapse faster than ARR numbers suggest.",
        },
        {
            "to_pattern_id": "F-017",
            "probability": 0.58,
            "avg_days": 60,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.06,
            "trigger_direction": "below",
            "mechanism": "Discount-trained customers wait for deals — pipeline conversion requires ever-larger discounts, compressing net revenue.",
        },
    ],

    # ── Convertible Note Stack Collapse ──────────────────────────────────────
    "F-064": [
        {
            "to_pattern_id": "F-038",
            "probability": 0.68,
            "avg_days": 60,
            "trigger_metric": "runway_months",
            "trigger_threshold": 4,
            "trigger_direction": "below",
            "mechanism": "Stacked notes with different valuation caps create a valuation overhang — institutional investors see an undilutable mess.",
        },
        {
            "to_pattern_id": "F-051",
            "probability": 0.52,
            "avg_days": 45,
            "trigger_metric": "nps",
            "trigger_threshold": 20,
            "trigger_direction": "below",
            "mechanism": "Note holders pressure for equity conversion or board seats — founder loses autonomy at the worst moment.",
        },
    ],

    # ── Marketing Before PMF ──────────────────────────────────────────────
    "F-085": [
        {
            "to_pattern_id": "F-003",
            "probability": 0.78,
            "avg_days": 30,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.10,
            "trigger_direction": "above",
            "mechanism": "Marketing spend acquires users who churn immediately — no PMF means money spent on top-of-funnel fills a leaky bucket, and churn explodes.",
        },
        {
            "to_pattern_id": "F-017",
            "probability": 0.65,
            "avg_days": 45,
            "trigger_metric": "burn_multiple",
            "trigger_threshold": 3.5,
            "trigger_direction": "above",
            "mechanism": "CAC paid before PMF means acquisition cost is never recovered — burn multiple spikes as the channel produces customers who won't renew.",
        },
        {
            "to_pattern_id": "F-004",
            "probability": 0.58,
            "avg_days": 60,
            "trigger_metric": "ltv_cac_ratio",
            "trigger_threshold": 1.0,
            "trigger_direction": "below",
            "mechanism": "Spending on marketing without product-market fit drives LTV:CAC below 1 — every acquired customer destroys unit economics.",
        },
    ],

    # ── Pivot Without Signal ──────────────────────────────────────────────
    "F-006": [
        {
            "to_pattern_id": "F-034",
            "probability": 0.72,
            "avg_days": 30,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.03,
            "trigger_direction": "below",
            "mechanism": "Pivot without clear signal forces the founding team to rebuild conviction from scratch — morale collapse and founder burnout often follow within a quarter.",
        },
        {
            "to_pattern_id": "F-003",
            "probability": 0.61,
            "avg_days": 60,
            "trigger_metric": "nps",
            "trigger_threshold": 15,
            "trigger_direction": "below",
            "mechanism": "Reactive pivots that discover a new market often find the same PMF problem in a different wrapper — churn pattern repeats.",
        },
        {
            "to_pattern_id": "F-017",
            "probability": 0.45,
            "avg_days": 90,
            "trigger_metric": "burn_multiple",
            "trigger_threshold": 4.0,
            "trigger_direction": "above",
            "mechanism": "Pivot rebuilding costs (new hires, new marketing, new product) drain cash while revenue is reset to near zero.",
        },
    ],

    # ── Technical Debt Accumulation Collapse ──────────────────────────────
    "F-019": [
        {
            "to_pattern_id": "F-031",
            "probability": 0.81,
            "avg_days": 30,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.05,
            "trigger_direction": "below",
            "mechanism": "Accumulated technical debt directly degrades engineering velocity — the team spends more time on maintenance than features.",
        },
        {
            "to_pattern_id": "F-054",
            "probability": 0.59,
            "avg_days": 45,
            "trigger_metric": "headcount",
            "trigger_threshold": 15,
            "trigger_direction": "above",
            "mechanism": "Senior engineers leave when the codebase becomes unworkable — talent density collapses as they're replaced by less experienced hires.",
        },
    ],

    # ── Key Person Single Point of Failure ────────────────────────────────
    "F-022": [
        {
            "to_pattern_id": "F-034",
            "probability": 0.76,
            "avg_days": 30,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.04,
            "trigger_direction": "below",
            "mechanism": "When the key person becomes unavailable (burnout, departure, illness), growth grinds to zero — all critical context was trapped in one person.",
        },
        {
            "to_pattern_id": "F-031",
            "probability": 0.56,
            "avg_days": 45,
            "trigger_metric": "nps",
            "trigger_threshold": 20,
            "trigger_direction": "below",
            "mechanism": "Knowledge gap from SPOF departure creates engineering velocity collapse — team can't maintain or extend critical systems.",
        },
    ],

    # ── Feature Parity Treadmill ───────────────────────────────────────────
    "F-043": [
        {
            "to_pattern_id": "F-031",
            "probability": 0.74,
            "avg_days": 30,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.05,
            "trigger_direction": "below",
            "mechanism": "Building to parity rather than differentiation drains engineering resources on catching up instead of leaping ahead — velocity collapses.",
        },
        {
            "to_pattern_id": "F-012",
            "probability": 0.62,
            "avg_days": 60,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.10,
            "trigger_direction": "above",
            "mechanism": "Competitor with more resources out-features you faster — customers defect when parity is never achieved.",
        },
    ],

    # ── Founder-to-CEO Transition Failure ────────────────────────────────
    "F-051": [
        {
            "to_pattern_id": "F-022",
            "probability": 0.69,
            "avg_days": 45,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.04,
            "trigger_direction": "below",
            "mechanism": "Founder sidelined during transition creates a knowledge SPOF — all customer relationships, technical context, and culture DNA were with the founder.",
        },
        {
            "to_pattern_id": "F-005",
            "probability": 0.55,
            "avg_days": 30,
            "trigger_metric": "nps",
            "trigger_threshold": 20,
            "trigger_direction": "below",
            "mechanism": "New CEO/COO dynamic creates co-founder tension — the deposed founder either leaves or stays and undermines the new structure.",
        },
    ],

    # ── Overfunded Paralysis ──────────────────────────────────────────────
    "F-026": [
        {
            "to_pattern_id": "F-001",
            "probability": 0.71,
            "avg_days": 60,
            "trigger_metric": "headcount",
            "trigger_threshold": 25,
            "trigger_direction": "above",
            "mechanism": "Excess capital removes urgency — team grows without discipline, hiring for prestige rather than leverage.",
        },
        {
            "to_pattern_id": "F-054",
            "probability": 0.58,
            "avg_days": 45,
            "trigger_metric": "headcount",
            "trigger_threshold": 20,
            "trigger_direction": "above",
            "mechanism": "Fast hiring with abundant cash leads to talent density collapse — wrong hires at speed become entrenched.",
        },
    ],

    # ── Race to the Bottom Pricing ────────────────────────────────────────
    "F-028": [
        {
            "to_pattern_id": "F-041",
            "probability": 0.77,
            "avg_days": 30,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.08,
            "trigger_direction": "above",
            "mechanism": "Price war forces aggressive discounting to prevent churn — discount addiction sets in as customers learn to negotiate.",
        },
        {
            "to_pattern_id": "F-013",
            "probability": 0.62,
            "avg_days": 45,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.05,
            "trigger_direction": "below",
            "mechanism": "Race to zero on pricing compresses ARR — net revenue retention turns negative as existing customers renegotiate down.",
        },
    ],
}


async def seed():
    conn = os.getenv("MONGODB_URI") or os.getenv("MDB_MCP_CONNECTION_STRING")
    if not conn:
        raise SystemExit("MONGODB_URI / MDB_MCP_CONNECTION_STRING not set")

    client = AsyncIOMotorClient(conn)
    db = client["oracle_db"]
    coll = db["failure_patterns"]

    total_updated = 0
    total_skipped = 0

    for pattern_id, transitions in TRANSITIONS.items():
        # Enrich each transition with observed_count + initial_probability for Bayesian updates
        enriched = []
        for t in transitions:
            enriched.append({
                **t,
                "observed_count": 0,
                "initial_probability": t["probability"],
                "last_observed": None,
            })

        result = await coll.update_one(
            {"pattern_id": pattern_id},
            {"$set": {"transitions": enriched}},
        )

        if result.matched_count:
            logger.info("[seed] %-8s → %d transitions written", pattern_id, len(enriched))
            total_updated += 1
        else:
            logger.warning("[seed] %-8s NOT FOUND — skipping", pattern_id)
            total_skipped += 1

    # Clear any stale transitions on patterns NOT in our seed (ensure clean slate)
    not_in_seed = [pid for pid in [] if pid not in TRANSITIONS]  # intentionally empty for safety
    logger.info("[seed] Done — %d patterns updated, %d not found", total_updated, total_skipped)
    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
