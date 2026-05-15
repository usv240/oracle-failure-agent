"""
MongoDB MCP client — persistent connection to mongodb-mcp-server.

Starts the MCP server once at app startup via a background asyncio task.
All requests reuse the live session (no per-request startup overhead).
Falls back to Motor if MCP is unavailable.

Binary: mongodb-mcp-server (globally installed via npm install -g mongodb-mcp-server@1.9.0)
Connection: MDB_MCP_CONNECTION_STRING env var (avoids Windows shell parsing issues with URI)
"""
import os
import re
import json
import asyncio
import logging
from typing import Any, Optional

from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters

logger = logging.getLogger(__name__)

MONGODB_URI = os.getenv("MONGODB_URI", "")
DB_NAME = "oracle_db"

# Global binary avoids npx download overhead on every request
MCP_COMMAND = "mongodb-mcp-server"
MCP_ARGS: list[str] = []
# Pass URI via env var — avoids Windows shell ? & parsing issues
MCP_ENV = {**os.environ, "MDB_MCP_CONNECTION_STRING": MONGODB_URI}


def _parse_mcp_content(content) -> Any:
    """
    Extract data from MCP response content.

    mongodb-mcp-server returns 2 content items:
      [0] Summary text: "Query resulted in N documents. Returning M documents."
      [1] Security-wrapped JSON:
            The following section contains unverified user data...
            <untrusted-user-data-UUID>          ← appears 3x (warning + data + footer)
            [{"_id": ...}, ...]
            </untrusted-user-data-UUID>

    We need the JSON from the 2nd opening tag (the actual data), not the 1st (in warning text).
    """
    last_text = None

    for c in content:
        if not hasattr(c, "text"):
            continue
        text = c.text
        last_text = text  # save for fallback

        # Look for the security-tagged data block
        opens  = [m.end()   for m in re.finditer(r"<untrusted-user-data-[^/>]+>", text)]
        closes = [m.start() for m in re.finditer(r"</untrusted-user-data-[^>]+>", text)]

        if len(opens) >= 2 and len(closes) >= 2:
            # 2nd pair wraps the actual JSON data
            json_str = text[opens[1]:closes[1]].strip()
            try:
                parsed = json.loads(json_str)
                if isinstance(parsed, (list, dict)):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass

        # Try direct JSON parse (for non-tagged responses)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, (list, dict)):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    # Return the last raw text (summary line like "Found N documents...")
    return last_text


class MCPManager:
    """
    Manages a persistent stdio connection to the MongoDB MCP server.
    Background asyncio task keeps the MCP process alive.
    All requests use the single shared session via an async lock.
    """

    def __init__(self):
        self._session: Optional[ClientSession] = None
        self._task: Optional[asyncio.Task] = None
        self._ready = asyncio.Event()
        self._shutdown = asyncio.Event()
        self._lock = asyncio.Lock()
        self.available = False
        self.tool_names: set[str] = set()

    async def start(self):
        """Start the background MCP worker. Waits up to 15s for connection."""
        self._task = asyncio.create_task(self._worker(), name="mcp-worker")
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=15.0)
            if self.available:
                logger.info("[MCP] Connected — %d tools: %s",
                            len(self.tool_names), sorted(self.tool_names))
        except asyncio.TimeoutError:
            logger.warning("[MCP] Connection timed out — Motor fallback active")
            self.available = False

    async def stop(self):
        """Signal shutdown and clean up."""
        self._shutdown.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                self._task.cancel()

    async def _worker(self):
        """
        Long-running background task owning the MCP stdio process.
        Signals _ready once initialised; stays alive until _shutdown.
        """
        params = StdioServerParameters(
            command=MCP_COMMAND,
            args=MCP_ARGS,
            env=MCP_ENV,
        )
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.tool_names = {t.name for t in tools.tools}
                    self._session = session
                    self.available = True
                    self._ready.set()
                    await self._shutdown.wait()   # stay alive
        except Exception as e:
            logger.warning("[MCP] Worker failed: %s — Motor fallback active", e)
            self.available = False
            self._ready.set()  # unblock start() even on failure

    async def call_tool(self, tool_name: str, args: dict) -> Any:
        """Call an MCP tool and return parsed result."""
        if not self.available or self._session is None:
            raise RuntimeError("MCP session not available")
        async with self._lock:
            result = await self._session.call_tool(tool_name, args)
        return _parse_mcp_content(result.content)

    # ── Convenience helpers ──────────────────────────────────────────

    async def find(self, collection: str, filter_: dict = None,
                   projection: dict = None, limit: int = 200) -> list[dict]:
        """Query documents via MCP `find` tool."""
        args: dict = {"database": DB_NAME, "collection": collection, "limit": limit}
        if filter_:
            args["filter"] = filter_
        if projection:
            args["projection"] = projection

        result = await self.call_tool("find", args)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "documents" in result:
            return result["documents"]
        return []

    async def find_one(self, collection: str, filter_: dict,
                       projection: dict = None) -> Optional[dict]:
        """Find a single document via MCP."""
        docs = await self.find(collection, filter_, projection, limit=1)
        return docs[0] if docs else None

    async def count(self, collection: str, filter_: dict = None) -> int:
        """Count documents via MCP `count` tool. Returns integer from text response."""
        args: dict = {"database": DB_NAME, "collection": collection}
        if filter_:
            args["query"] = filter_
        result = await self.call_tool("count", args)
        if isinstance(result, int):
            return result
        # Result is text like "Found 100 documents in the collection..."
        if isinstance(result, str):
            m = re.search(r"\d+", result)
            return int(m.group()) if m else 0
        return 0

    async def aggregate(self, collection: str, pipeline: list) -> list[dict]:
        """Run aggregation pipeline via MCP `aggregate` tool."""
        result = await self.call_tool("aggregate", {
            "database": DB_NAME,
            "collection": collection,
            "pipeline": pipeline,
        })
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "documents" in result:
            return result["documents"]
        return []


# Module-level singleton — imported by routes and services
mcp = MCPManager()
