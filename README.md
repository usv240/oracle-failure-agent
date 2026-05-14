# 🔮 The Failure Oracle

> "90% of startups fail for known, preventable reasons. Know yours — before it's too late."

An AI agent that watches your startup's metrics and warns you when you're matching
a known failure pattern — with a specific survival playbook from companies that made it through.

🚀 **Live Demo:** https://oracle-failure-oracle-38381883054.us-central1.run.app

---

## Setup (Step by Step)

### Step 1 — Prerequisites
```
Python 3.11+
A MongoDB Atlas account (free tier works) → cloud.mongodb.com
A Google Cloud account → console.cloud.google.com
A Gemini API key → aistudio.google.com/apikey
```

### Step 2 — Clone and install
```bash
cd oracle
pip install -r requirements.txt
```

### Step 3 — Configure environment
```bash
cp .env.example .env
# Edit .env and fill in:
#   MONGODB_URI       — from MongoDB Atlas → Connect → Drivers
#   GOOGLE_PROJECT_ID — your GCP project
#   GEMINI_API_KEY    — from Google AI Studio (add to .env)
```

### Step 4 — Seed the failure library
```bash
python -m backend.db.seed
# Expected output:
# ✅ Seeded 30 failure patterns
# ✅ Indexes created
```

### Step 5 — Run locally
```bash
uvicorn backend.main:app --reload --port 8080
# Open: http://localhost:8080
```

### Step 6 — Test
```bash
python tests/test_oracle.py
# Check outputs/ folder for generated reports
```

---

## How It Works

1. Founder inputs their current metrics (MRR, churn, burn, NPS, etc.)
2. Agent queries MongoDB failure pattern library
3. Gemini evaluates confidence of pattern match
4. If >60% confidence: fires alert with playbook + saves to `outputs/`
5. Founder can also audit decisions before making them

---

## Project Structure

```
oracle/
├── backend/
│   ├── main.py              # FastAPI app
│   ├── config.py            # Settings
│   ├── db/
│   │   ├── connection.py    # MongoDB client
│   │   ├── schemas.py       # Pydantic models
│   │   └── seed.py          # Seed script
│   ├── routes/
│   │   ├── metrics.py       # POST /api/metrics/analyze
│   │   ├── audit.py         # POST /api/audit/evaluate
│   │   └── patterns.py      # GET /api/patterns/
│   └── services/
│       ├── gemini.py        # Gemini client
│       ├── pattern_matcher.py
│       ├── auditor.py
│       └── output_writer.py
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── agent/
│   ├── system_prompt.txt
│   └── tools.json
├── data/
│   └── failure_patterns_seed.json
├── outputs/              # Generated reports saved here
├── tests/
│   └── test_oracle.py
└── Dockerfile
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/metrics/analyze` | Submit metrics, get pattern alert |
| POST | `/api/audit/evaluate` | Audit a decision |
| GET | `/api/patterns/` | List all patterns |
| GET | `/api/patterns/{id}` | Get pattern details |
| GET | `/api/health` | Health check |

---

## Deploy to Cloud Run

```bash
# Build
docker build -t oracle-agent .

# Push to GCR
docker tag oracle-agent gcr.io/PROJECT_ID/oracle-agent
docker push gcr.io/PROJECT_ID/oracle-agent

# Deploy
gcloud run deploy oracle-agent \
  --image gcr.io/PROJECT_ID/oracle-agent \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars MONGODB_URI=...,GOOGLE_PROJECT_ID=...,GEMINI_API_KEY=...
```

---

## License

Apache 2.0 — see [LICENSE](LICENSE)

Built with Gemini 2.5 Flash (Vertex AI) + MongoDB Atlas
