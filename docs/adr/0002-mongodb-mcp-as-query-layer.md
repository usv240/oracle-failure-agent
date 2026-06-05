# ADR-0002: MongoDB MCP as the query layer, not Motor directly

**Status:** Accepted  
**Date:** 2026-06-01

---

The backend uses Motor (the async Python MongoDB driver) throughout. It would have been straightforward to call Motor directly from every agent tool — `await collection.find(...)`, `await collection.aggregate(...)` — and skip the MCP layer entirely. The pipeline would be faster and simpler to reason about.

The decision to route all pattern queries through the `mongodb-mcp-server` instead was not taken lightly, because it adds a process boundary and a serialisation round-trip for every retrieval call.

The reason it matters for this project is verifiability. When a judge or an investor sees the SSE terminal streaming `MongoDB MCP → find('failure_patterns', {pattern_id: 'F-017'})`, that is not a log we wrote — it is the actual MCP tool call the ADK agent is making, surfaced live. The `source: "mcp"` field in every `/api/patterns/` response is independently verifiable: fetch the endpoint, look at the field. There is no equivalent proof when you call Motor directly; the code says you used Motor, but there is nothing observable at runtime.

The second reason is that MCP keeps the agent tools honest. Each agent tool must construct a valid MCP tool call with a named collection and explicit filter/pipeline arguments. This is more constrained than calling Motor with arbitrary Python, which means the retrieval logic is auditable in a way that raw driver calls are not. When the Investigator runs `vectorSearch` and the Reporter runs `$graphLookup`, both operations go through named, inspectable MCP tools.

The practical trade-off is real. Each MCP call adds a subprocess IPC round-trip compared to a direct driver call. For batch operations like seeding, we still use Motor. For all agent-facing retrieval, scoring, and aggregation in the critical path, the MCP server is the only path.

One edge case worth documenting: the `mongodb-mcp-server` runs as a persistent stdio process managed by `mcp_client.py`. On Cloud Run, if the MCP process dies, the next request will restart it. The restart adds 2–3 seconds to the first call after a cold start. Every MCP tool call is wrapped in a try/except that falls back to a direct Motor query if the MCP server is unavailable, so the pipeline degrades gracefully rather than failing.
