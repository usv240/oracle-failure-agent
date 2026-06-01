"""
Patch existing failure_patterns in MongoDB with `transitions` data.

This is a one-time migration — it does NOT re-seed or touch embeddings.
Run from the project root:
    python -m backend.db.patch_transitions

The transition graph models 6 real-world failure cascade chains:
  Chain 1: PMF issues → premature scaling → burn crisis → team collapse
  Chain 2: Unit economics decay → discount addiction → negative NRR → runway collapse
  Chain 3: Team dysfunction → talent exodus → technical debt → shutdown
  Chain 4: Growth plateau → distribution failure → PMF reboot → pivot failure
  Chain 5: Fundraising traps → bridge round spiral → valuation overhang
  Chain 6: Platform / regulatory blindsides → competitor entry → shutdown
"""

import asyncio
import logging
from backend.db.connection import get_db, close

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Transition graph
# Each key is a pattern_id whose document will receive a `transitions` array.
# trigger_metric must be one of the MetricsInput field names or a derived key
# supported by cascade.py: runway_months, churn_rate, burn_multiple,
# ltv_cac_ratio, nps, headcount, mrr_growth_rate.
# ---------------------------------------------------------------------------

TRANSITIONS: dict[str, list[dict]] = {

    # ── F-001  Premature Scaling with Hidden Churn ────────────────────────────
    "F-001": [
        {
            "to_pattern_id": "F-017",
            "probability": 0.72,
            "avg_days": 45,
            "trigger_metric": "runway_months",
            "trigger_threshold": 6.0,
            "trigger_direction": "below",
            "trigger_condition": "runway_months < 6",
            "mechanism": "Premature headcount growth depletes cash before revenue catches up — runway falls below 6 months.",
            "observed_count": 0,
            "initial_probability": 0.72,
        },
        {
            "to_pattern_id": "F-054",
            "probability": 0.58,
            "avg_days": 30,
            "trigger_metric": "burn_multiple",
            "trigger_threshold": 3.0,
            "trigger_direction": "above",
            "trigger_condition": "burn_multiple > 3×",
            "mechanism": "Unsustainable burn signals instability — A-players leave for safer companies.",
            "observed_count": 0,
            "initial_probability": 0.58,
        },
        {
            "to_pattern_id": "F-007",
            "probability": 0.65,
            "avg_days": 60,
            "trigger_metric": "runway_months",
            "trigger_threshold": 9.0,
            "trigger_direction": "below",
            "trigger_condition": "runway_months < 9",
            "mechanism": "Scale-up burn erodes cash cushion, forcing a bridge round at a disadvantaged valuation.",
            "observed_count": 0,
            "initial_probability": 0.65,
        },
    ],

    # ── F-002  Runway Optimism Bias ───────────────────────────────────────────
    "F-002": [
        {
            "to_pattern_id": "F-007",
            "probability": 0.78,
            "avg_days": 60,
            "trigger_metric": "runway_months",
            "trigger_threshold": 6.0,
            "trigger_direction": "below",
            "trigger_condition": "runway_months < 6",
            "mechanism": "Founders delay fundraising because they overestimate conversion rate — by the time they start, runway is critical.",
            "observed_count": 0,
            "initial_probability": 0.78,
        },
        {
            "to_pattern_id": "F-038",
            "probability": 0.52,
            "avg_days": 90,
            "trigger_metric": "runway_months",
            "trigger_threshold": 9.0,
            "trigger_direction": "below",
            "trigger_condition": "runway_months < 9",
            "mechanism": "Late fundraising under duress → accepting unfavourable terms that create valuation overhang.",
            "observed_count": 0,
            "initial_probability": 0.52,
        },
    ],

    # ── F-003  Product-Market Fit Mirage ──────────────────────────────────────
    "F-003": [
        {
            "to_pattern_id": "F-016",
            "probability": 0.70,
            "avg_days": 45,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.08,
            "trigger_direction": "above",
            "trigger_condition": "churn_rate > 8%",
            "mechanism": "Hidden PMF gap surfaces as churn — distribution investment amplifies the signal into a retention crisis.",
            "observed_count": 0,
            "initial_probability": 0.70,
        },
        {
            "to_pattern_id": "F-037",
            "probability": 0.62,
            "avg_days": 30,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.05,
            "trigger_direction": "below",
            "trigger_condition": "mrr_growth_rate < 5%/mo",
            "mechanism": "Founder hires sales team to force growth that product cannot sustain — accelerating burn without fixing retention.",
            "observed_count": 0,
            "initial_probability": 0.62,
        },
        {
            "to_pattern_id": "F-013",
            "probability": 0.55,
            "avg_days": 60,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.10,
            "trigger_direction": "above",
            "trigger_condition": "churn_rate > 10%",
            "mechanism": "Mirage customers acquired early begin churning at scale, flipping net revenue retention negative.",
            "observed_count": 0,
            "initial_probability": 0.55,
        },
    ],

    # ── F-004  CAC Exceeds LTV at Scale ──────────────────────────────────────
    "F-004": [
        {
            "to_pattern_id": "F-041",
            "probability": 0.66,
            "avg_days": 30,
            "trigger_metric": "ltv_cac_ratio",
            "trigger_threshold": 1.5,
            "trigger_direction": "below",
            "trigger_condition": "ltv_cac_ratio < 1.5×",
            "mechanism": "Sales team compensates for weak unit economics by offering discounts — eroding LTV further.",
            "observed_count": 0,
            "initial_probability": 0.66,
        },
        {
            "to_pattern_id": "F-017",
            "probability": 0.68,
            "avg_days": 45,
            "trigger_metric": "ltv_cac_ratio",
            "trigger_threshold": 1.0,
            "trigger_direction": "below",
            "trigger_condition": "ltv_cac_ratio < 1×",
            "mechanism": "Negative unit economics at scale directly inflates burn multiple — cash consumed per dollar of growth becomes unsustainable.",
            "observed_count": 0,
            "initial_probability": 0.68,
        },
        {
            "to_pattern_id": "F-007",
            "probability": 0.55,
            "avg_days": 90,
            "trigger_metric": "runway_months",
            "trigger_threshold": 9.0,
            "trigger_direction": "below",
            "trigger_condition": "runway_months < 9",
            "mechanism": "Burning cash to acquire unprofitable customers collapses runway, forcing an emergency fundraise.",
            "observed_count": 0,
            "initial_probability": 0.55,
        },
    ],

    # ── F-005  Co-Founder Conflict at Inflection ──────────────────────────────
    "F-005": [
        {
            "to_pattern_id": "F-022",
            "probability": 0.65,
            "avg_days": 45,
            "trigger_metric": "nps",
            "trigger_threshold": 20,
            "trigger_direction": "below",
            "trigger_condition": "nps < 20",
            "mechanism": "Co-founder conflict paralyses product decisions — NPS falls as team ships incrementally instead of solving core problems.",
            "observed_count": 0,
            "initial_probability": 0.65,
        },
        {
            "to_pattern_id": "F-034",
            "probability": 0.58,
            "avg_days": 60,
            "trigger_metric": "nps",
            "trigger_threshold": 15,
            "trigger_direction": "below",
            "trigger_condition": "nps < 15",
            "mechanism": "Unresolved conflict drains founder energy — burnout manifests as strategic inaction and missed milestones.",
            "observed_count": 0,
            "initial_probability": 0.58,
        },
    ],

    # ── F-007  Bridge Round Death Spiral ──────────────────────────────────────
    "F-007": [
        {
            "to_pattern_id": "F-038",
            "probability": 0.72,
            "avg_days": 45,
            "trigger_metric": "runway_months",
            "trigger_threshold": 3.0,
            "trigger_direction": "below",
            "trigger_condition": "runway_months < 3",
            "mechanism": "Bridge round buys time but not trajectory — next round comes at a fraction of the prior valuation, destroying option value.",
            "observed_count": 0,
            "initial_probability": 0.72,
        },
        {
            "to_pattern_id": "F-054",
            "probability": 0.65,
            "avg_days": 60,
            "trigger_metric": "runway_months",
            "trigger_threshold": 6.0,
            "trigger_direction": "below",
            "trigger_condition": "runway_months < 6",
            "mechanism": "News of emergency fundraise leaks — senior engineers exit before the runway cliff.",
            "observed_count": 0,
            "initial_probability": 0.65,
        },
    ],

    # ── F-011  Hiring Ahead of Revenue ────────────────────────────────────────
    "F-011": [
        {
            "to_pattern_id": "F-017",
            "probability": 0.75,
            "avg_days": 45,
            "trigger_metric": "burn_multiple",
            "trigger_threshold": 3.0,
            "trigger_direction": "above",
            "trigger_condition": "burn_multiple > 3×",
            "mechanism": "Headcount growth outpaces revenue — burn multiple spikes as payroll exceeds new ARR generated.",
            "observed_count": 0,
            "initial_probability": 0.75,
        },
        {
            "to_pattern_id": "F-001",
            "probability": 0.60,
            "avg_days": 30,
            "trigger_metric": "headcount",
            "trigger_threshold": 30,
            "trigger_direction": "above",
            "trigger_condition": "headcount > 30",
            "mechanism": "Hiring spree locks in operating costs before PMF is confirmed, creating premature scaling dynamics.",
            "observed_count": 0,
            "initial_probability": 0.60,
        },
        {
            "to_pattern_id": "F-007",
            "probability": 0.55,
            "avg_days": 75,
            "trigger_metric": "runway_months",
            "trigger_threshold": 9.0,
            "trigger_direction": "below",
            "trigger_condition": "runway_months < 9",
            "mechanism": "High headcount burn erodes runway faster than fundraising cadence — bridge round becomes necessary.",
            "observed_count": 0,
            "initial_probability": 0.55,
        },
    ],

    # ── F-013  Negative Net Revenue Retention ─────────────────────────────────
    "F-013": [
        {
            "to_pattern_id": "F-083",
            "probability": 0.75,
            "avg_days": 30,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.08,
            "trigger_direction": "above",
            "trigger_condition": "churn_rate > 8%",
            "mechanism": "Negative NRR compounds cohort by cohort — each new month's customers churn faster than earlier cohorts.",
            "observed_count": 0,
            "initial_probability": 0.75,
        },
        {
            "to_pattern_id": "F-017",
            "probability": 0.62,
            "avg_days": 60,
            "trigger_metric": "burn_multiple",
            "trigger_threshold": 4.0,
            "trigger_direction": "above",
            "trigger_condition": "burn_multiple > 4×",
            "mechanism": "Constant churn replacement burn with no expansion revenue drives burn multiple into danger zone.",
            "observed_count": 0,
            "initial_probability": 0.62,
        },
    ],

    # ── F-016  Distribution Without Retention ─────────────────────────────────
    "F-016": [
        {
            "to_pattern_id": "F-013",
            "probability": 0.68,
            "avg_days": 45,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.08,
            "trigger_direction": "above",
            "trigger_condition": "churn_rate > 8%",
            "mechanism": "Top-of-funnel growth fills the bucket while churn empties it — net retention goes negative.",
            "observed_count": 0,
            "initial_probability": 0.68,
        },
        {
            "to_pattern_id": "F-085",
            "probability": 0.55,
            "avg_days": 30,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.05,
            "trigger_direction": "below",
            "trigger_condition": "mrr_growth_rate < 5%/mo",
            "mechanism": "Marketing spend increases to offset churn, burning cash before PMF is validated.",
            "observed_count": 0,
            "initial_probability": 0.55,
        },
    ],

    # ── F-017  Burn Multiple Death Spiral ─────────────────────────────────────
    "F-017": [
        {
            "to_pattern_id": "F-007",
            "probability": 0.78,
            "avg_days": 45,
            "trigger_metric": "runway_months",
            "trigger_threshold": 6.0,
            "trigger_direction": "below",
            "trigger_condition": "runway_months < 6",
            "mechanism": "Unsustainable burn collapses runway — company is forced into an emergency bridge round.",
            "observed_count": 0,
            "initial_probability": 0.78,
        },
        {
            "to_pattern_id": "F-054",
            "probability": 0.60,
            "avg_days": 30,
            "trigger_metric": "burn_multiple",
            "trigger_threshold": 5.0,
            "trigger_direction": "above",
            "trigger_condition": "burn_multiple > 5×",
            "mechanism": "Extreme burn multiple signals existential risk — senior talent exits as equity value evaporates.",
            "observed_count": 0,
            "initial_probability": 0.60,
        },
    ],

    # ── F-026  Overfunded Paralysis ───────────────────────────────────────────
    "F-026": [
        {
            "to_pattern_id": "F-001",
            "probability": 0.70,
            "avg_days": 60,
            "trigger_metric": "headcount",
            "trigger_threshold": 40,
            "trigger_direction": "above",
            "trigger_condition": "headcount > 40",
            "mechanism": "Excess capital deployed into headcount before clear product-market fit — classic premature scaling.",
            "observed_count": 0,
            "initial_probability": 0.70,
        },
        {
            "to_pattern_id": "F-044",
            "probability": 0.55,
            "avg_days": 90,
            "trigger_metric": "nps",
            "trigger_threshold": 20,
            "trigger_direction": "below",
            "trigger_condition": "nps < 20",
            "mechanism": "Large teams attract political hires — brilliant jerk tolerance grows with headcount.",
            "observed_count": 0,
            "initial_probability": 0.55,
        },
    ],

    # ── F-034  Founder Burnout Spiral ─────────────────────────────────────────
    "F-034": [
        {
            "to_pattern_id": "F-051",
            "probability": 0.62,
            "avg_days": 60,
            "trigger_metric": "nps",
            "trigger_threshold": 20,
            "trigger_direction": "below",
            "trigger_condition": "nps < 20",
            "mechanism": "Burned-out founder cannot lead the CEO evolution — operational gaps compound and NPS reflects a rudderless product.",
            "observed_count": 0,
            "initial_probability": 0.62,
        },
        {
            "to_pattern_id": "F-054",
            "probability": 0.55,
            "avg_days": 45,
            "trigger_metric": "nps",
            "trigger_threshold": 15,
            "trigger_direction": "below",
            "trigger_condition": "nps < 15",
            "mechanism": "Founder disengagement is visible to the team — top performers leave first.",
            "observed_count": 0,
            "initial_probability": 0.55,
        },
    ],

    # ── F-037  Sales Team Before Product-Market Fit ───────────────────────────
    "F-037": [
        {
            "to_pattern_id": "F-003",
            "probability": 0.70,
            "avg_days": 30,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.05,
            "trigger_direction": "below",
            "trigger_condition": "mrr_growth_rate < 5%/mo",
            "mechanism": "Sales force cannot generate pipeline without a compelling product — low growth exposes the PMF gap.",
            "observed_count": 0,
            "initial_probability": 0.70,
        },
        {
            "to_pattern_id": "F-017",
            "probability": 0.65,
            "avg_days": 45,
            "trigger_metric": "burn_multiple",
            "trigger_threshold": 3.0,
            "trigger_direction": "above",
            "trigger_condition": "burn_multiple > 3×",
            "mechanism": "High sales payroll against low output drives burn multiple into danger — each new dollar of ARR costs $3+ to generate.",
            "observed_count": 0,
            "initial_probability": 0.65,
        },
    ],

    # ── F-038  Valuation Overhang Trap ────────────────────────────────────────
    "F-038": [
        {
            "to_pattern_id": "F-054",
            "probability": 0.65,
            "avg_days": 60,
            "trigger_metric": "nps",
            "trigger_threshold": 20,
            "trigger_direction": "below",
            "trigger_condition": "nps < 20",
            "mechanism": "Down-round or flat-round demoralises team — equity value destruction triggers key employee departures.",
            "observed_count": 0,
            "initial_probability": 0.65,
        },
        {
            "to_pattern_id": "F-007",
            "probability": 0.55,
            "avg_days": 90,
            "trigger_metric": "runway_months",
            "trigger_threshold": 6.0,
            "trigger_direction": "below",
            "trigger_condition": "runway_months < 6",
            "mechanism": "Overhang makes new investors reluctant — company is forced into another bridge to buy time.",
            "observed_count": 0,
            "initial_probability": 0.55,
        },
    ],

    # ── F-041  Discount Addiction ──────────────────────────────────────────────
    "F-041": [
        {
            "to_pattern_id": "F-013",
            "probability": 0.68,
            "avg_days": 45,
            "trigger_metric": "ltv_cac_ratio",
            "trigger_threshold": 1.0,
            "trigger_direction": "below",
            "trigger_condition": "ltv_cac_ratio < 1×",
            "mechanism": "Discounts compress contract value while CAC remains high — LTV:CAC crosses below 1× and net retention goes negative.",
            "observed_count": 0,
            "initial_probability": 0.68,
        },
        {
            "to_pattern_id": "F-004",
            "probability": 0.60,
            "avg_days": 60,
            "trigger_metric": "ltv_cac_ratio",
            "trigger_threshold": 1.5,
            "trigger_direction": "below",
            "trigger_condition": "ltv_cac_ratio < 1.5×",
            "mechanism": "Systematic discounting erodes LTV at scale — the unit economics problem becomes structural, not tactical.",
            "observed_count": 0,
            "initial_probability": 0.60,
        },
    ],

    # ── F-051  Founder-to-CEO Transition Failure ──────────────────────────────
    "F-051": [
        {
            "to_pattern_id": "F-054",
            "probability": 0.72,
            "avg_days": 45,
            "trigger_metric": "nps",
            "trigger_threshold": 15,
            "trigger_direction": "below",
            "trigger_condition": "nps < 15",
            "mechanism": "Leadership vacuum during transition — VP-level hires leave when they see no clear accountability structure.",
            "observed_count": 0,
            "initial_probability": 0.72,
        },
        {
            "to_pattern_id": "F-034",
            "probability": 0.55,
            "avg_days": 30,
            "trigger_metric": "nps",
            "trigger_threshold": 20,
            "trigger_direction": "below",
            "trigger_condition": "nps < 20",
            "mechanism": "Failed transition throws founder back into execution mode — burnout accelerates from doing both jobs.",
            "observed_count": 0,
            "initial_probability": 0.55,
        },
    ],

    # ── F-053  Product-Led Growth Stall ──────────────────────────────────────
    "F-053": [
        {
            "to_pattern_id": "F-016",
            "probability": 0.65,
            "avg_days": 45,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.08,
            "trigger_direction": "above",
            "trigger_condition": "churn_rate > 8%",
            "mechanism": "PLG stall reveals the product cannot retain users without a sales motion — distribution without retention emerges.",
            "observed_count": 0,
            "initial_probability": 0.65,
        },
        {
            "to_pattern_id": "F-039",
            "probability": 0.58,
            "avg_days": 30,
            "trigger_metric": "mrr_growth_rate",
            "trigger_threshold": 0.05,
            "trigger_direction": "below",
            "trigger_condition": "mrr_growth_rate < 5%/mo",
            "mechanism": "Stalled PLG loop misdiagnosed — team increases acquisition spend instead of fixing the activation funnel.",
            "observed_count": 0,
            "initial_probability": 0.58,
        },
    ],

    # ── F-054  Talent Density Collapse ────────────────────────────────────────
    "F-054": [
        {
            "to_pattern_id": "F-034",
            "probability": 0.62,
            "avg_days": 30,
            "trigger_metric": "nps",
            "trigger_threshold": 20,
            "trigger_direction": "below",
            "trigger_condition": "nps < 20",
            "mechanism": "Loss of senior engineers leaves founders executing hands-on — overload accelerates burnout.",
            "observed_count": 0,
            "initial_probability": 0.62,
        },
        {
            "to_pattern_id": "F-019",
            "probability": 0.55,
            "avg_days": 60,
            "trigger_metric": "nps",
            "trigger_threshold": 15,
            "trigger_direction": "below",
            "trigger_condition": "nps < 15",
            "mechanism": "Reduced engineering capacity means technical debt accumulates unchecked — velocity collapses.",
            "observed_count": 0,
            "initial_probability": 0.55,
        },
    ],

    # ── F-083  Cohort Decay Acceleration ──────────────────────────────────────
    "F-083": [
        {
            "to_pattern_id": "F-013",
            "probability": 0.75,
            "avg_days": 30,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.10,
            "trigger_direction": "above",
            "trigger_condition": "churn_rate > 10%",
            "mechanism": "Accelerating cohort decay crosses the 10% monthly churn threshold — net revenue retention flips negative.",
            "observed_count": 0,
            "initial_probability": 0.75,
        },
        {
            "to_pattern_id": "F-017",
            "probability": 0.60,
            "avg_days": 60,
            "trigger_metric": "burn_multiple",
            "trigger_threshold": 4.0,
            "trigger_direction": "above",
            "trigger_condition": "burn_multiple > 4×",
            "mechanism": "High churn forces constant re-acquisition — burn multiple spikes as growth requires exponentially more spend.",
            "observed_count": 0,
            "initial_probability": 0.60,
        },
    ],

    # ── F-085  Marketing Before PMF ───────────────────────────────────────────
    "F-085": [
        {
            "to_pattern_id": "F-003",
            "probability": 0.68,
            "avg_days": 30,
            "trigger_metric": "churn_rate",
            "trigger_threshold": 0.08,
            "trigger_direction": "above",
            "trigger_condition": "churn_rate > 8%",
            "mechanism": "Paid acquisition fills the funnel with mismatched users who churn fast — confirming the PMF was a mirage.",
            "observed_count": 0,
            "initial_probability": 0.68,
        },
        {
            "to_pattern_id": "F-017",
            "probability": 0.60,
            "avg_days": 45,
            "trigger_metric": "burn_multiple",
            "trigger_threshold": 3.0,
            "trigger_direction": "above",
            "trigger_condition": "burn_multiple > 3×",
            "mechanism": "Marketing spend pre-PMF produces expensive, low-quality customers — burn multiple spikes.",
            "observed_count": 0,
            "initial_probability": 0.60,
        },
    ],

}


async def patch():
    db = get_db()
    collection = db["failure_patterns"]

    patched = 0
    skipped = 0
    errors = 0

    for pattern_id, transitions in TRANSITIONS.items():
        try:
            result = await collection.update_one(
                {"pattern_id": pattern_id},
                {
                    "$set": {
                        "transitions": transitions,
                        "times_triggered": 0,
                    }
                },
            )
            if result.matched_count == 0:
                log.warning("  SKIP — pattern %s not found in collection", pattern_id)
                skipped += 1
            elif result.modified_count == 0:
                log.info("  NOOP — %s already has transitions (no change)", pattern_id)
            else:
                log.info("  PATCHED %s — %d transitions", pattern_id, len(transitions))
                patched += 1
        except Exception as e:
            log.error("  ERROR patching %s: %s", pattern_id, e)
            errors += 1

    # Patterns without transitions should at least have times_triggered = 0
    # so the cascade counter $inc doesn't fail
    no_trans_result = await collection.update_many(
        {"transitions": {"$exists": False}},
        {"$set": {"transitions": [], "times_triggered": 0}},
    )
    log.info(
        "  SET empty transitions on %d patterns that had none",
        no_trans_result.modified_count,
    )

    log.info(
        "\n[Done] Patched: %d  |  Skipped (not found): %d  |  Errors: %d",
        patched, skipped, errors,
    )
    await close()


if __name__ == "__main__":
    asyncio.run(patch())
