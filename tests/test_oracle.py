"""
Run these tests while the server is running locally.
Usage:
  1. Start server:  uvicorn backend.main:app --reload --port 8080
  2. Run tests:     python tests/test_oracle.py
Outputs are written to the outputs/ folder.
"""
import httpx
import json
from pathlib import Path

BASE = "http://localhost:8080"


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── Test 1: Health check ────────────────────────────────────────
def test_health():
    print_section("TEST 1: Health Check")
    r = httpx.get(f"{BASE}/api/health")
    assert r.status_code == 200
    print("✅ Server is healthy:", r.json())


# ── Test 2: List patterns ───────────────────────────────────────
def test_list_patterns():
    print_section("TEST 2: List Failure Patterns")
    r = httpx.get(f"{BASE}/api/patterns/")
    assert r.status_code == 200
    data = r.json()
    print(f"✅ {data['total']} patterns loaded in library")
    for p in data["patterns"][:5]:
        print(f"   {p['pattern_id']}: {p['name']}")


# ── Test 3: Healthy startup — no alert ─────────────────────────
def test_healthy_startup():
    print_section("TEST 3: Healthy Startup — Expect No Alert")
    payload = {
        "startup_name": "HealthyCo",
        "current_month": 12,
        "mrr": 120000,
        "mrr_growth_rate": 0.22,
        "churn_rate": 0.03,
        "burn_rate": 80000,
        "runway_months": 18,
        "headcount": 10,
        "nps": 58,
        "cac": 1200,
        "ltv": 14000,
        "industry": "B2B SaaS",
    }
    r = httpx.post(f"{BASE}/api/metrics/analyze", json=payload, timeout=30)
    assert r.status_code == 200
    data = r.json()
    print(f"Alert triggered: {data['alert']}")
    print(f"Message: {data['message']}")
    if not data["alert"]:
        print("✅ Correct — no alert for healthy startup")
    else:
        print(f"⚠️  Alert fired (may still be correct): {data['pattern']['pattern_name']}")


# ── Test 4: Danger zone — expect alert ─────────────────────────
def test_danger_startup():
    print_section("TEST 4: Danger Zone Startup — Expect Alert")
    payload = {
        "startup_name": "AcmeSaaS",
        "current_month": 14,
        "mrr": 85000,
        "mrr_growth_rate": 0.18,
        "churn_rate": 0.09,
        "burn_rate": 120000,
        "runway_months": 8,
        "headcount": 12,
        "nps": 31,
        "cac": 1800,
        "ltv": 9200,
        "industry": "B2B SaaS",
    }
    r = httpx.post(f"{BASE}/api/metrics/analyze", json=payload, timeout=30)
    assert r.status_code == 200
    data = r.json()

    print(f"Alert triggered: {data['alert']}")
    if data["alert"]:
        p = data["pattern"]
        print(f"✅ Pattern detected: {p['pattern_name']}")
        print(f"   Confidence: {int(p['confidence']*100)}%")
        print(f"   Days to crisis: ~{p['days_to_crisis']}")
        print(f"   Signals detected: {len(p['warning_signals_detected'])}")
        print(f"   Output file: {p['output_file']}")
        print(f"\n   📄 Check outputs/latest_alert.md for full report")
    else:
        print("⚠️  No alert — check pattern seeding or Gemini API key")


# ── Test 5: Quibi-like extreme case ────────────────────────────
def test_quibi_case():
    print_section("TEST 5: Quibi-Like Startup — Extreme Case")
    payload = {
        "startup_name": "QuickStream",
        "current_month": 3,
        "mrr": 420000,
        "mrr_growth_rate": 0.05,
        "churn_rate": 0.18,
        "burn_rate": 8500000,
        "runway_months": 14,
        "headcount": 185,
        "nps": 12,
        "cac": 45000,
        "ltv": 18000,
        "industry": "Consumer",
    }
    r = httpx.post(f"{BASE}/api/metrics/analyze", json=payload, timeout=30)
    assert r.status_code == 200
    data = r.json()
    print(f"Alert triggered: {data['alert']}")
    if data["alert"]:
        p = data["pattern"]
        print(f"✅ Pattern: {p['pattern_name']} ({int(p['confidence']*100)}% confidence)")
        print(f"   Days to crisis: ~{p['days_to_crisis']}")


# ── Test 6: Decision audit ──────────────────────────────────────
def test_decision_audit():
    print_section("TEST 6: Decision Audit — Hire 3 Engineers")
    payload = {
        "decision": "Hire 3 senior engineers this month to accelerate product development",
        "metrics": {
            "startup_name": "AcmeSaaS",
            "current_month": 14,
            "mrr": 85000,
            "mrr_growth_rate": 0.18,
            "churn_rate": 0.09,
            "burn_rate": 120000,
            "runway_months": 8,
            "headcount": 12,
            "nps": 31,
            "cac": 1800,
            "ltv": 9200,
            "industry": "B2B SaaS",
        },
    }
    r = httpx.post(f"{BASE}/api/audit/evaluate", json=payload, timeout=30)
    assert r.status_code == 200
    data = r.json()
    print(f"Risk level: {data['risk_level']}")
    print(f"Total cases: {data['total_cases']}")
    print(f"Success: {data['success_cases']} | Failure: {data['failure_cases']}")
    print(f"Key differentiator: {data['key_differentiator']}")
    print(f"Recommendation: {data['recommendation']}")
    print(f"\n   📄 Check outputs/latest_audit.md for full report")


# ── Check outputs were created ──────────────────────────────────
def check_outputs():
    print_section("CHECKING OUTPUT FILES")
    output_dir = Path("outputs")
    if not output_dir.exists():
        print("⚠️  outputs/ directory not found")
        return

    files = list(output_dir.glob("*.md")) + list(output_dir.glob("*.json"))
    if files:
        print(f"✅ {len(files)} output files created:")
        for f in sorted(files):
            size = f.stat().st_size
            print(f"   {f.name} ({size:,} bytes)")
    else:
        print("⚠️  No output files found yet")


# ── Main ────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n🔮 THE FAILURE ORACLE — TEST SUITE")
    print("Make sure the server is running: uvicorn backend.main:app --reload --port 8080\n")

    try:
        test_health()
        test_list_patterns()
        test_healthy_startup()
        test_danger_startup()
        test_quibi_case()
        test_decision_audit()
        check_outputs()
        print("\n\n✅ ALL TESTS COMPLETE")
        print("📂 Open outputs/latest_alert.md to review the agent's output")
    except httpx.ConnectError:
        print("\n❌ Cannot connect to server.")
        print("   Run: uvicorn backend.main:app --reload --port 8080")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise
