from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path

from backend.db.connection import ping, close
from backend.routes import metrics, audit, patterns
from backend.config import OUTPUT_PATH
from backend.services.mcp_client import mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await ping()
    print("[OK] MongoDB connected (Motor)")
    OUTPUT_PATH.mkdir(exist_ok=True)
    # Start MongoDB MCP server in background
    await mcp.start()
    if mcp.available:
        print(f"[OK] MongoDB MCP server ready ({len(mcp._tool_names)} tools)")
    else:
        print("[WARN] MongoDB MCP unavailable — Motor fallback active")
    yield
    # Shutdown
    await mcp.stop()
    await close()


app = FastAPI(
    title="The Failure Oracle",
    description="AI agent that detects startup failure patterns before they become fatal",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(metrics.router, prefix="/api/metrics", tags=["metrics"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(patterns.router, prefix="/api/patterns", tags=["patterns"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "failure-oracle"}


# Serve frontend — must be last
frontend_path = Path("frontend")
if frontend_path.exists():
    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
