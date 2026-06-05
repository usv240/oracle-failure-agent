# ADR-0004: $graphLookup cascade graph over flat single-pattern diagnosis

**Status:** Accepted
**Date:** 2026-06-03

---

## The problem

The first version of the Oracle identified one failure pattern per analysis. Enter your metrics, get back the best match: "Burn Multiple Death Spiral, 91% confidence." Useful, but founders told us immediately that it felt incomplete.

The reason: failure patterns do not happen in isolation. Burn Multiple Death Spiral does not kill a startup on its own. It creates conditions that trigger a second pattern, which creates conditions for a third. The real collapse sequence looks like: cash crisis triggers talent loss, talent loss makes it impossible to ship, which kills the ability to raise. Each step is a documented pattern with its own trigger conditions. Showing only the first one gives the founder the wrong mental model of what is coming.

## Why flat pattern matching does not solve this

Flat matching finds the best match for the current state of the metrics. It has no way to show what happens next if nothing changes. A founder would have to re-run the analysis three months later to see the next pattern fire, by which point their options are narrower.

## What we built instead

The `cascade_transitions` collection is a graph. Each document is a directed edge: from one failure pattern to another, with a trigger condition, a delay in days, and a probability. MongoDB's `$graphLookup` traverses this graph starting from the matched pattern, up to depth 3, and returns the full propagation chain.

The output for a WeWork-profile startup is concrete: F-017 (Burn Multiple Death Spiral) is the current match. If burn is not cut in 30 days, F-054 (Talent Density Collapse) fires. If talent loss is not stopped in the next 45 days, F-007 (Bridge Round Spiral) fires. Worst-case timeline to terminal state: 120 days. Each edge shows exactly what the founder would need to change to break the chain before it propagates.

## The self-improving part

We could have pre-computed the cascade for every pattern at seed time and stored it as a flat list. That would be faster to query. But it would go stale the moment any transition probability changed.

Instead, we run `$graphLookup` at query time against a live collection. MongoDB Change Streams watch for new analyses. When a real startup matches F-017 and subsequently triggers F-054, the transition probability on that edge increases. The next founder who matches F-017 gets a cascade graph that reflects real-world outcomes, not just seeded estimates.

## Why depth 3

Beyond depth 3, the compounded probability of any specific chain drops below 5% for most paths. Showing chains that low would add noise, not signal. The depth cap is a product decision, not a technical one.

## Data integrity

The ACID transaction that writes cascade results atomically across three collections is what makes the output trustworthy. If the write fails partway through, the analysis is still recorded but the cascade panel stays empty rather than showing partial data.
