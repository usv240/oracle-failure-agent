"""
Failure Cascade Graph Service
==============================
Uses MongoDB $graphLookup to traverse the failure-mode state machine and
compute the full cascade chain from a detected pattern.

Also computes the Cascade Intervention Optimizer: given each transition's
trigger_condition, calculates the MINIMUM metric change needed to prevent
the cascade link from firing — specific numbers, not generic advice.

MongoDB features used:
  • $graphLookup          — graph traversal across failure_patterns
  • Motor ACID transactions — atomic write of intervention + telemetry + counter
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Optional

from backend.db.connection import get_db
from backend.db.schemas import MetricsInput

logger = logging.getLogger(__name__)

# ── Derived metric helpers ────────────────────────────────────────────────────

def _derived(metrics: MetricsInput) -> dict:
    """Compute derived metrics used in trigger conditions."""
    net_new_mrr = metrics.mrr * metrics.mrr_growth_rate
    burn_multiple = (metrics.burn_rate / net_new_mrr) if net_new_mrr > 0 else 99.0
    ltv_cac = (metrics.ltv / metrics.cac) if metrics.cac > 0 else 0.0
    return {
        "mrr": metrics.mrr,
        "mrr_growth_rate": metrics.mrr_growth_rate,
        "churn_rate": metrics.churn_rate,
        "burn_rate": metrics.burn_rate,
        "runway_months": metrics.runway_months,
        "headcount": metrics.headcount,
        "nps": metrics.nps,
        "cac": metrics.cac,
        "ltv": metrics.ltv,
        "burn_multiple": round(burn_multiple, 2),
        "ltv_cac_ratio": round(ltv_cac, 2),
    }


def _is_triggered(derived: dict, trigger_metric: str, threshold: float, direction: str) -> bool:
    """Check if a trigger condition is already met (i.e. the cascade link is hot)."""
    val = derived.get(trigger_metric)
    if val is None:
        return False
    if direction == "above":
        return val >= threshold
    else:
        return val <= threshold


def _days_until_trigger(
    derived: dict,
    trigger_metric: str,
    threshold: float,
    direction: str,
    avg_days: int,
) -> int:
    """
    Estimate how many days until the trigger fires, given current metrics.
    Uses a simple linear projection based on burn rate / growth rate.
    Falls back to avg_days from historical data.
    """
    val = derived.get(trigger_metric)
    if val is None:
        return avg_days

    if _is_triggered(derived, trigger_metric, threshold, direction):
        return 0  # Already triggered

    # Runway projection: runway_months decreases at ~1/month
    if trigger_metric == "runway_months" and direction == "below":
        months_to_threshold = val - threshold
        return max(1, int(months_to_threshold * 30))

    # Churn usually increases slowly — use avg_days as default
    return avg_days


# ── Intervention Optimizer ────────────────────────────────────────────────────

def compute_cascade_intervention(
    metrics: MetricsInput,
    transition: dict,
) -> dict | None:
    """
    Compute the MINIMUM metric change to prevent this cascade transition from firing.
    Returns a specific number, not generic advice.

    This is deterministic algebra on the trigger threshold, NOT an AI-generated recommendation.
    """
    derived = _derived(metrics)
    tm = transition.get("trigger_metric", "")
    threshold = float(transition.get("trigger_threshold", 0))
    direction = transition.get("trigger_direction", "below")
    avg_days = int(transition.get("avg_days", 60))
    safety_margin = 0.15  # 15% buffer above the trigger threshold

    # Already triggered — intervention is urgent
    already_triggered = _is_triggered(derived, tm, threshold, direction)
    urgency = "CRITICAL" if already_triggered else "WARNING"

    action: dict = {
        "trigger_metric": tm,
        "trigger_threshold": threshold,
        "current_value": derived.get(tm),
        "already_triggered": already_triggered,
        "urgency": urgency,
        "days_to_act": max(1, avg_days - 15),
    }

    # ── runway_months: need to stay above threshold ───────────────────────────
    if tm == "runway_months" and direction == "below":
        safe_target = threshold * (1 + safety_margin)
        current_runway = metrics.runway_months
        if current_runway >= safe_target and not already_triggered:
            action["action"] = "monitor"
            action["message"] = f"Runway ({current_runway:.1f}mo) above safe threshold ({safe_target:.1f}mo). Monitor monthly."
            return action

        # How much must burn_rate decrease to reach safe_target?
        # runway = cash / burn_rate → cash = runway * burn_rate (approx)
        # new_runway = cash / new_burn  →  new_burn = cash / safe_target
        current_cash_approx = current_runway * metrics.burn_rate
        new_burn = current_cash_approx / safe_target
        burn_reduction = metrics.burn_rate - new_burn
        # Headcount assuming $12k/person/month fully-loaded
        COST_PER_PERSON = 12_000
        headcount_reduction = math.ceil(burn_reduction / COST_PER_PERSON)

        action.update({
            "action": "reduce_burn",
            "target_value": round(safe_target, 1),
            "burn_reduction_needed": round(burn_reduction),
            "headcount_reduction": max(0, headcount_reduction),
            "message": (
                f"Reduce monthly burn by ${burn_reduction:,.0f} "
                f"(from ${metrics.burn_rate:,.0f} → ${new_burn:,.0f}) "
                f"to extend runway to {safe_target:.1f} months. "
                f"Minimum headcount change: −{headcount_reduction} people "
                f"(assuming ${COST_PER_PERSON:,}/person/month fully loaded)."
            ),
        })

    # ── churn_rate: need to stay below threshold ──────────────────────────────
    elif tm == "churn_rate" and direction == "above":
        safe_target = threshold * (1 - safety_margin)
        current_churn = metrics.churn_rate
        if current_churn <= safe_target and not already_triggered:
            action["action"] = "monitor"
            action["message"] = f"Churn ({current_churn*100:.1f}%) below danger threshold ({threshold*100:.1f}%). Monitor."
            return action

        churn_reduction = current_churn - safe_target
        # Estimated MRR recovery from fixing churn
        mrr_at_risk = metrics.mrr * churn_reduction
        action.update({
            "action": "reduce_churn",
            "target_value": round(safe_target, 3),
            "churn_reduction_needed": round(churn_reduction, 3),
            "mrr_at_risk_monthly": round(mrr_at_risk),
            "message": (
                f"Reduce monthly churn by {churn_reduction*100:.1f}pp "
                f"(from {current_churn*100:.1f}% → {safe_target*100:.1f}%). "
                f"This protects ${mrr_at_risk:,.0f}/month in at-risk MRR. "
                f"Focus: activation, onboarding, and 30-day check-in cadence."
            ),
        })

    # ── burn_multiple: need to stay below threshold ───────────────────────────
    elif tm == "burn_multiple" and direction == "above":
        safe_target = threshold * (1 - safety_margin)
        derived_bm = derived.get("burn_multiple", 99)
        if derived_bm <= safe_target and not already_triggered:
            action["action"] = "monitor"
            action["message"] = f"Burn multiple ({derived_bm:.1f}×) below danger ({threshold:.1f}×). Monitor."
            return action

        # To reduce burn_multiple, either reduce burn_rate OR increase net_new_mrr
        net_new_mrr = metrics.mrr * metrics.mrr_growth_rate
        # Option A: reduce burn
        target_burn = net_new_mrr * safe_target if net_new_mrr > 0 else 0
        burn_reduction = max(0, metrics.burn_rate - target_burn)
        # Option B: increase growth rate needed
        target_growth_rate = metrics.burn_rate / (metrics.mrr * safe_target) if metrics.mrr > 0 else 0

        # Only show Option B when it's realistic (< 50% monthly growth target)
        if target_growth_rate <= 0.5:
            opt_b = f" Option B — Grow MRR growth rate to {target_growth_rate*100:.0f}%/month."
        else:
            opt_b = " (Revenue growth alone cannot fix this — burn reduction is the only viable path.)"
        action.update({
            "action": "reduce_burn_or_grow",
            "target_value": round(safe_target, 2),
            "burn_reduction_option": round(burn_reduction),
            "growth_rate_needed": round(target_growth_rate, 3),
            "message": (
                f"Burn multiple is {derived_bm:.1f}× (danger: {threshold:.1f}×). "
                f"Reduce burn by ${burn_reduction:,.0f}/month to reach {safe_target:.1f}×."
                f"{opt_b}"
            ),
        })

    # ── ltv_cac_ratio: need to stay above threshold ───────────────────────────
    elif tm == "ltv_cac_ratio" and direction == "below":
        safe_target = threshold * (1 + safety_margin)
        current_ratio = derived.get("ltv_cac_ratio", 0)
        if current_ratio >= safe_target and not already_triggered:
            action["action"] = "monitor"
            action["message"] = f"LTV:CAC ({current_ratio:.1f}×) above safe minimum ({safe_target:.1f}×). Monitor."
            return action

        ltv_needed = metrics.cac * safe_target
        ltv_increase = ltv_needed - metrics.ltv
        cac_needed = metrics.ltv / safe_target if metrics.ltv > 0 else 0
        cac_reduction = metrics.cac - cac_needed

        action.update({
            "action": "fix_unit_economics",
            "target_value": round(safe_target, 2),
            "ltv_increase_needed": round(ltv_increase),
            "cac_reduction_option": round(cac_reduction),
            "message": (
                f"LTV:CAC is {current_ratio:.1f}× (danger: <{threshold:.1f}×). "
                f"Option A — Increase LTV by ${ltv_increase:,.0f} (improve retention/upsell). "
                f"Option B — Reduce CAC by ${cac_reduction:,.0f} (improve channel efficiency)."
            ),
        })

    # ── NPS: need to stay above threshold ────────────────────────────────────
    elif tm == "nps" and direction == "below":
        safe_target = threshold + 10  # NPS needs 10-point buffer
        current_nps = metrics.nps
        if current_nps >= safe_target and not already_triggered:
            action["action"] = "monitor"
            action["message"] = f"NPS ({current_nps}) above danger floor ({threshold}). Monitor."
            return action

        nps_gap = safe_target - current_nps
        action.update({
            "action": "improve_nps",
            "target_value": safe_target,
            "nps_gap": nps_gap,
            "message": (
                f"NPS is {current_nps} (danger: <{threshold}). "
                f"Need +{nps_gap} points to reach safe zone. "
                f"Priority: close 10 customer interviews this week, fix top 3 complaint themes."
            ),
        })

    # ── Headcount: need to keep below threshold ───────────────────────────────
    elif tm == "headcount" and direction == "above":
        current_hc = metrics.headcount
        if current_hc <= threshold and not already_triggered:
            action["action"] = "monitor"
            action["message"] = f"Headcount ({current_hc}) below threshold ({threshold}). Continue hiring carefully."
            return action
        excess = current_hc - int(threshold * 0.9)  # 10% safety margin
        action.update({
            "action": "freeze_hiring",
            "target_value": int(threshold * 0.9),
            "excess_headcount": max(0, excess),
            "message": (
                f"Headcount ({current_hc}) exceeds safe growth threshold ({threshold}). "
                f"Implement hiring freeze. Consider reducing by {max(0, excess)} roles "
                f"to restore talent density before next hire."
            ),
        })

    # ── Generic fallback ──────────────────────────────────────────────────────
    else:
        action.update({
            "action": "reduce_risk",
            "message": (
                f"Metric '{tm}' at {derived.get(tm, 'unknown')} approaching "
                f"cascade trigger ({direction} {threshold}). "
                f"Act within {avg_days - 15} days."
            ),
        })

    return action


# ── $graphLookup cascade fetch ────────────────────────────────────────────────

async def get_cascade_chain(pattern_id: str) -> dict | None:
    """
    Use MongoDB $graphLookup to traverse the failure cascade graph
    up to 3 hops deep from the detected pattern.

    Returns the cascade chain sorted by depth with cumulative probabilities.
    """
    db = get_db()

    pipeline = [
        {"$match": {"pattern_id": pattern_id}},
        {
            "$graphLookup": {
                "from": "failure_patterns",
                "startWith": "$transitions.to_pattern_id",
                "connectFromField": "transitions.to_pattern_id",
                "connectToField": "pattern_id",
                "as": "cascade_chain",
                "maxDepth": 3,
                "depthField": "cascade_depth",
            }
        },
        {
            "$project": {
                "_id": 0,
                "pattern_id": 1,
                "name": 1,
                "survival_rate": 1,
                "failure_count": 1,
                "survival_count": 1,
                "days_to_crisis": 1,
                "category": 1,
                "transitions": 1,
                "cascade_chain.pattern_id": 1,
                "cascade_chain.name": 1,
                "cascade_chain.survival_rate": 1,
                "cascade_chain.failure_count": 1,
                "cascade_chain.survival_count": 1,
                "cascade_chain.days_to_crisis": 1,
                "cascade_chain.category": 1,
                "cascade_chain.cascade_depth": 1,
                "cascade_chain.transitions": 1,
            }
        },
    ]

    try:
        results = await db["failure_patterns"].aggregate(pipeline).to_list(length=1)
    except Exception as e:
        logger.warning("[cascade] $graphLookup failed: %s", e)
        return None

    if not results:
        return None

    root = results[0]
    raw_chain = root.get("cascade_chain", [])
    root_transitions = root.get("transitions", [])

    if not raw_chain and not root_transitions:
        return None

    # Build transition map for lookup
    chain_by_id = {p["pattern_id"]: p for p in raw_chain}

    # Walk the transition tree to build an ordered cascade timeline
    cascade_steps = []

    def _walk(from_id: str, from_transitions: list, depth: int, cumulative_prob: float, cumulative_days: int):
        if depth > 3:
            return
        for t in (from_transitions or []):
            to_id = t.get("to_pattern_id")
            if not to_id or to_id not in chain_by_id:
                continue
            node = chain_by_id[to_id]
            prob = float(t.get("probability", 0))
            days = int(t.get("avg_days", 60))
            cum_prob = cumulative_prob * prob
            cum_days = cumulative_days + days

            cascade_steps.append({
                "depth": depth,
                "pattern_id": to_id,
                "pattern_name": node["name"],
                "category": node.get("category", ""),
                "survival_rate": node.get("survival_rate") or (
                    node.get("survival_count", 0) /
                    max(node.get("failure_count", 0) + node.get("survival_count", 0), 1)
                ),
                "days_to_crisis": node.get("days_to_crisis", 90),
                "transition_probability": round(prob, 3),
                "cumulative_probability": round(cum_prob, 3),
                "days_from_now": cum_days,
                "trigger_condition": t.get("trigger_condition", ""),
                "trigger_metric": t.get("trigger_metric", ""),
                "trigger_threshold": t.get("trigger_threshold"),
                "trigger_direction": t.get("trigger_direction", ""),
                "mechanism": t.get("mechanism", ""),
                "observed_count": t.get("observed_count", 0),
            })

            next_transitions = node.get("transitions", [])
            _walk(to_id, next_transitions, depth + 1, cum_prob, cum_days)

    _walk(pattern_id, root_transitions, 1, 1.0, 0)

    # Sort by days_from_now (timeline order)
    cascade_steps.sort(key=lambda x: (x["days_from_now"], -x["cumulative_probability"]))

    # Deduplicate — keep highest probability path for each pattern
    seen: set[str] = set()
    deduped = []
    for step in cascade_steps:
        if step["pattern_id"] not in seen:
            seen.add(step["pattern_id"])
            deduped.append(step)

    return {
        "root_pattern_id": pattern_id,
        "root_pattern_name": root["name"],
        "root_survival_rate": root.get("survival_rate") or (
            root.get("survival_count", 0) /
            max(root.get("failure_count", 0) + root.get("survival_count", 0), 1)
        ),
        "cascade_steps": deduped,
        "max_depth": max((s["depth"] for s in deduped), default=0),
        "has_cascade": len(deduped) > 0,
        "total_chain_length": len(deduped),
        "worst_case_days": max((s["days_from_now"] for s in deduped), default=0),
        "cascade_calibration": _build_calibration_note(deduped),
    }


# ── Full cascade analysis for a startup ──────────────────────────────────────

async def compute_full_cascade(
    metrics: MetricsInput,
    pattern_id: str,
    pattern_confidence: float,
) -> dict | None:
    """
    1. Fetch cascade chain via $graphLookup
    2. For each cascade step, compute the intervention needed to break that link
    3. Write the result atomically via Motor ACID transaction
    4. Return full cascade result with interventions
    """
    cascade = await get_cascade_chain(pattern_id)
    if not cascade or not cascade["has_cascade"]:
        logger.info("[cascade] No cascade chain found for %s", pattern_id)
        return None

    derived = _derived(metrics)
    interventions = []

    # For each step, find the TRANSITION from the previous pattern
    # and compute the intervention to break it
    db = get_db()

    for step in cascade["cascade_steps"]:
        # Fetch the source pattern to get the full transition object
        # (the step only has subset of transition data from graphLookup projection)
        if step["depth"] == 1:
            source_pid = pattern_id
        else:
            # depth 2+ — source is parent in chain
            # Find which cascade step at depth-1 has a transition to this step
            parent_steps = [s for s in cascade["cascade_steps"]
                           if s["depth"] == step["depth"] - 1]
            source_pid = parent_steps[0]["pattern_id"] if parent_steps else pattern_id

        source_doc = await db["failure_patterns"].find_one(
            {"pattern_id": source_pid},
            {"transitions": 1}
        )
        source_transitions = source_doc.get("transitions", []) if source_doc else []
        matched_t = next(
            (t for t in source_transitions if t.get("to_pattern_id") == step["pattern_id"]),
            None
        )

        if matched_t and matched_t.get("trigger_metric"):
            intervention = compute_cascade_intervention(metrics, matched_t)
            if intervention:
                intervention["breaks_cascade_to"] = step["pattern_id"]
                intervention["cascade_pattern_name"] = step["pattern_name"]
                intervention["days_until_cascade"] = step["days_from_now"]
                interventions.append(intervention)

    # ACID Transaction: atomically write intervention plan + telemetry + update counter
    client = db.client
    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                # 1. Write the cascade intervention plan
                await db["cascade_interventions"].update_one(
                    {
                        "startup_name": metrics.startup_name,
                        "root_pattern_id": pattern_id,
                    },
                    {
                        "$set": {
                            "startup_name": metrics.startup_name,
                            "root_pattern_id": pattern_id,
                            "root_pattern_name": cascade["root_pattern_name"],
                            "cascade_steps": cascade["cascade_steps"],
                            "interventions": interventions,
                            "metrics_snapshot": {
                                "mrr": metrics.mrr,
                                "burn_rate": metrics.burn_rate,
                                "runway_months": metrics.runway_months,
                                "churn_rate": metrics.churn_rate,
                                "nps": metrics.nps,
                            },
                            "computed_at": datetime.utcnow(),
                            "expires_at": datetime.utcnow() + timedelta(days=90),
                        }
                    },
                    upsert=True,
                    session=session,
                )

                # 2. Record cascade telemetry event
                await db["telemetry_events"].insert_one(
                    {
                        "event": "cascade_computed",
                        "startup_name": metrics.startup_name,
                        "root_pattern_id": pattern_id,
                        "cascade_depth": cascade["max_depth"],
                        "cascade_length": cascade["total_chain_length"],
                        "worst_case_days": cascade["worst_case_days"],
                        "interventions_count": len(interventions),
                        "timestamp": datetime.utcnow(),
                    },
                    session=session,
                )

                # 3. Increment times_triggered counter on the root pattern
                await db["failure_patterns"].update_one(
                    {"pattern_id": pattern_id},
                    {"$inc": {"times_triggered": 1}},
                    session=session,
                )

            logger.info(
                "[cascade] ACID write OK — startup=%s pattern=%s depth=%d interventions=%d",
                metrics.startup_name, pattern_id, cascade["max_depth"], len(interventions),
            )
    except Exception as e:
        logger.warning("[cascade] ACID transaction failed (non-fatal): %s", e)

    return {
        **cascade,
        "interventions": interventions,
        "derived_metrics": {k: derived[k] for k in ["burn_multiple", "ltv_cac_ratio"]},
        "cascade_calibration": _build_calibration_note(cascade["cascade_steps"]),
    }


def _build_calibration_note(steps: list[dict]) -> str:
    """Build a human-readable note about how well the cascade is calibrated."""
    total_observed = sum(s.get("observed_count", 0) for s in steps)
    if total_observed == 0:
        return (
            "Probabilities: research estimates (seed). "
            "Self-improving via MongoDB Change Streams — each real A→B transition updates: "
            "p = 0.3 × initial + 0.7 × (observed/total_starts)."
        )
    elif total_observed < 10:
        return (
            f"Partially calibrated from {total_observed} real oracle observation(s). "
            "Bayesian blend: p = 0.3 × initial + 0.7 × empirical. "
            "Converges further with each new analysis."
        )
    else:
        return (
            f"Auto-calibrated from {total_observed} confirmed real-world transitions via Change Streams. "
            "Bayesian blend: p = 0.3 × initial + 0.7 × empirical."
        )


# ── Self-improving: record a confirmed transition ─────────────────────────────

async def record_observed_transition(from_pattern_id: str, to_pattern_id: str, days_between: int):
    """
    Called by Change Stream when a startup transitions from one pattern to another.
    Updates observed_count on the transition and recomputes probability via Bayesian blend.
    """
    db = get_db()

    # Increment observed_count on the specific transition
    result = await db["failure_patterns"].update_one(
        {
            "pattern_id": from_pattern_id,
            "transitions.to_pattern_id": to_pattern_id,
        },
        {
            "$inc": {"transitions.$.observed_count": 1},
            "$set": {"transitions.$.last_observed": datetime.utcnow()},
        },
    )

    if result.modified_count == 0:
        return  # Transition not in graph — ignore

    # Recompute probability via Bayesian blend
    # new_prob = 0.3 * initial_probability + 0.7 * (observed_count / total_starts)
    total_starts = await db["startup_analyses"].count_documents(
        {"pattern_id": from_pattern_id, "alert": True}
    )

    if total_starts >= 5:
        pattern = await db["failure_patterns"].find_one(
            {"pattern_id": from_pattern_id},
            {"transitions": 1},
        )
        if not pattern:
            return

        for t in pattern.get("transitions", []):
            if t.get("to_pattern_id") == to_pattern_id:
                observed = t.get("observed_count", 0)
                initial = float(t.get("initial_probability", t.get("probability", 0.5)))
                empirical = observed / total_starts
                blended = round(0.3 * initial + 0.7 * empirical, 3)

                await db["failure_patterns"].update_one(
                    {
                        "pattern_id": from_pattern_id,
                        "transitions.to_pattern_id": to_pattern_id,
                    },
                    {"$set": {"transitions.$.probability": blended}},
                )
                logger.info(
                    "[cascade] Probability updated %s→%s: %.3f→%.3f (obs=%d/total=%d)",
                    from_pattern_id, to_pattern_id, initial, blended, observed, total_starts,
                )
                break
