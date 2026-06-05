# ADR-0003: Hybrid Vector + BM25 RRF retrieval over pure vector search

**Status:** Accepted
**Date:** 2026-06-02

---

## The problem

The pattern library has 100 entries. When a founder enters their metrics, we need to find which patterns actually match. The retrieval method matters a lot here: a wrong retrieval means the entire analysis is wrong, regardless of how good the scoring step is.

## Why pure vector search is not enough

The obvious first approach was pure vector search: embed the metrics, embed each pattern, find the nearest neighbours by cosine similarity.

This works for semantic similarity. "High burn rate" clusters near patterns about cash flow failure even if those exact words do not appear. But it breaks for structured data. A burn multiple of 4x should rank Burn Multiple Death Spiral far above other patterns. Pure vector search cannot do that reliably because the embedding turns the entire metric set into one dense vector. Two startups with very different burn multiples but similar overall profiles can end up at nearly the same embedding distance from the same pattern.

## Why pure BM25 is not enough either

BM25 keyword search has the opposite problem. It is great at exact matches: search for "burn multiple" and it will reliably surface patterns that mention "burn multiple." But it will miss a pattern that describes "cash consumption rate exceeding revenue growth" even though both describe the same risk. Semantic variation breaks it.

## What we use instead

Reciprocal Rank Fusion (RRF) combines both rankings without requiring us to tune a blend weight. Each retrieval method produces its own ranked list. RRF merges them by taking the reciprocal of each document's rank in each list and adding the scores together. Patterns that rank well in both lists rise to the top. Patterns that rank well in only one list still get partial credit.

In practice, patterns with both semantic affinity and lexical match consistently outrank patterns that only match one way.

We also use the Atlas Search `$compound` operator to boost specific fields. Trigger condition matches get higher weight than description matches, so a pattern whose exact trigger conditions fire will always rank above a semantically similar pattern whose triggers do not.

## The trade-offs

Two retrieval paths plus an RRF merge plus a Gemini re-scoring pass adds complexity and some latency. A single retrieval path would be faster. But for a tool where the difference between the right pattern and the wrong pattern can change whether a founder raises, cuts, or pivots, the accuracy is worth it.
