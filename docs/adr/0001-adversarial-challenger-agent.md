# ADR-0001: Adversarial Challenger Agent before every verdict

**Status:** Accepted  
**Date:** 2026-06-01

---

The first version of the pipeline had a single Investigator agent score each pattern and output a confidence number. It worked, but the scores were unreliable in a specific way: when the input metrics were ambiguous — high burn but reasonable runway, high churn but growing revenue — the model would anchor to whichever signal it encountered first in the prompt and build its reasoning around that. There was no mechanism to push back.

The problem is that a single LLM doing both retrieval and scoring has no adversarial pressure. It finds a plausible match, builds a coherent narrative, and returns a number. Users had no way to know whether a 91% confidence score was a strong match or the model confidently wrong.

Three alternatives were considered. Running the same scoring call three times and averaging reduces variance slightly but all three calls see identical data in identical order — you are averaging over temperature noise, not over genuine disagreement. Adding a fact-check pass where a second model reviews the first model's output falls into the same trap: the second model anchors on the first model's framing before forming its own view. Neither approach produces an independent signal.

The adversarial Challenger does something different. After the Investigator produces a match and confidence score, the Challenger agent receives the same raw metrics and a brief that explicitly requires it to find reasons the match is wrong. It cannot see the Investigator's reasoning; it only sees the pattern definition and the metrics. It produces an independent confidence estimate, a CONFIRM or DISPUTE verdict, and specific objections.

The practical result: the user sees both positions. When the Investigator scores 95% and the Challenger scores 60%, the DISPUTED badge at Δ35pp tells the founder this is a contested finding — credible enough to take seriously, not certain enough to treat as fact. When both agents agree within 10pp, the CONFIRMED badge carries genuine weight because it survived an adversarial challenge.

The Challenger also catches retrieval errors. If the Investigator matched on one strong signal and ignored two contradictory signals, the Challenger — working from the same raw metrics — will surface those contradictions in its objections. The debate transcript is visible, so the founder can read both sides rather than accepting a bare number.

Two downsides worth acknowledging. This adds one full Gemini call per analysis, adding 8–15 seconds of latency. And because both agents are non-deterministic, the Δ between them varies on repeated runs. Neither is a dealbreaker for this use case: the latency is acceptable for a decision that could affect months of runway, and the variance is honest — it reflects genuine uncertainty rather than hiding it behind a false precision.
