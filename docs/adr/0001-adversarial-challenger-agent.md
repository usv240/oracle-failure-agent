# ADR-0001: Adversarial Challenger Agent before every verdict

**Status:** Accepted
**Date:** 2026-06-01

---

## The problem

The first version of the pipeline had one agent score each pattern and return a confidence number. It worked, but the scores were not trustworthy in a specific way.

When metrics were mixed (high burn but decent runway, high churn but growing revenue), the model anchored to whichever signal appeared first in the prompt and built its reasoning around that. There was nothing pushing back. A single agent doing retrieval and scoring has no pressure to doubt itself. It finds a plausible match, tells a coherent story, and returns a number. The founder had no way to know if 91% confidence was genuinely strong or just the model being confidently wrong.

## What we tried first

We considered three alternatives before landing on the Challenger:

1. **Run the same scoring call three times and average.** This reduces random variance slightly, but all three calls see identical data in the same order. You are averaging over noise, not over real disagreement.

2. **Add a fact-check pass.** A second model reviews the first model's output. The problem: the second model reads the first model's conclusion before forming its own view. It anchors on that framing and rarely produces a genuinely independent signal.

Neither approach gives the founder any information about *how confident the system actually is*.

## What we built instead

After the Investigator produces a match, the Challenger agent gets the same raw metrics and a brief that requires it to find reasons the match is wrong. It cannot see the Investigator's reasoning. It only sees the pattern definition and the numbers. It produces its own confidence score, a CONFIRM or DISPUTE verdict, and specific objections.

The founder sees both positions side by side. When the Investigator scores 95% and the Challenger scores 60%, the DISPUTED badge at a 35-point gap tells the founder this is a contested finding. When both agents land within 10 points, the CONFIRMED badge carries real weight because the finding survived an active challenge.

The Challenger also catches errors the Investigator misses. If the Investigator focused on one strong signal and ignored two contradictory ones, the Challenger working from the same raw metrics will surface those contradictions.

## The trade-offs

This adds one full Gemini 3 call per analysis, adding roughly 8 to 15 seconds of latency. The scores are also non-deterministic, so the gap between the two agents will vary slightly across runs.

Neither is a dealbreaker. For a decision that could affect months of runway, the extra latency is worth it. And the variance is honest: it reflects genuine uncertainty instead of hiding it behind a precise-looking number.
