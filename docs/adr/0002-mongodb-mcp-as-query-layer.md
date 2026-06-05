# ADR-0002: MongoDB MCP as the query layer, not Motor directly

**Status:** Accepted
**Date:** 2026-06-01

---

## The problem

The backend uses Motor (the async Python MongoDB driver) throughout the codebase. Calling Motor directly from every agent tool would have been simpler and slightly faster. We chose not to do that.

## Why MCP matters here

The core reason is verifiability. When a judge or investor watches the live SSE terminal and sees `MongoDB MCP -> find('failure_patterns', {pattern_id: 'F-017'})`, that is not a log line we wrote by hand. It is the actual MCP tool call the ADK agent is making, surfaced in real time. The `source: "mcp"` field in every `/api/patterns/` response is independently checkable: open the endpoint, look at the field. There is no equivalent proof with a direct Motor call. The code says Motor was used, but nothing is observable at runtime.

The second reason is discipline. Each agent tool has to construct a valid MCP call with a named collection and explicit filter or pipeline arguments. This is more constrained than arbitrary Python driver code, which means the retrieval logic is auditable in a way that raw Motor calls are not.

## The trade-offs

Each MCP call adds a small round-trip overhead compared to calling the driver directly. For bulk operations like seeding the database, we still use Motor. For all agent-facing retrieval, scoring, and aggregation in the critical path, the MCP server is the only path.

One edge case worth noting: the `mongodb-mcp-server` runs as a persistent background process. On Cloud Run, if that process dies, the next request restarts it, adding 2 to 3 seconds to the first call after a cold start. Every MCP call has a fallback to a direct Motor query if the MCP server is unavailable, so the pipeline still works even in that scenario.
