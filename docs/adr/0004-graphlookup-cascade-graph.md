# ADR-0004: $graphLookup cascade graph over flat single-pattern diagnosis

**Status:** Accepted  
**Date:** 2026-06-03

---

The first version of the Oracle diagnosed one failure pattern per analysis. Enter your metrics, get back the best match: "Burn Multiple Death Spiral, 91% confidence." That was useful but incomplete in a specific way that founders recognised immediately.

Failure patterns don't happen in isolation. Burn Multiple Death Spiral doesn't kill a startup directly — it creates conditions that trigger a second pattern, which creates conditions for a third. The real risk timeline looks like: cash crisis → talent flight → inability to raise → death. Each step is a documented pattern with its own trigger conditions. Showing only the first pattern gives the founder the wrong mental model of what is actually happening.

Flat pattern matching cannot represent this. It finds the best match for the current state of the metrics, but it has no way to express what happens to the startup if nothing changes. You would need to run the analysis again three months from now to see the next pattern — by which point the options are narrower.

The `cascade_transitions` collection models the failure state machine directly. Each document describes an edge: from one pattern to another, with a trigger condition, a delay in days, and a probability. `$graphLookup` traverses this graph from the matched pattern as the root, up to depth 3, and returns the full propagation chain. The result is not a prediction — it is the documented consequence chain from the pattern library itself, made traversable.

The practical output for a WeWork-profile startup is: F-017 (Burn Multiple Death Spiral) → in 30 days, F-054 (Talent Density Collapse) fires if burn isn't cut → in 45 more days, F-007 (Bridge Round Spiral) fires if talent loss continues. Worst-case timeline: 120 days from today to terminal state. Each edge has an intervention condition so the founder knows exactly what has to change to break the chain at each step.

Three alternatives were considered. Pre-computing the full cascade for every pattern at seed time and storing it as a flat array avoids the graph query but breaks as soon as any transition probability updates. A second option was running `$graphLookup` at query time but with static probabilities — this works but means the cascade never improves. The chosen approach runs `$graphLookup` at query time against a live collection that Change Streams update after every new analysis. When a real startup hits F-017 and subsequently triggers F-054, the transition probability on that edge increases. The cascade graph for the next founder who matches F-017 reflects that real-world outcome.

The depth cap at 3 is deliberate. Beyond depth 3, the compounded probability of any specific chain becomes low enough that surfacing it adds noise rather than actionable signal. The algebra for cascade survival probability (multiply the edge probabilities at each depth) drops below 5% by depth 4 for most chains, which is not useful to show.

The ACID transaction that writes cascade interventions atomically across three collections is what makes the data trustworthy enough to drive business decisions. If the cascade write fails partway through, the analysis is still recorded, but the cascade panel is empty rather than showing partial data.
