# The Failure Oracle

> 90% of startups fail for the same documented reasons. The warning signals appear 3–6 months before the crisis. Most founders never see them coming.

The Failure Oracle is a multi-agent AI system that watches your startup's live metrics and fires an early warning when your trajectory matches a documented failure pattern — with the exact survival playbook used by companies that made it through.

**Live demo:** https://oracle-38381883054.us-central1.run.app

---

## The Problem

When a Sequoia partner looks at your metrics and says *"I've seen this before"*, they're pattern-matching against a mental library built from hundreds of failures. That library took 20 years to build. Most founders don't have access to it.

The patterns are documented. The signals appear months in advance. Quibi's month-4 metrics matched a known failure signature weeks before the first press story ran. WeWork's unit economics matched a pattern seen dozens of times in marketplace companies before the IPO collapse. Theranos ticked every box of the Too-Late Pivot pattern while still raising money.

The Failure Oracle gives every founder access to that pattern library — in real time, against their own live metrics.

---

## What It Does

Enter 11 metrics. The Oracle runs a 3-agent AI pipeline and returns:

- **Pattern match** — which of 100 documented failure patterns your metrics most closely resemble, with a similarity score (0–100%) and the trigger conditions that fired
- **Oracle Score** — a transparent 0–100 composite health score you can audit line-by-line: see every penalty (churn, burn multiple, runway, LTV:CAC, pattern match) and bonus (NPS, growth) with your actual numbers plugged in
- **Why this pattern matched** — a trigger breakdown showing exactly which pattern conditions your metrics crossed (threshold vs. current value)
- **Risk banner** — CRITICAL / HIGH RISK / MODERATE with estimated days to crisis
- **Escape Plan** — the minimum metric changes to drop below the 60% danger threshold. Pure deterministic algebra on stored thresholds, not AI advice. "Reduce monthly churn from 8.2% to 5.5%" — reproducible every run
- **Failure Cascade Graph** — MongoDB `$graphLookup` traverses a directed failure-mode state machine up to 3 hops: what failure fires next, in how many days, at what cumulative probability. Cascade probabilities self-improve via Bayesian blending as real cases are observed
- **Cascade Intervention Optimizer** — for each cascade link, the exact minimum metric change to break it before the failure propagates
- **Survival Playbook** — numbered steps used by every startup that survived this specific pattern
- **Cocktail Alert** — when 2+ patterns exceed 60% confidence simultaneously, compound survival is modeled as `max(2%, min(rates) × 0.5^(n−1))`
- **Challenger Agent verdict** — a second independent Gemini 3 Flash instance re-evaluates the match with deliberate skepticism. If its confidence diverges from the Investigator's by >10pp, a DISPUTE is flagged
- **Trajectory** — if you've run the Oracle before on the same startup, it computes Oracle Score velocity (e.g., "deteriorating ~3.2 pts/run") and projects your risk score and Oracle Score forward 3 months via linear regression
- **Uncharted Territory** — if your metrics don't closely resemble any known pattern (<40% best match), the Oracle is honest about it rather than forcing a low-confidence result
- **Cohort percentile** — `$bucket` + `$facet` shows your Oracle Score vs. all analyzed startups at the same industry and stage
- **Decision Auditor** — describe any decision before making it; the Oracle cross-references it against 100 patterns using Gemini 3 Flash with `thinking_budget=1024`

---

## Demo Scenarios

Load any of these with one click.

| Scenario | Real Metrics | Oracle Result |
|---|---|---|
| 💀 **Quibi (Apr 2020)** | $8.5M/mo burn, 22% churn, NPS 8, CAC $48K, LTV $12K | Product-Market Fit Mirage — ~95% match, **CRITICAL** |
| 🏢 **WeWork (Q3 2019)** | $22M/mo burn, 16% churn, 14,000 headcount, LTV:CAC 0.5x | Unit Economics failure — ~85% match, **CRITICAL** |
| 🩸 **Theranos (2015)** | 45% churn, NPS −42, $5.8M burn on $18K MRR | Too-Late Pivot — ~90% match, **CRITICAL** |
| ⚡ **HighVelocity AI** | 38% MoM growth, 7% churn, NPS 68, 8.2x LTV:CAC, 9mo runway | Mixed signals → designed to trigger Challenger **DISPUTE** |
| ✅ **Healthy Startup** | 22% MRR growth, 3% churn, NPS 58, 18mo runway | No dangerous patterns detected |

---

## Why This Isn't Just Semantic Search

The architecture might look like: embed metrics → find nearest pattern → ask Gemini to explain. That description is half-true. Here's what actually happens that pure semantic search doesn't do:

1. **Hybrid retrieval, not just vectors.** Atlas Vector Search (cosine) runs in parallel with Atlas Search (BM25), merged via Reciprocal Rank Fusion. RRF outperforms either mode alone on heterogeneous narrative + numeric data.
2. **Structured trigger evaluation.** Every pattern has explicit numeric thresholds (churn > X%, burn multiple > Y, NPS < Z). The agent evaluates your metrics against those thresholds and surfaces which fired — independent of semantic similarity. A trigger breakdown row in the UI shows each condition with a ✗ (crossed) or ✓ (safe).
3. **Adversarial multi-agent verification.** The Challenger Agent is a second Gemini 3 Flash instance with an explicitly skeptical prompt: look for *counter-evidence*, not confirmation. If it disagrees by >10pp, DISPUTE is flagged with the confidence delta and strongest counter-evidence visible in the UI.
4. **Re-evaluation loop on low confidence.** If the top match scores below 70%, the agent re-queries MongoDB MCP for a broader candidate set and scores again. That's genuine agent behavior: observe, plan, act, iterate.
5. **Transparent formula, not a black box.** The Oracle Score and Escape Plan are both deterministic algebra — no AI involved. Every number is reproducible. The "Audit formula" button shows each component with your actual values plugged in.
6. **Self-improving cascade graph.** Transition probabilities start as research estimates. As real-world A→B pattern transitions are observed via Change Streams, probabilities update via Bayesian blend: `p = 0.3 × initial + 0.7 × (observed / total_starts)`. The cascade learns.

---

## Dual-Model Architecture

The Oracle uses two different models intentionally — each assigned to the task it does best:

| Model | Role | Why |
|---|---|---|
| **Vertex AI Gemini 2.5 Flash** | Primary pattern scorer | `thinking_budget=0` for parallel speed (2–4s total for 5 candidates). Consistent latency SLA. Also used for decision auditing with `thinking_budget=1024` for deeper reasoning. |
| **Gemini 3 Flash (`gemini-3-flash-preview`)** | All 3 ADK agents (Investigator, Challenger, Reporter) | Sharper multi-step reasoning and instruction following for adversarial analysis. Accessed via paid Gemini API (Gemini 3 Flash not yet available on Vertex AI). |

If Vertex AI is unavailable, scoring falls back to Gemini 3. If Gemini 3 quota is exhausted, the ADK agents fall back to the Gemini 3 fallback chain (`gemini-3.5-flash → gemini-3.1-flash-lite → gemini-3.1-flash-lite-preview`).

---

## How the Agent Pipeline Works

```
Browser
   │
   ▼
FastAPI  ──────►  Google ADK SequentialAgent
                      │
                      ├─ Agent 1: Investigator  (gemini-3-flash-preview)
                      │     ├─► Voyage AI voyage-4-large  →  1024-dim embedding
                      │     ├─► Atlas Vector Search (cosine) + Atlas Search (BM25)
                      │     │       └─ merged via Reciprocal Rank Fusion → top 5
                      │     ├─► MongoDB MCP  → category context enrichment
                      │     ├─► Vertex AI Gemini 2.5 Flash  →  parallel scoring
                      │     │       └─ confidence, signals, reasoning (thinking_budget=0)
                      │     └─► re-evaluation loop if best score < 70%
                      │
                      ├─ Agent 2: Challenger  (gemini-3-flash-preview)
                      │     └─► second independent Gemini 3 Flash call
                      │             └─ adversarial prompt: find counter-evidence
                      │             └─ returns CONFIRM or DISPUTE + Δpp
                      │
                      └─ Agent 3: Reporter  (gemini-3-flash-preview)
                            ├─► MongoDB aggregation → category benchmarks
                            └─► structured markdown report saved to disk

After ADK pipeline:
   ├─► Oracle Score  (deterministic algebra, 0-100)
   ├─► Oracle Score Breakdown  (per-component audit)
   ├─► Trigger Breakdown  (which conditions crossed)
   ├─► Escape Plan  (minimum changes to drop below 60%)
   ├─► Cascade Graph  ($graphLookup, ACID transaction write)
   └─► Trajectory  (velocity from prior snapshots)
```

**Step 1 — Embed.** The 11 metrics are converted to a natural-language description and embedded into a 1024-dim vector. Primary: MongoDB Voyage AI `voyage-4-large` (asymmetric retrieval — "query" encoding for searches, "document" encoding for stored patterns). Fallback: Google `text-embedding-004` via Vertex AI, padded to 1024-dim via `_adjust_dimension`.

**Step 2 — Hybrid retrieval.** Atlas Vector Search (cosine, `$vectorSearch`) and Atlas Search (BM25, `$search`) run in parallel via `asyncio.gather`. Results merged via Reciprocal Rank Fusion. This handles cases where either retrieval alone misses — semantic search catches conceptual matches, BM25 catches term overlap.

**Step 3 — MCP context.** The `mongodb-mcp-server` (persistent background stdio process) fetches all patterns in the top candidate's category for broader context.

**Step 4 — Parallel Vertex AI scoring.** Up to 5 candidate patterns are scored simultaneously by **Vertex AI Gemini 2.5 Flash** (`thinking_budget=0`). Each call evaluates trigger alignment, detected warning signals, days to crisis, and match confidence. Parallel via `asyncio.gather` — total scoring time 2–4s.

**Step 5 — Re-evaluation loop.** If best match < 70% confidence, the agent re-queries MongoDB MCP for a broader pattern set and runs a second scoring pass. Genuine agent iteration, not a single-shot retrieval.

**Step 6 — Challenger Agent.** If a pattern is detected at ≥60% confidence, a second Gemini 3 Flash call with a skeptical prompt looks for counter-evidence. Delta >10pp → DISPUTE. Both scores + confidence gap (Δpp) appear in the UI side by side.

**Step 7 — Post-pipeline outputs.** Oracle Score (transparent formula, auditable line-by-line), trigger breakdown, Escape Plan (deterministic algebra), Cascade Graph (`$graphLookup`, written via ACID transaction), trajectory velocity from prior snapshots.

**Step 8 — Alert or Uncharted.** Patterns ≥60% confidence fire a full alert. Patterns <40% best match → Uncharted Territory (honest uncertainty, no forced match). Between 40–60% → low-signal, no alert.

---

## Real-Time Streaming

Every agent step streams to the browser terminal via SSE:

```
🤖 Oracle Pipeline starting — ADK SequentialAgent: Investigator → Challenger → Reporter
🔢 Generating 1024-dim embedding via MongoDB Voyage AI voyage-4-large...
✅ Embedding ready — querying MongoDB Atlas Vector Search...
🔍 Hybrid retrieval: Atlas Vector Search + BM25 → Reciprocal Rank Fusion...
✅ Vector Search + BM25 RRF: 10 vector + 8 BM25 results merged → top 5 candidates
✅ Candidates: Product-Market Fit Mirage, Hidden Churn Spiral, Premature Scaling...
🗄️  MongoDB MCP → find('failure_patterns', {category: 'product_market_fit'}, limit=10)
✅ MCP returned 10 'product_market_fit' patterns for context.
🤖 Vertex AI Gemini 2.5 Flash scoring 5 candidates in parallel (thinking_budget=0)...
📊  → Product-Market Fit Mirage: 95% match score
📊  → Hidden Churn Spiral: 41% match score
⚠️  Pattern confirmed: Product-Market Fit Mirage at 95%. Handing off to Challenger...
✅  Challenger CONFIRMS at 92% (Δ3pp) — CAC:LTV inversion is the dominant signal
🔗  $graphLookup cascade: 3 failure mode(s), depth 2 — worst case 135d to crisis
📊  Oracle Score: 18/100 (CRITICAL)
🔓  Escape Plan: 4 ranked interventions — combined confidence drop: −44pp
💾  Reporter: report saved — Oracle pipeline complete (3 agents, 1 report)
```

---

## Result UI — What the Alert Shows

**Oracle Score + Band Legend**
A 0–100 composite health score (100 = perfect, 0 = crisis) with a live band legend: STRONG (75–100) · WATCH (50–74) · WARNING (25–49) · CRITICAL (0–24). Click "Audit formula ▾" to expand a table showing every component with your actual numbers: base 100, minus pattern match penalty, churn penalty, LTV:CAC penalty, runway penalty, burn multiple penalty, plus NPS and growth bonuses.

**Trend Delta + Trajectory**
If you've run the Oracle before on the same startup name, the trend badge shows Oracle Score velocity ("↑ Risk increasing — Oracle Score −8, deteriorating ~4 pts/run"). The forecast panel projects both pattern risk % and Oracle Score at +1/+2/+3 months via linear regression over your history.

**Trigger Breakdown**
A "Why this pattern matched" section showing each of the pattern's specific trigger conditions: metric name, threshold, your current value, and ✗ (threshold crossed = drives the match) or ✓ (safe). Computed deterministically from stored thresholds — no AI.

**Challenger Panel**
Shows Investigator vs. Challenger confidence side by side with the Δpp gap badge. CONFIRM = both agents agree (within 10pp). DISPUTE = Challenger found meaningful counter-evidence. The strongest counter-evidence is shown as text. Audio debrief available.

**Escape Plan**
Ranked interventions to drop pattern match below 60%. Each shows: metric, current value, target value, exact change needed, difficulty (easy/medium/hard), and estimated confidence drop. Combined top-3 drop shown.

**Failure Cascade Graph**
SVG node-edge graph from `$graphLookup`. Each edge shows transition probability (Bayesian-blended once real cases are observed: "72%→68% after 3 cases"), trigger condition, and mechanism. Cascade Intervention Optimizer below shows per-link interventions.

**Uncharted Territory**
When best match < 40%, shows a yellow card: "Your metrics don't closely resemble any of the 100 documented failure patterns (best match: 34% with X). This could mean you're in unexplored territory — treat as low-confidence and re-run monthly."

---

## Oracle Score Formula

The Oracle Score is deterministic and transparent — no ML, fully auditable:

```
Start at 100
− match_confidence × 60      (pattern match penalty — up to −60pp)
− min((churn% − 5) × 2, 30)  (churn > 5% threshold)
− min((3 − ltv_cac) × 5, 15) (LTV:CAC < 3x)
− min((12 − runway) × 1.5, 15) (runway < 12 months)
− min((burn_mult − 2) × 2, 10) (burn multiple > 2x)
+ min((nps − 30) / 7, 10)    (NPS > 30 bonus)
+ min((growth − 0.10) × 50, 5) (MoM growth > 10% bonus)
```

Bands: STRONG ≥75 · WATCH ≥50 · WARNING ≥25 · CRITICAL <25

The "Audit formula" button in the UI shows this calculation with your actual values substituted in.

---

## MongoDB Integration

MongoDB is in the critical path across 8 distinct capabilities:

**1. Atlas Vector Search** — 1024-dim cosine similarity across 100 pattern narratives, `$vectorSearch` with stage/month filter.

**2. Atlas Search (BM25)** — full-text keyword search, merged with vector results via Reciprocal Rank Fusion.

**3. MongoDB MCP** — `mongodb-mcp-server@1.9.0` persistent stdio process. Three API endpoints use MCP as primary:
- `GET /api/patterns/` → MCP `find` — response includes `"source": "mcp"` as proof
- `GET /api/patterns/{id}` → MCP `find_one`
- `POST /api/audit/evaluate` → MCP `find` fetches all 100 patterns before Gemini evaluation

**4. `$graphLookup` Cascade** — each `failure_patterns` document has a `transitions` array encoding directed edges to downstream patterns (`trigger_metric`, `trigger_threshold`, `probability`, `avg_days`, `observed_count`, `initial_probability`). `$graphLookup` traverses this state machine up to 3 hops.

**5. ACID Transactions** — `POST /api/cascade/analyze` atomically writes to 3 collections: `cascade_interventions`, `telemetry_events`, `failure_patterns.$inc.times_triggered`. Uses `async with session.start_transaction()`.

**6. Change Streams (self-improving)** — watches `startup_analyses` for A→B pattern transitions within 90 days. On each observed transition: increments `observed_count`, recomputes Bayesian blend `0.3 × initial + 0.7 × (observed / total_starts)`. Cascade probabilities auto-calibrate. The UI shows when a probability has been updated: "72%→68% (3 cases)".

**7. `$bucket` + `$facet` Cohort Intelligence** — single query running 5 sub-pipelines: score distribution, alert rate, top patterns, cohort averages, survivor stats. Returns your exact percentile rank.

**8. Aggregation pipelines** — `fetch_category_benchmarks` uses `$group` for survival stats per category. Numeric fallback uses `$addFields + $sort` to score patterns by trigger conditions fired.

---

## Google ADK Agent

Google ADK (`google-adk`) orchestrates the 3-agent pipeline:

```python
from google.adk.agents import Agent, SequentialAgent
from google.adk.tools import FunctionTool

investigator = Agent(name="investigator", model="gemini-3-flash-preview",
    tools=[FunctionTool(analyze_startup_metrics)], output_key="investigator_result")

challenger = Agent(name="challenger", model="gemini-3-flash-preview",
    tools=[FunctionTool(challenge_pattern_match)], output_key="challenger_result")

reporter = Agent(name="reporter", model="gemini-3-flash-preview",
    tools=[FunctionTool(fetch_category_benchmarks), FunctionTool(save_analysis_report)])

oracle = SequentialAgent(name="failure_oracle", sub_agents=[investigator, challenger, reporter])
```

Each sub-agent is a real `LlmAgent` with its own Gemini 3 Flash call, dedicated tools, and session-state output via `output_key`. Real-time steps stream via SSE using `asyncio.Queue` + `ContextVar` — tool functions emit events without knowing they're being observed.

---

## Tech Stack

| Technology | Role |
|---|---|
| **Gemini 3 Flash (`gemini-3-flash-preview`)** | All 3 ADK agents — Investigator, Challenger, Reporter — via paid Gemini API |
| **Vertex AI Gemini 2.5 Flash** | Primary parallel pattern scorer (`thinking_budget=0`) + decision auditing (`thinking_budget=1024`) |
| **Google ADK (`google-adk`)** | `SequentialAgent` with 3 real sub-agents, `Runner`, `InMemorySessionService`, `output_key` session state |
| **MongoDB Voyage AI `voyage-4-large`** | 1024-dim embeddings, asymmetric retrieval (query vs. document encoding) |
| **MongoDB Atlas Vector Search** | Cosine similarity search across 100 pattern narratives |
| **MongoDB Atlas Search** | BM25 full-text search, merged with vector via RRF |
| **MongoDB MCP (`mongodb-mcp-server@1.9.0`)** | Persistent stdio MCP server — 28 tools, in critical path for 3 endpoints |
| **MongoDB `$graphLookup`** | Directed failure cascade graph — 3-hop traversal, 17 seeded patterns with 47 transitions |
| **Motor ACID Transactions** | Atomic writes across 3 collections per cascade analysis |
| **MongoDB Change Streams** | Detects A→B transitions → Bayesian probability update |
| **MongoDB `$bucket` + `$facet`** | Cohort percentile intelligence — 5 sub-pipelines in one query |
| **FastAPI + Motor** | Async Python backend, parallel scoring via `asyncio.gather` |
| **Server-Sent Events** | Real-time streaming of every agent step |
| **Google Cloud Run** | Serverless deployment, auto-scaling |

---

## Project Structure

```
oracle/
├── backend/
│   ├── main.py              # FastAPI app — starts MCP + ADK + Change Streams at startup
│   ├── config.py            # Settings (pydantic-settings + .env) — all model names env-driven
│   ├── db/
│   │   ├── connection.py    # Motor async client
│   │   ├── schemas.py       # Pydantic models (PatternMatch, AlertResponse, etc.)
│   │   └── seed.py          # Seeds 100 patterns + generates embeddings
│   ├── routes/
│   │   ├── metrics.py       # POST /api/metrics/analyze  — routes through ADK agent
│   │   ├── stream.py        # POST /api/metrics/analyze/stream  — SSE
│   │   ├── audit.py         # POST /api/audit/evaluate + /pre-mortem — Gemini reasoning
│   │   ├── cascade.py       # $graphLookup cascade + intervention + cohort intelligence
│   │   ├── patterns.py      # GET /api/patterns/  — MCP-backed library browser
│   │   └── integrations.py  # POST /api/integrations/stripe
│   └── services/
│       ├── gemini.py        # Dual-model client: Vertex AI 2.5 Flash scorer + Gemini 3 chain
│       ├── adk_runner.py    # ADK SequentialAgent: Investigator → Challenger → Reporter
│       ├── mcp_client.py    # Persistent MCP stdio connection manager
│       ├── pattern_matcher.py  # Vector search + parallel scoring + Oracle Score + Escape Plan
│       ├── cascade.py       # $graphLookup + Intervention Optimizer + ACID + Bayesian update
│       ├── change_stream.py # Self-improving Change Stream watcher
│       ├── auditor.py       # MCP fetch + Gemini deliberate reasoning
│       └── output_writer.py # Markdown report writer
├── frontend/
│   ├── index.html           # Single-page app — full educational UI
│   ├── style.css            # Light/dark theme, all component styles
│   └── app.js               # All UI logic — streaming, rendering, cascade, trajectory
├── data/
│   └── failure_patterns_seed.json  # 100 patterns, F-001 to F-100
├── scripts/
│   └── seed_cascade_transitions.py  # Seeds 17 patterns with 47 cascade transitions
└── tests/
    └── test_suite.py        # Unit tests (Oracle Score, Escape Plan, Bayesian) + integration tests
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/metrics/analyze` | ADK agent analysis — full pattern alert response |
| `POST` | `/api/metrics/analyze/stream` | Same pipeline, SSE streaming |
| `POST` | `/api/metrics/extract-metrics` | Extract 11 metrics from any free-form text (Gemini) |
| `POST` | `/api/metrics/watch` | Register startup for background monitoring (6h interval) |
| `GET` | `/api/metrics/watch/{name}` | Get monitoring status + last result |
| `POST` | `/api/metrics/watch/{name}/check-now` | Trigger immediate re-analysis |
| `POST` | `/api/audit/evaluate` | Decision audit — MCP fetch + Gemini reasoning |
| `POST` | `/api/audit/pre-mortem` | Oracle Pre-Mortem — Gemini projects decision +1/+3/+6 months |
| `GET` | `/api/patterns/` | All 100 patterns (MCP-backed, `"source":"mcp"`) |
| `GET` | `/api/patterns/{id}` | Single pattern detail |
| `GET` | `/api/cascade/{pattern_id}` | `$graphLookup` cascade chain |
| `POST` | `/api/cascade/analyze` | Full cascade + intervention optimizer + ACID transaction |
| `GET` | `/api/cascade/cohort/intelligence` | `$bucket` + `$facet` cohort percentile |
| `GET` | `/api/health` | Status — MCP, ADK, model config, active Gemini model |

Health check:
```json
{
  "status": "ok",
  "mongodb": "connected",
  "mcp": "ready",
  "mcp_tools": 28,
  "adk_agent": "initialized",
  "pattern_count": 100,
  "gemini_active": "gemini-3-flash-preview",
  "gemini3_chain": ["gemini-3-flash-preview", "gemini-3.5-flash", "gemini-3.1-flash-lite"],
  "gemini_fallback": "gemini-2.5-flash (vertex-ai)",
  "embedding_model": "voyage-4-large (1024-dim)",
  "embedding_source": "MongoDB Voyage AI"
}
```

---

## The Pattern Library

100 curated failure archetypes across 12 categories, synthesized from public sources: YC batch post-mortems, CB Insights startup failure reports, Paul Graham and Ben Horowitz essays, Sequoia / a16z / Bessemer research, and public founder post-mortems (Quibi, Theranos, WeWork, Homejoy, Jawbone, Juicero, Vine).

| Category | Count |
|---|---|
| Go-To-Market | 14 |
| Team | 12 |
| Unit Economics | 12 |
| Product-Market Fit | 11 |
| Fundraising | 8 |
| Competition | 8 |
| Product | 8 |
| Premature Scaling | 6 |
| Regulatory | 6 |
| Technical Debt | 6 |
| Platform Risk | 5 |
| Pivot | 4 |

Each pattern contains: narrative, trigger conditions (numeric thresholds), warning signals with `days_before_failure` data, survival playbook, famous failures, and historical outcome statistics.

---

## Setup

### Prerequisites

```
Python 3.11+
Node.js 20+  (for MongoDB MCP server)
MongoDB Atlas account  — cloud.mongodb.com (free M0 tier works)
Google Cloud project   — console.cloud.google.com (Vertex AI enabled)
Gemini API key         — aistudio.google.com/apikey
Voyage AI API key      — voyageai.com (for embeddings)
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
MONGODB_DB_NAME=oracle_db
GOOGLE_PROJECT_ID=your-project-id    # GCP project with Vertex AI enabled
GOOGLE_LOCATION=us-central1
GEMINI_API_KEY=AIza...               # Google AI Studio → Get API key (for ADK agents)
VOYAGE_API_KEY=pa-...                # Voyage AI key (for embeddings)
GEMINI_MODEL=gemini-2.5-flash        # Vertex AI scoring model
ADK_MODEL=gemini-3-flash-preview     # ADK agent model (Gemini 3, via Gemini API)
VOYAGE_MODEL=voyage-4-large          # Embedding model
EMBED_FALLBACK_MODEL=text-embedding-004  # Fallback embedding
```

All model names are env-driven — no model strings hardcoded in source.

### Seed the pattern library

```bash
python -m backend.db.seed
# Generating embeddings for 100 patterns via Voyage AI (batched)...
# [OK] Seeded 100 failure patterns with 1024-dim embeddings
# [OK] Atlas Vector Search index created (vector_index, cosine)

python scripts/seed_cascade_transitions.py
# [OK] Seeded cascade transitions for 17 patterns (47 directed edges)
```

> Requires application default credentials: `gcloud auth application-default login`

### Run

```bash
uvicorn backend.main:app --reload --port 8080
# [OK] MongoDB connected (Motor)
# [OK] MongoDB MCP server ready (28 tools)
# [OK] Change Stream watcher started
# [OK] Failure Oracle ADK agent initialized (model: gemini-3-flash-preview)
```

Open `http://localhost:8080`. Click the Quibi preset to see the pipeline run. Try HighVelocity AI to see a Challenger DISPUTE.

### Test

```bash
python tests/test_suite.py --base http://localhost:8080
# Section 0: Unit tests (Oracle Score formula, Escape Plan, Bayesian math) — no server needed
# Section 1+: Integration tests across all endpoints
# Saves timestamped HTML + JSON reports to tests/reports/
```

Unit tests run independently of the server (pure Python math verification). Integration tests require a running instance.

---

## Deploy to Google Cloud Run

The Dockerfile installs Python 3.11, Node.js 20, and `mongodb-mcp-server` globally — full pipeline in one container.

```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/oracle --project PROJECT_ID

gcloud run deploy oracle \
  --image gcr.io/PROJECT_ID/oracle \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --env-vars-file env-cloud.yaml
```

**Required env vars for deployment:** `MONGODB_URI`, `GEMINI_API_KEY`, `VOYAGE_API_KEY`, `GOOGLE_PROJECT_ID`, `GOOGLE_LOCATION`, `MONGODB_DB_NAME`

---

## Key Implementation Notes

**Why `MDB_MCP_CONNECTION_STRING` instead of `--connectionString`?** MongoDB Atlas URIs contain `?` and `&` characters that shell argument parsers interpret as special characters. Passing via environment variable avoids the parsing issue.

**Why a persistent MCP process?** Starting `mongodb-mcp-server` per request adds 2–3 seconds of Node.js startup overhead. A single background asyncio task owns the stdio connection for the app lifetime, with an async lock protecting concurrent access.

**Why `thinking_budget=0` for scoring but `thinking_budget=1024` for auditing?** Pattern scoring needs speed (parallel, 2–4s total for 5 candidates). Decision auditing is a deliberate one-shot call where reasoning quality matters more. Different call profiles, different configurations.

**Why Gemini 3 Flash for ADK agents and Vertex AI 2.5 Flash for scoring?** Gemini 3 Flash is sharper for the multi-step adversarial reasoning the Challenger requires. Vertex AI 2.5 Flash has better latency SLA and supports `thinking_budget` parameter for the scoring path. Gemini 3 Flash is not yet available on Vertex AI, so it routes via the paid Gemini API. Two different jobs, two different models.

**Why the Escape Plan uses no AI.** If the Escape Plan said "consider reducing burn" and you asked "by how much?", an AI answer would be vague. The plan solves backwards from the pattern's stored trigger thresholds: `new_burn = target_runway * current_burn_rate`. The number is exact, reproducible, and verifiable.

---

## Honest Limitations

- **Pattern similarity is not failure probability.** A 95% match means the metric narrative strongly resembles a documented failure pattern. It does not mean 95% chance of failing. Survivors of every pattern exist.
- **The library is 100 patterns deep, not 10,000.** Curated for depth and citation traceability, not breadth. Real failure modes exist that aren't yet in the library — that's what the Uncharted Territory path is for.
- **Decision Auditor outputs reasoning, not statistics.** Cross-references decisions against named patterns. Not calibrated statistical risk numbers.
- **Survival rates are sourced estimates.** Calibrated against CB Insights, YC published data, and founder post-mortems — directionally accurate, not actuarially precise.
- **English-language sources only.** International failure modes are underrepresented.

---

## License

Apache 2.0

Built with Gemini 3 Flash · Vertex AI Gemini 2.5 Flash · Google ADK · MongoDB Atlas · MongoDB MCP · Voyage AI · Cloud Run
