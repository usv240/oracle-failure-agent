# The Failure Oracle

> 90% of startups fail for the same documented reasons. The warning signals appear 3–6 months before the crisis. Most founders never see them coming.

The Failure Oracle is an AI agent that watches your startup's live metrics and fires an early warning when your trajectory matches a documented failure pattern — with the exact survival playbook used by companies that made it through.

**Live demo:** https://oracle-failure-oracle-38381883054.us-central1.run.app

---

## The Problem

When a Sequoia partner looks at your metrics and says *"I've seen this before"*, they're pattern-matching against a mental library built from hundreds of failures. That library took 20 years to build. Most founders don't have access to it.

The patterns are documented. The signals appear months in advance. Quibi's month-4 metrics matched a known failure signature weeks before the first press story ran. WeWork's unit economics matched a pattern seen dozens of times in marketplace companies before the IPO collapse. Theranos ticked every box of the Too-Late Pivot pattern while still raising money.

The Failure Oracle gives every founder access to that pattern library — in real time, against their own live metrics.

---

## What It Does

Enter 11 metrics. The Oracle runs a multi-step AI agent pipeline and returns:

- The specific failure pattern you're matching, with a confidence score
- A **risk banner** — CRITICAL / HIGH RISK / MODERATE — with estimated days to crisis
- A **crisis trajectory timeline** showing where you are between "signal first detectable" and "projected crisis"
- **Category intelligence** — survival rate across all documented cases in your pattern's category (e.g. "only 11% of Product-Market Fit failures survive")
- **Gemini's own reasoning** — the model's explanation of exactly which metrics are driving the match
- **Warning signals** already visible in your data, with how many days ago they first became detectable
- **Your metrics vs. the pattern's actual trigger thresholds** — not generic benchmarks, the exact documented danger zones
- The **survival playbook** — what every company that survived this pattern did differently, as numbered steps
- **Famous companies** that matched this exact pattern, with outcomes
- Historical outcome statistics across all documented cases

And separately, a **Decision Auditor** — describe any decision you're about to make, and the Oracle cross-references it against 100 failure patterns using deliberate reasoning.

---

## Demo Scenarios

Load any of these with one click. Results are deterministic because they're based on real historical data.

| Scenario | Real Metrics | Oracle Result |
|---|---|---|
| 💀 **Quibi (Apr 2020)** | $8.5M/mo burn, 22% churn, NPS 8, CAC $48K, LTV $12K | Product-Market Fit Mirage — ~95% match, **CRITICAL** |
| 🏢 **WeWork (Q3 2019)** | $22M/mo burn, 16% churn, 14,000 headcount, LTV:CAC 0.5x | Unit Economics failure — ~85% match, **CRITICAL** |
| 🩸 **Theranos (2015)** | 45% churn, NPS −42, $5.8M burn on $18K MRR | Too-Late Pivot — ~90% match, **CRITICAL** |
| ✅ **Healthy Startup** | 22% MRR growth, 3% churn, NPS 58, 18mo runway | No dangerous patterns detected |

---

## How the Agent Pipeline Works

```
 Browser
    │
    ▼
 FastAPI  ──────►  Google ADK Agent  (gemini-3-flash-preview)
                       │
                       ├─ Tool 1: analyze_startup_metrics
                       │     ├─► MongoDB Voyage AI voyage-4-large (primary)
                       │     │       └─ 1024-dim vector from 11 metrics
                       │     ├─► MongoDB Atlas Vector Search
                       │     │       └─ cosine similarity, 100 patterns
                       │     ├─► MongoDB MCP  (category enrichment)
                       │     │       └─ mongodb-mcp-server@1.9.0
                       │     └─► Gemini 3 Flash  (parallel scoring)
                       │             └─ confidence, signals, reasoning
                       │
                       ├─ Tool 2: challenge_pattern_match  (60–92% confidence)
                       │     └─► Gemini 3 Flash  (Challenger Agent)
                       │             └─ independent stress-test of Investigator's finding
                       │
                       ├─ Tool 3: fetch_category_benchmarks
                       │     └─► MongoDB aggregation pipeline
                       │             └─ avg survival rate, worst pattern
                       │
                       └─ Tool 4: save_analysis_report
                             └─► markdown report written to disk
```

**Step 1 — Embed.** The 11 metrics are composed into a natural-language description and embedded into a 1024-dimensional vector. Primary model: MongoDB Voyage AI `voyage-4-large` (1024-dim, asymmetric retrieval). Fallback: Google `text-embedding-004` via Vertex AI, padded to 1024-dim via `_adjust_dimension`.

**Step 2 — Vector Search.** The embedding queries MongoDB Atlas Vector Search (`$vectorSearch`, cosine similarity) across 100 failure pattern narratives. This finds patterns that *conceptually* match the startup's situation — semantic matching that pure numeric thresholds miss. Quibi's metrics find "Product-Market Fit Mirage" because the narrative matches, not because a churn threshold fires.

**Step 3 — MCP Context Fetch.** The `mongodb-mcp-server` (persistent background stdio process, started at app startup) fetches all patterns from the top candidate's category. This gives the agent context about how the startup sits within the broader category landscape.

**Step 4 — Parallel Gemini 3 Flash Scoring.** Up to 5 candidate patterns are scored in parallel by Gemini 3 Flash (`thinking_budget=0` for speed). Each call evaluates metric-trigger alignment, detected warning signals, days to crisis, and match confidence. Parallel execution brings total response time to 2–4 seconds.

**Step 5 — Re-evaluation Loop.** If the best match scores below 70%, the agent re-queries MongoDB MCP for a broader pattern set and runs a second round of scoring. This is genuine agent behaviour — a second pass on low-confidence results, not a fallback.

**Step 6 — Challenger Agent.** If a pattern is detected at 60–92% confidence, the ADK agent calls `challenge_pattern_match` — a second Gemini 3 Flash instance with a deliberately skeptical prompt. It independently scores the same pattern looking for counter-evidence ("which metrics CONTRADICT this match?"). If the Challenger's confidence differs by more than 10pp, it issues a DISPUTE verdict. Both the verdict and the strongest counter-metric appear in the result UI. This is genuine multi-agent adversarial verification, not a UI layer.

**Step 7 — Category Benchmarks.** The ADK agent calls `fetch_category_benchmarks` — a MongoDB aggregation pipeline that computes the average survival rate, total documented cases, and most dangerous pattern across the matched category. This context appears directly in the result UI.

**Step 8 — Alert or Safe.** Patterns above 60% confidence fire a full alert. Below 60%: safe result. The ADK agent saves a structured markdown report to disk regardless.

---

## Real-Time Streaming

The `/api/metrics/analyze/stream` endpoint streams every agent step as Server-Sent Events. The browser terminal shows the pipeline executing live:

```
> Oracle pipeline initializing — Gemini 3 Flash ADK Agent → Atlas Vector Search → MongoDB MCP → Gemini 3 Flash scoring...
🔢 Generating 1024-dimensional embedding from 11 startup metrics...
✅ 1024-dimensional embedding ready — stored in MongoDB Atlas for vector similarity search.
🔍 Hybrid retrieval: MongoDB Atlas Vector Search (cosine similarity) + Atlas Search (BM25) — merging via Reciprocal Rank Fusion...
✅ Vector Search + BM25 RRF: 10 vector + 8 BM25 results merged → top 5 candidates
✅ Candidates: Product-Market Fit Mirage, Hidden Churn Spiral, Premature Scaling, Capital Efficiency Collapse, Talent Drain Crisis
🗄️  MongoDB MCP → find('failure_patterns', {category: 'product_market_fit'}, limit=10)
✅ MCP returned 10 'product_market_fit' patterns for context.
🤖 Gemini 3 Flash scoring 5 candidates in parallel...
⚡ Evaluating [1/5] Product-Market Fit Mirage...
⚡ Evaluating [2/5] Hidden Churn Spiral...
⚡ Evaluating [3/5] Premature Scaling...
⚡ Evaluating [4/5] Capital Efficiency Collapse...
⚡ Evaluating [5/5] Talent Drain Crisis...
📊  → Product-Market Fit Mirage: 95% match score
📊  → Hidden Churn Spiral: 41% match score
📊  → Premature Scaling: 38% match score
📊  → Capital Efficiency Collapse: 31% match score
📊  → Talent Drain Crisis: 22% match score
⚠️  Pattern confirmed: Product-Market Fit Mirage at 95% match score. Generating full alert...
⚖️  Challenger Agent independently evaluating Investigator's finding...
✅  Challenger Agent CONFIRMS at 92% (Δ3pp) — CAC:LTV inversion is the dominant signal; I find no structural counter
📊  Oracle Score: 18/100 (CRITICAL)
```

If Gemini 3 is rate-limited during scoring, the terminal emits an amber notice and falls back transparently to Vertex AI 2.5 Flash.

---

## Result UI — What the Alert Shows

Every alert result includes, in order:

**Risk banner** — CRITICAL (≥88%) / HIGH RISK (≥75%) / MODERATE, with a pulsing animation at CRITICAL level and estimated days to crisis.

**Crisis trajectory timeline** — a horizontal track showing:
- `◆ Signal first detectable` — when the earliest warning signal would have been visible (e.g. "~90 days ago")
- `▲ TODAY` — your current position on the timeline
- `⚠ Projected crisis` — estimated days remaining if no action taken

The track is colour-coded by urgency: grey for the past warning window, deepening red toward the crisis point. This makes the abstract "days to crisis" number visceral.

**Category intelligence** — pulled from a live MongoDB aggregation: "In the Product-Market Fit category, only 11% survival rate across all curated cases. Most fatal pattern: Hidden Churn Spiral."

**Gemini's match reasoning** — the model's own explanation of *why* the metrics match this pattern. Not a template. An actual sentence like "Your $48K CAC against a $12K LTV means you're spending 4x to acquire customers who will never pay you back — the same structural trap that killed Quibi."

**Your metrics vs. pattern trigger thresholds** — a table showing your actual value alongside the documented danger threshold for that specific pattern (e.g. Monthly Churn: 22% / Pattern trigger: >8% / ✗), not generic benchmarks.

**Warning signals** — each signal from the pattern library evaluated against the current snapshot, with how many days ago it first became detectable. Status: DETECTED / EMERGING / NOT_YET.

**Historical outcomes** — animated counters: failed, survived, total cases.

**Survival playbook** — the exact steps used by every startup that survived this pattern, rendered as numbered items with a staggered slide-in animation.

**Famous companies** — real companies that matched this exact pattern, with outcome and detail.

---

## Decision Auditor

Before you make a major decision, ask the Oracle.

Type: *"Should we hire 20 more engineers this quarter?"*

The Oracle fetches all 100 patterns via MongoDB MCP, then uses Gemini 3 Flash with `thinking_budget=1024` — deliberate reasoning, not fast scoring — to evaluate the decision. During the wait, the button cycles: *"Gemini 3 Flash is reasoning… → Cross-referencing 100 patterns… → Evaluating risk vectors…"*

The result shows:
- Risk level (CRITICAL / HIGH / MEDIUM / LOW)
- The linked failure pattern as a card — name, category, survival rate, famous example
- Key differentiator: what separates the founders who made it from those who didn't
- Recommendation: specific and cited, referencing the relevant pattern
- Full analysis rationale

---

## Additional Features

**Live Health Pulse.** As you type metrics into the form, three derived ratios update in real time: Net Burn Multiple (burn / net new MRR), LTV:CAC ratio, and runway. Colour-coded healthy/warning/danger.

**Live field validation.** Form inputs for churn rate, MRR growth, NPS, and runway turn red/amber/green borders as you type, compared against SaaS benchmarks.

**Monthly tracking.** Every analysis is saved to localStorage. The tracking panel shows a sparkline SVG chart of your confidence score over time (red dots for alerts, green for safe), plus a row-by-row history with trend arrows.

**Share via URL.** The "Share Analysis" button copies a URL that encodes all 11 metric values as query parameters. Opening the link pre-fills the form and auto-runs the analysis.

**Stripe integration.** Connect your Stripe secret key to import live MRR, churn rate, and customer count directly — no manual entry.

**Pattern library.** Browse all 100 patterns filtered by category. Each card shows pattern ID, category badge, survival rate mini-bar, failure/survival counts, and expands to show the full narrative, warning signals, survival playbook, and known cases.

**Light / dark theme.** Persisted to localStorage, applied before first render to avoid flash.

**Keyboard shortcuts.** `Escape` closes modals. `Cmd/Ctrl+Enter` submits the analysis form from anywhere on the page.

**Download report.** Generates a formatted markdown report from the current result, including all signals, metric table, playbook, and famous failures.

---

## MongoDB Integration

MongoDB is genuinely in the critical path — not a side store.

**Atlas Vector Search.** Each of the 100 failure pattern narratives is embedded at seed time into a 1024-dimensional vector using MongoDB Voyage AI `voyage-4-large` (falling back to `text-embedding-004` padded to 1024-dim). At query time, `$vectorSearch` (cosine similarity, `vector_index`) retrieves semantically similar patterns. This is why Quibi's metrics find "Product-Market Fit Mirage" — the narrative matches semantically, not because a numeric threshold fires.

**MongoDB MCP — verifiable in production.** A persistent `mongodb-mcp-server@1.9.0` process starts at app startup over stdio. Three API endpoints use MCP as the primary data access layer:
- `GET /api/patterns/` → MCP `find` — every response includes `"source": "mcp"`
- `GET /api/patterns/{id}` → MCP `find_one`
- `POST /api/audit/evaluate` → MCP `find` fetches all 100 patterns before Gemini evaluation

The `"source": "mcp"` field in every patterns response is verifiable proof.

**Aggregation pipeline.** The numeric fallback uses a `$addFields` + `$sort` aggregation that scores each pattern by how many trigger conditions fire (churn, burn multiple, NPS, LTV:CAC, runway), ensuring the most relevant candidates are always returned. The `fetch_category_benchmarks` ADK tool runs a `$group` aggregation to compute survival statistics per category.

**Motor fallback.** If MCP is unavailable, every endpoint falls back to Motor (the async MongoDB driver) transparently. The app logs which path was taken at every call.

**Flexible schema.** Each of the 100 patterns has a different trigger condition structure — some have churn thresholds, others burn multiples, others NPS bounds. MongoDB stores these as heterogeneous nested documents without schema enforcement.

---

## Google ADK Agent

Google ADK (`google-adk`) is the official open-source agent framework from Google — the code-first developer layer that underpins Google Cloud Agent Builder. The `/api/metrics/analyze` endpoint routes through a formal ADK agent:

```python
from google.adk.agents import Agent
from google.adk.tools import FunctionTool

agent = Agent(
    name="failure_oracle",
    model="gemini-3-flash-preview",
    tools=[
        FunctionTool(analyze_startup_metrics),    # embed + vector search + Gemini score
        FunctionTool(challenge_pattern_match),    # Challenger Agent — second Gemini 3 instance
        FunctionTool(fetch_category_benchmarks),  # MongoDB aggregation for category stats
        FunctionTool(save_analysis_report),       # write markdown report to disk
    ],
)
```

The agent receives the startup's metrics and orchestrates four tools: `analyze_startup_metrics` runs the full Atlas Vector Search + Gemini scoring pipeline; if a pattern is detected at 60–92% confidence, `challenge_pattern_match` spins up a second Gemini 3 Flash instance that independently stress-tests the finding; `fetch_category_benchmarks` enriches the result with MongoDB aggregation-derived survival statistics; `save_analysis_report` persists the findings to disk. Four tools. Real orchestration with adversarial verification.

The SSE streaming endpoint exposes the same underlying pipeline with real-time step-by-step visibility.

Gemini 3 Flash (`gemini-3-flash-preview`) is the primary model for all generation — ADK orchestration, parallel pattern scoring, and decision auditing. Vertex AI Gemini 2.5 Flash is the fallback for reliability under load.

---

## Tech Stack

| Technology | Role |
|---|---|
| **Gemini 3 Flash (`gemini-3-flash-preview`)** | ADK agent orchestration, parallel pattern scoring, decision auditing |
| **Google ADK (`google-adk`)** | Official Google agent framework (the code-first layer of Google Cloud Agent Builder) — 4 FunctionTools (incl. Challenger Agent), `Runner`, `InMemorySessionService` |
| **Gemini 2.5 Flash (Vertex AI)** | Fallback for generation under rate limits |
| **text-embedding-004 (Vertex AI)** | Fallback embeddings — padded to 1024-dim via `_adjust_dimension` |
| **MongoDB Atlas** | Primary data store — 100 failure patterns, flexible schema |
| **MongoDB Atlas Vector Search** | Semantic retrieval via cosine similarity (`vector_index`, READY) |
| **MongoDB MCP (`mongodb-mcp-server@1.9.0`)** | Persistent stdio MCP server — 28 tools, in critical path |
| **FastAPI + Motor** | Async Python backend, parallel scoring via `asyncio.gather` |
| **Server-Sent Events** | Real-time streaming of every agent step to the terminal |
| **Google Cloud Run** | Serverless deployment, auto-scaling |

---

## Project Structure

```
oracle/
├── backend/
│   ├── main.py              # FastAPI app — starts MCP + ADK at startup
│   ├── config.py            # Settings (pydantic-settings + .env)
│   ├── db/
│   │   ├── connection.py    # Motor async client
│   │   ├── schemas.py       # Pydantic models (PatternMatch, AlertResponse, etc.)
│   │   └── seed.py          # Seeds 100 patterns + generates embeddings
│   ├── routes/
│   │   ├── metrics.py       # POST /api/metrics/analyze  — routes through ADK agent
│   │   ├── stream.py        # POST /api/metrics/analyze/stream  — SSE
│   │   ├── audit.py         # POST /api/audit/evaluate  — MCP + Gemini 3 reasoning
│   │   ├── patterns.py      # GET /api/patterns/  — MCP-backed library browser
│   │   └── integrations.py  # POST /api/integrations/stripe
│   └── services/
│       ├── gemini.py        # Gemini 3 Flash primary, Vertex AI 2.5 fallback
│       ├── adk_runner.py    # ADK agent with 4 FunctionTools (incl. Challenger Agent)
│       ├── mcp_client.py    # Persistent MCP stdio connection manager
│       ├── pattern_matcher.py  # Vector search + parallel Gemini scoring
│       ├── auditor.py       # MCP fetch + Gemini 3 deliberate reasoning
│       └── output_writer.py # Markdown report writer
├── frontend/
│   ├── index.html           # Single-page app
│   ├── style.css            # Light/dark theme, all component styles
│   └── app.js               # All UI logic — streaming, rendering, charts
├── data/
│   └── failure_patterns_seed.json  # 100 patterns, F-001 to F-100
├── tests/
│   └── test_suite.py        # 42-test suite — saves HTML + JSON reports
└── Dockerfile               # Python 3.11 + Node.js 20 + mongodb-mcp-server
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/metrics/analyze` | ADK agent analysis — full pattern alert response |
| `POST` | `/api/metrics/analyze/stream` | Same pipeline, SSE streaming |
| `POST` | `/api/metrics/extract-metrics` | Extract 11 metrics from any free-form text (Gemini 3) |
| `POST` | `/api/metrics/watch` | Register startup for background monitoring (6h interval) |
| `GET` | `/api/metrics/watch/{name}` | Get monitoring status + last result for a startup |
| `POST` | `/api/metrics/watch/{name}/check-now` | Trigger immediate re-analysis |
| `POST` | `/api/metrics/slack-share` | Post current Oracle alert to Slack webhook |
| `POST` | `/api/audit/evaluate` | Decision audit — MCP fetch + Gemini 3 reasoning |
| `POST` | `/api/integrations/stripe` | Import MRR/churn from Stripe key |
| `GET` | `/api/patterns/` | All 100 patterns (MCP-backed, `"source":"mcp"`) |
| `GET` | `/api/patterns/{id}` | Single pattern detail (MCP `find_one`) |
| `GET` | `/api/health` | Status — MCP, ADK, pattern count, model config |

Health check response:
```json
{
  "status": "ok",
  "service": "failure-oracle",
  "mongodb": "connected",
  "mcp": "ready",
  "mcp_tools": 28,
  "adk_agent": "initialized",
  "pattern_count": 100,
  "gemini_active": "gemini-3-flash-preview",
  "gemini3_chain": ["gemini-3-flash-preview", "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.1-flash-lite-preview"],
  "gemini_fallback": "gemini-2.5-flash (vertex-ai)",
  "embedding_model": "voyage-4-large (1024-dim)",
  "embedding_source": "MongoDB Voyage AI"
}
```

---

## The Pattern Library

100 curated failure archetypes across 12 categories, synthesized from public sources: YC batch post-mortems, CB Insights startup failure reports, Paul Graham and Ben Horowitz essays, Sequoia / a16z / Bessemer research, and public founder post-mortems (Quibi, Theranos, WeWork, Homejoy, Jawbone, Juicero, Vine). Each pattern's failure/survival counts and trigger thresholds are derived from these public records.

| Category | Count | What's inside |
|---|---|---|
| Go-To-Market | 14 | Enterprise trap, channel concentration, outbound ceiling, sales-led death spiral... |
| Team | 12 | Co-founder conflict, burnout, talent density collapse, remote culture fragmentation... |
| Unit Economics | 12 | CAC > LTV, burn multiple spiral, free-tier economics, marketplace liquidity trap... |
| Product-Market Fit | 11 | PMF mirage, market timing failure, distribution without retention... |
| Premature Scaling | 6 | Hidden churn, international expansion trap, hiring ahead of revenue... |
| Fundraising | 8 | Runway optimism bias, bridge round death spiral, valuation overhang... |
| Competition | 8 | Platform dependency, incumbent awakening, category harvested by big tech... |
| Product | 8 | Feature creep, complexity spiral, parity treadmill... |
| Regulatory | 6 | Regulatory blindside, data privacy trap, IP litigation collapse... |
| Technical Debt | 6 | Tech debt collapse, velocity collapse, premature microservices... |
| Platform Risk | 5 | Algorithm dependency, app store hostage, API deprecation cliff... |
| Pivot | 4 | Pivot without signal, too-late pivot, pivot fatigue... |

Each pattern contains: narrative, trigger conditions (churn, burn multiple, NPS, LTV:CAC, runway thresholds), warning signals with `days_before_failure` data, survival playbook, famous failures, and historical outcome statistics (failure count, survival count, survival rate).

---

## Setup

### Prerequisites

```
Python 3.11+
Node.js 20+  (for MongoDB MCP server)
MongoDB Atlas account  — cloud.mongodb.com (free M0 tier works)
Google Cloud project   — console.cloud.google.com
Gemini API key         — aistudio.google.com/apikey
```

### Install

```bash
pip install -r requirements.txt
npm install -g mongodb-mcp-server@1.9.0
```

### Configure

```bash
cp .env.example .env
```

```env
MONGODB_URI=mongodb+srv://...         # Atlas → Connect → Drivers
GOOGLE_PROJECT_ID=your-project-id    # GCP project with Vertex AI enabled
GOOGLE_LOCATION=us-central1
GEMINI_API_KEY=AIza...               # Google AI Studio → Get API key
GEMINI_MODEL=gemini-2.5-flash        # Vertex AI fallback model
```

### Seed the pattern library

```bash
python -m backend.db.seed
# Generating embeddings for 100 patterns via Voyage AI (batched)...
# [OK] Seeded 100 failure patterns with 1024-dim embeddings
# [OK] Atlas Vector Search index created (vector_index, cosine)
```

> Requires application default credentials: `gcloud auth application-default login`

### Run

```bash
uvicorn backend.main:app --reload --port 8080
# [OK] MongoDB connected (Motor)
# [OK] MongoDB MCP server ready (28 tools)
# [OK] Failure Oracle ADK agent initialized (model: gemini-3-flash-preview)
```

Open `http://localhost:8080`. Click the Quibi preset to see the pipeline run.

### Test

```bash
python tests/test_suite.py --base http://localhost:8080
# Runs 42 tests across 9 categories
# Saves timestamped HTML + JSON reports to tests/reports/
```

---

## Deploy to Cloud Run

The Dockerfile installs Python 3.11, Node.js 20, and `mongodb-mcp-server` globally — everything needed for the full pipeline in a single container.

```bash
docker build -t oracle-agent .

docker tag oracle-agent gcr.io/PROJECT_ID/oracle-agent
docker push gcr.io/PROJECT_ID/oracle-agent

gcloud run deploy oracle-agent \
  --image gcr.io/PROJECT_ID/oracle-agent \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars MONGODB_URI=...,GOOGLE_PROJECT_ID=...,GEMINI_API_KEY=...
```

---

## Key Implementation Notes

**Why `MDB_MCP_CONNECTION_STRING` instead of `--connectionString`?** MongoDB Atlas URIs contain `?` and `&` characters that shell argument parsers interpret as special characters. Passing the URI as an environment variable avoids the parsing issue entirely.

**Why does MCP return `<untrusted-user-data-UUID>` tags?** The `mongodb-mcp-server` wraps query results in security tags to prevent prompt injection. The actual JSON data is between the *second* pair of opening/closing tags — the first occurrence appears in a warning message. `_parse_mcp_content()` in `mcp_client.py` handles this correctly.

**Why `thinking_budget=0` for scoring but `thinking_budget=1024` for auditing?** Pattern scoring needs to be fast (parallel, 2-4s total for 5 candidates). Decision auditing is a deliberate one-shot call where reasoning quality matters more than latency. Different call profiles deserve different model configurations.

**Why a persistent MCP process?** Starting `mongodb-mcp-server` per request adds 2-3 seconds of Node.js startup overhead. A single background asyncio task owns the stdio connection for the lifetime of the FastAPI process, with an async lock protecting concurrent access.

---

## License

Apache 2.0

Built with Gemini 3 Flash · Google ADK · MongoDB Atlas Vector Search · MongoDB MCP · Vertex AI · Cloud Run
