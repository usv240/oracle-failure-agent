# ADR-0003: Hybrid Vector + BM25 RRF retrieval over pure vector search

**Status:** Accepted  
**Date:** 2026-06-02

---

The pattern library has 100 entries. Each pattern has a name, a description, trigger conditions, warning signals, and a survival playbook. When a founder enters their metrics, the system needs to find which patterns are plausible matches.

Pure vector search was the obvious first approach. Embed the metrics, embed each pattern description, find the nearest neighbours by cosine similarity. This works for semantic similarity — "high burn rate" will cluster near patterns that describe cash flow failure even if the exact phrase doesn't appear. But it fails in a specific way for structured data: it treats the entire metric vector as an undifferentiated blob and has no way to weight specific fields.

A burn multiple of 4× should rank Burn Multiple Death Spiral much higher than similar-sounding patterns that don't specifically trigger on that metric. Pure vector search cannot do that reliably because the embedding collapses the metric structure into a single dense vector. Two startups with very different burn multiples but similar overall profiles can end up at almost the same embedding distance from the same pattern.

BM25 retrieval has the opposite problem. It is strong on exact-match signals — a search for "burn multiple" will reliably surface patterns that explicitly mention burn multiple — but weak on semantic variation. A pattern that describes "cash consumption rate exceeding revenue growth" will score low for the query "burn multiple" even though they describe the same risk.

Reciprocal Rank Fusion combines both rankings without requiring you to tune a blend weight. Each retrieval path produces an independent ranked list; RRF merges them by taking the reciprocal of each document's rank in each list and summing. Documents that rank well in both lists rise to the top. Documents that rank well in only one list get partial credit. In practice, patterns with both semantic affinity and lexical match with the input metrics consistently outrank patterns that only have one.

The Atlas Search `$compound` operator lets us boost specific fields. Trigger condition matches get higher weight than description matches, so a pattern whose exact trigger conditions are met will always rank above a semantically similar pattern whose triggers are not.

`moreLikeThis` is used for a secondary use case: once a primary match is found, the similar patterns panel uses `moreLikeThis` to surface related patterns the founder should be aware of even if they don't meet the confidence threshold. This uses the document body of the matched pattern as the query rather than the metrics vector.

The combined approach adds complexity — two retrieval paths, an RRF merge step, and a re-scoring pass by Gemini before the top-5 candidates are returned. The alternative would have been faster. But for a 100-pattern library where the difference between the right match and the wrong match can change a founder's decision about whether to raise or cut, the accuracy improvement is worth the latency.
