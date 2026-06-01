import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path

from backend.db.connection import ping, close
from backend.routes import metrics, audit, patterns, stream, integrations, monitor, extract, portfolio, export, share, cascade
from backend.config import OUTPUT_PATH, settings
from backend.services.mcp_client import mcp
from backend.services.monitor import start_monitor, stop_monitor
from backend.services.change_stream import start_change_stream, stop_change_stream
from backend.services import telemetry

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────
    await ping()
    logger.info("[OK] MongoDB connected (Motor)")
    OUTPUT_PATH.mkdir(exist_ok=True)

    # Ensure indexes on runtime collections (idempotent, fast if already exist)
    from backend.db.connection import get_db
    _db = get_db()
    try:
        await _db["watched_startups"].create_index("startup_name", unique=True)
        await _db["startup_analyses"].create_index([("startup_name", 1), ("checked_at", -1)])
        await _db["startup_analyses"].create_index([("alert", 1), ("checked_at", -1)])
        # Shared reports: unique ID + TTL 90 days
        await _db["shared_reports"].create_index("share_id", unique=True)
        await _db["shared_reports"].create_index("created_at", expireAfterSeconds=60*60*24*90)
    except Exception as e:
        logger.warning("Index creation warning (may already exist): %s", e)

    # Telemetry indexes — TTL 30d on telemetry_events
    await telemetry.ensure_indexes()

    # Apply $jsonSchema validators (validationLevel=moderate, validationAction=warn)
    # This enforces document shape at the DB level without rejecting existing data.
    try:
        await _db.command({
            "collMod": "startup_analyses",
            "validator": {
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": ["startup_name", "checked_at", "alert"],
                    "properties": {
                        "startup_name": {"bsonType": "string", "minLength": 1},
                        "checked_at":   {"bsonType": "date"},
                        "alert":        {"bsonType": "bool"},
                        "confidence":   {"bsonType": ["double", "null"], "minimum": 0, "maximum": 1},
                        "days_to_crisis": {"bsonType": ["int", "null"]},
                    },
                }
            },
            "validationLevel": "moderate",
            "validationAction": "warn",
        })
        logger.info("[OK] $jsonSchema validator applied to startup_analyses")
    except Exception as e:
        logger.warning("Schema validation (startup_analyses) skipped: %s", e)

    try:
        await _db.command({
            "collMod": "failure_patterns",
            "validator": {
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": ["pattern_id", "name", "category", "narrative"],
                    "properties": {
                        "pattern_id": {"bsonType": "string"},
                        "name":       {"bsonType": "string"},
                        "category":   {"bsonType": "string"},
                        "narrative":  {"bsonType": "string"},
                        "failure_count":  {"bsonType": ["int", "long"]},
                        "survival_count": {"bsonType": ["int", "long"]},
                    },
                }
            },
            "validationLevel": "moderate",
            "validationAction": "warn",
        })
        logger.info("[OK] $jsonSchema validator applied to failure_patterns")
    except Exception as e:
        logger.warning("Schema validation (failure_patterns) skipped: %s", e)

    # Start MongoDB MCP server in background
    await mcp.start()
    if mcp.available:
        logger.info("[OK] MongoDB MCP server ready (%d tools)", len(mcp.tool_names))
    else:
        logger.warning("[WARN] MongoDB MCP unavailable — Motor fallback active")

    # Start background monitoring loop
    start_monitor()
    logger.info("[OK] Background monitoring started (interval: 6h)")

    # Start Change Stream watcher (event-driven alert detection)
    start_change_stream()
    logger.info("[OK] Change stream watcher started")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    await stop_change_stream()
    await stop_monitor()
    await mcp.stop()
    await close()


CLOUD_RUN_URL = settings.APP_URL

app = FastAPI(
    title="The Failure Oracle",
    description="AI agent that detects startup failure patterns before they become fatal",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[CLOUD_RUN_URL, "http://localhost:8080", "http://localhost:8101", "http://127.0.0.1:8080"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Global exception handler — never expose internal tracebacks to clients
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again."},
    )

app.include_router(metrics.router, prefix="/api/metrics", tags=["metrics"])
app.include_router(stream.router, prefix="/api/metrics", tags=["metrics"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(patterns.router, prefix="/api/patterns", tags=["patterns"])
app.include_router(cascade.router, prefix="/api/cascade", tags=["cascade"])
app.include_router(integrations.router, prefix="/api/integrations", tags=["integrations"])
app.include_router(monitor.router, prefix="/api/metrics", tags=["monitoring"])
app.include_router(extract.router, prefix="/api/metrics", tags=["extraction"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(export.router, prefix="/api/export", tags=["export"])
app.include_router(share.router, prefix="/api/share", tags=["share"])


@app.get("/api/stats")
async def stats():
    """Live platform stats pulled from MongoDB — used by the frontend live-stats bar.

    Includes telemetry counts for MCP, vector search, and Gemini calls over the
    last 24h. These prove the partner integrations are firing on every analysis
    — not just decorative.
    """
    from backend.db.connection import get_db
    from datetime import datetime, timezone, timedelta
    db = get_db()
    try:
        total_analyses, monitored, pattern_count, tele_counts = await asyncio.gather(
            db["startup_analyses"].count_documents({}),
            db["watched_startups"].count_documents({}),
            db["failure_patterns"].count_documents({}),
            telemetry.get_24h_counts(),
        )
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        alerts_today = await db["startup_analyses"].count_documents({
            "alert": True,
            "checked_at": {"$gte": cutoff},
        })
    except Exception:
        return {
            "total_analyses": 0, "startups_monitored": 0, "alerts_today": 0, "pattern_count": 0,
            "mcp_calls_24h": 0, "vector_searches_24h": 0, "gemini_calls_24h": 0,
        }
    return {
        "total_analyses": total_analyses,
        "startups_monitored": monitored,
        "alerts_today": alerts_today,
        "pattern_count": pattern_count,
        "mcp_calls_24h": tele_counts.get("mcp_call", 0),
        "vector_searches_24h": tele_counts.get("vector_search", 0),
        "gemini_calls_24h": tele_counts.get("gemini_call", 0),
    }


@app.get("/api/health")
async def health():
    from backend.db.connection import get_db
    import backend.services.adk_runner as _adk_mod
    from backend.services.gemini import active_gemini3_model, _GEMINI3_CHAIN
    db = get_db()
    try:
        pattern_count = await db["failure_patterns"].count_documents({})
    except Exception:
        pattern_count = -1
    return {
        "status": "ok",
        "service": "failure-oracle",
        "mongodb": "connected",
        "mcp": "ready" if mcp.available else "unavailable (motor fallback active)",
        "mcp_tools": len(mcp.tool_names),
        "adk_agent": "initialized" if _adk_mod._runner is not None else "pending",
        "pattern_count": pattern_count,
        "gemini_active": active_gemini3_model,
        "gemini3_chain": _GEMINI3_CHAIN,
        "gemini_fallback": f"{settings.GEMINI_MODEL} (vertex-ai)",
        "embedding_model": "voyage-4-large (1024-dim)" if settings.VOYAGE_API_KEY else "text-embedding-004 → 1024-dim",
        "embedding_source": "MongoDB Voyage AI" if settings.VOYAGE_API_KEY else "Google Vertex AI",
    }


# Serve frontend static files — must be last (catches all remaining routes)
frontend_path = Path("frontend")
if frontend_path.exists():
    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
