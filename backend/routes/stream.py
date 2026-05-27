"""
Streaming analysis endpoint using Server-Sent Events (SSE).

Routes through the ADK SequentialAgent pipeline (Investigator → Challenger → Reporter).
Each tool function emits progress events to a shared asyncio.Queue (via ContextVar),
which this endpoint yields as SSE in real time.

The terminal the user sees is a genuine window into the ADK SequentialAgent execution —
not a replay, not a simulation.
"""
import json
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from backend.db.schemas import MetricsInput

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/analyze/stream")
async def analyze_stream(metrics: MetricsInput):
    """
    SSE streaming endpoint — routes through the same 3-agent ADK SequentialAgent as /analyze.
    Each agent step streams to the client as it executes.
    """
    from backend.services.adk_runner import run_analysis_via_adk_stream

    async def _sse():
        async for event_dict in run_analysis_via_adk_stream(metrics):
            yield f"data: {json.dumps(event_dict)}\n\n"

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
