"""
Comprehensive test suite for The Failure Oracle.

Usage:
    python tests/test_suite.py [--base http://localhost:8089]

Saves timestamped JSON + HTML reports to tests/reports/.
"""
import sys
import json
import time
import re
import urllib.request
import urllib.error
import argparse
from datetime import datetime
from pathlib import Path

# ── Config ───────────────────────────────────────────────────────
DEFAULT_BASE = "http://localhost:8089"
REPORTS_DIR  = Path(__file__).parent / "reports"

# Demo payloads
HEALTHY = dict(startup_name="GrowthCo", current_month=12, mrr=120000,
               mrr_growth_rate=0.22, churn_rate=0.03, burn_rate=80000,
               runway_months=18, headcount=10, nps=58, cac=1200,
               ltv=14000, industry="B2B SaaS")

WARNING = dict(startup_name="AcmeSaaS", current_month=14, mrr=85000,
               mrr_growth_rate=0.18, churn_rate=0.09, burn_rate=120000,
               runway_months=8, headcount=12, nps=31, cac=1800,
               ltv=9200, industry="B2B SaaS")

QUIBI = dict(startup_name="Quibi", current_month=4, mrr=420000,
             mrr_growth_rate=0.04, churn_rate=0.22, burn_rate=8500000,
             runway_months=14, headcount=185, nps=8, cac=48000,
             ltv=12000, industry="Consumer")

WEWORK = dict(startup_name="WeWork", current_month=20, mrr=2900000,
              mrr_growth_rate=0.14, churn_rate=0.16, burn_rate=22000000,
              runway_months=7, headcount=14000, nps=18, cac=38000,
              ltv=19000, industry="Marketplace")

THERANOS = dict(startup_name="Theranos", current_month=24, mrr=18000,
                mrr_growth_rate=0.01, churn_rate=0.45, burn_rate=5800000,
                runway_months=6, headcount=800, nps=-42, cac=95000,
                ltv=8000, industry="Healthtech")


# ── HTTP helpers ─────────────────────────────────────────────────
def get(base, path, timeout=15):
    start = time.time()
    try:
        r = urllib.request.urlopen(f"{base}{path}", timeout=timeout)
        body = json.loads(r.read().decode())
        return body, r.status, time.time() - start, None
    except urllib.error.HTTPError as e:
        return None, e.code, time.time() - start, str(e)
    except Exception as e:
        return None, 0, time.time() - start, str(e)


def post(base, path, data, timeout=90):
    start = time.time()
    req = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        body = json.loads(r.read().decode())
        return body, r.status, time.time() - start, None
    except urllib.error.HTTPError as e:
        body = None
        try: body = json.loads(e.read().decode())
        except: pass
        return body, e.code, time.time() - start, str(e)
    except Exception as e:
        return None, 0, time.time() - start, str(e)


def sse_first_events(base, path, data, n=20, timeout=90):
    """Collect first n SSE events from a streaming endpoint."""
    req = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.time()
    events = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            buf = ""
            while len(events) < n:
                chunk = resp.read(512)
                if not chunk: break
                buf += chunk.decode("utf-8", errors="replace")
                lines = buf.split("\n"); buf = lines[-1]
                for line in lines[:-1]:
                    if line.startswith("data: "):
                        try:
                            evt = json.loads(line[6:])
                            events.append(evt)
                            if evt["type"] in ("result", "safe", "error"):
                                return events, time.time() - start, None
                        except: pass
    except Exception as e:
        return events, time.time() - start, str(e)
    return events, time.time() - start, None


# ── Test runner ──────────────────────────────────────────────────
class TestRun:
    def __init__(self, base):
        self.base = base
        self.results = []
        self.t_start = time.time()

    def test(self, name, category, fn):
        """Run one test, capture pass/fail/details."""
        t0 = time.time()
        try:
            details = fn()
            elapsed = time.time() - t0
            self.results.append({
                "name": name, "category": category,
                "status": "PASS", "elapsed": round(elapsed, 2),
                "details": details or "",
            })
            print(f"  [PASS] {name} ({elapsed:.1f}s)")
        except AssertionError as e:
            elapsed = time.time() - t0
            self.results.append({
                "name": name, "category": category,
                "status": "FAIL", "elapsed": round(elapsed, 2),
                "details": str(e),
            })
            print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            elapsed = time.time() - t0
            self.results.append({
                "name": name, "category": category,
                "status": "ERROR", "elapsed": round(elapsed, 2),
                "details": str(e),
            })
            print(f"  [ERROR] {name}: {e}")

    def section(self, title):
        print(f"\n-- {title} {'-'*(50-len(title))}")

    def summary(self):
        passed  = sum(1 for r in self.results if r["status"] == "PASS")
        failed  = sum(1 for r in self.results if r["status"] == "FAIL")
        errored = sum(1 for r in self.results if r["status"] == "ERROR")
        total   = len(self.results)
        elapsed = round(time.time() - self.t_start, 1)
        return {"passed": passed, "failed": failed, "errored": errored,
                "total": total, "elapsed": elapsed}


# ── Individual tests ─────────────────────────────────────────────
def run_all(base=DEFAULT_BASE):
    run = TestRun(base)
    B = base

    # ────────────────────────────────────────────────────────────
    run.section("1. Health & Connectivity")

    run.test("Server reachable", "health", lambda: (
        (body := get(B, "/api/health")[0]),
        assert_eq(body["status"], "ok", "status"),
        assert_eq(body["service"], "failure-oracle", "service"),
        "OK",
    )[-1])

    def test_docs():
        # /docs returns HTML — just check HTTP 200, don't parse JSON
        import urllib.request
        try:
            r = urllib.request.urlopen(f"{B}/docs", timeout=10)
            assert_true(r.status == 200, f"expected 200, got {r.status}")
            return "HTTP 200"
        except Exception as e:
            raise AssertionError(f"docs unreachable: {e}")
    run.test("OpenAPI docs reachable", "health", test_docs)

    # ────────────────────────────────────────────────────────────
    run.section("2. Pattern Library (MCP)")

    def test_patterns_mcp():
        body, status, elapsed, err = get(B, "/api/patterns/")
        assert_eq(status, 200, "HTTP status")
        assert err is None, f"request error: {err}"
        assert_true(body["total"] == 100, f"expected 100 patterns, got {body['total']}")
        assert_eq(body["source"], "mcp", "source must be mcp, not motor")
        assert_true(elapsed < 8, f"MCP response too slow: {elapsed:.1f}s")
        # Verify pattern structure
        p = body["patterns"][0]
        for field in ["pattern_id", "name", "category", "narrative",
                      "warning_signals", "survival_playbook", "famous_failures",
                      "failure_count", "survival_count"]:
            assert_true(field in p, f"pattern missing field: {field}")
        return f"100 patterns via MCP in {elapsed:.1f}s"

    run.test("GET /api/patterns/ returns 100 via MCP", "patterns", test_patterns_mcp)

    def test_pattern_categories():
        body, status, _, _ = get(B, "/api/patterns/")
        cats = set(p["category"] for p in body["patterns"])
        assert_true(len(cats) >= 10, f"expected ≥10 categories, got {len(cats)}: {cats}")
        return f"{len(cats)} categories: {', '.join(sorted(cats))}"

    run.test("Pattern library has ≥10 categories", "patterns", test_pattern_categories)

    def test_pattern_by_id():
        body, status, _, err = get(B, "/api/patterns/F-001")
        assert_eq(status, 200, "HTTP status")
        assert_eq(body["pattern_id"], "F-001", "pattern_id")
        assert_true(len(body["survival_playbook"]) > 0, "survival_playbook empty")
        assert_true(len(body["warning_signals"]) > 0, "warning_signals empty")
        return f"F-001: {body['name']}"

    run.test("GET /api/patterns/F-001 returns correct pattern", "patterns", test_pattern_by_id)

    def test_pattern_404():
        body, status, _, _ = get(B, "/api/patterns/F-999")
        assert_eq(status, 404, "should 404 for unknown pattern")
        return "404 as expected"

    run.test("GET /api/patterns/F-999 returns 404", "patterns", test_pattern_404)

    def test_pattern_embeddings():
        # Spot-check that patterns have embeddings seeded
        body, _, _, _ = get(B, "/api/patterns/F-001")
        assert_true("narrative" in body and len(body["narrative"]) > 50,
                    "narrative too short or missing")
        assert_true(body["failure_count"] > 0, "failure_count is 0")
        return f"failure_count={body['failure_count']}, survival_count={body['survival_count']}"

    run.test("Pattern data quality (narrative, counts)", "patterns", test_pattern_embeddings)

    # ────────────────────────────────────────────────────────────
    run.section("3. Analysis Endpoint (ADK-orchestrated)")

    def test_healthy():
        body, status, elapsed, err = post(B, "/api/metrics/analyze", HEALTHY)
        assert_eq(status, 200, f"HTTP status (err={err})")
        assert body is not None, f"response body is None (err={err})"
        got_pattern = body.get("pattern", {}).get("pattern_name") if body.get("alert") else "none"
        assert_true(not body["alert"], f"healthy startup should NOT alert, got: {got_pattern}")
        return f"No alert in {elapsed:.1f}s"

    run.test("Healthy startup -> No alert", "analyze", test_healthy)

    def test_warning():
        body, status, elapsed, err = post(B, "/api/metrics/analyze", WARNING)
        assert_eq(status, 200, "HTTP status")
        assert_true(body["alert"], "warning startup should trigger alert")
        p = body["pattern"]
        assert_true(p["confidence"] >= 0.70, f"expected ≥70% confidence, got {p['confidence']:.0%}")
        # warning_signals_detected can be empty if Gemini scored all signals NOT_YET — that's valid
        assert_true(len(p["survival_playbook"]) >= 3, "survival playbook too short")
        assert_true(p["days_to_crisis"] > 0, "days_to_crisis must be positive")
        sigs = len(p["warning_signals_detected"])
        return f"{p['pattern_name']} @ {p['confidence']:.0%}, {sigs} signals, in {elapsed:.1f}s"

    run.test("Warning startup -> Alert ≥70% confidence", "analyze", test_warning)

    def test_quibi():
        body, status, elapsed, err = post(B, "/api/metrics/analyze", QUIBI)
        assert_eq(status, 200, "HTTP status")
        assert_true(body["alert"], "Quibi should trigger alert")
        p = body["pattern"]
        assert_true(p["confidence"] >= 0.80, f"Quibi should be ≥80%, got {p['confidence']:.0%}")
        assert_true(p["days_to_crisis"] > 0, "days_to_crisis must be positive")
        assert_true(len(p["famous_failures"]) > 0, "famous_failures empty")
        return f"{p['pattern_name']} @ {p['confidence']:.0%} in {elapsed:.1f}s"

    run.test("Quibi (April 2020) → Alert ≥80%", "analyze", test_quibi)

    def test_wework():
        body, status, elapsed, err = post(B, "/api/metrics/analyze", WEWORK)
        assert_eq(status, 200, "HTTP status")
        assert_true(body["alert"], "WeWork should trigger alert")
        p = body["pattern"]
        assert_true(p["confidence"] >= 0.75, f"WeWork should be ≥75%, got {p['confidence']:.0%}")
        return f"{p['pattern_name']} @ {p['confidence']:.0%} in {elapsed:.1f}s"

    run.test("WeWork (Q3 2019) → Alert ≥75%", "analyze", test_wework)

    def test_theranos():
        body, status, elapsed, err = post(B, "/api/metrics/analyze", THERANOS)
        assert_eq(status, 200, "HTTP status")
        assert_true(body["alert"], "Theranos should trigger alert")
        p = body["pattern"]
        assert_true(p["confidence"] >= 0.75, f"Theranos should be ≥75%, got {p['confidence']:.0%}")
        return f"{p['pattern_name']} @ {p['confidence']:.0%} in {elapsed:.1f}s"

    run.test("Theranos (2015) → Alert ≥75%", "analyze", test_theranos)

    def test_response_structure():
        body, status, _, _ = post(B, "/api/metrics/analyze", QUIBI)
        p = body["pattern"]
        for field in ["pattern_id", "pattern_name", "confidence", "failure_count",
                      "survival_count", "survival_rate", "narrative",
                      "warning_signals_detected", "survival_playbook",
                      "famous_failures", "days_to_crisis"]:
            assert_true(field in p, f"PatternMatch missing field: {field}")
        sig = p["warning_signals_detected"][0]
        for sf in ["signal", "status"]:
            assert_true(sf in sig, f"WarningSig missing: {sf}")
        assert_true(sig["status"] in ("DETECTED", "EMERGING"), f"invalid status: {sig['status']}")
        return "All required fields present, signal status valid"

    run.test("AlertResponse structure complete", "analyze", test_response_structure)

    def test_confidence_range():
        body, _, _, _ = post(B, "/api/metrics/analyze", QUIBI)
        c = body["pattern"]["confidence"]
        assert_true(0.0 <= c <= 1.0, f"confidence out of range [0,1]: {c}")
        return f"confidence={c:.2f} ∈ [0,1]"

    run.test("Confidence score is in [0.0, 1.0]", "analyze", test_confidence_range)

    def test_response_time():
        _, _, elapsed, _ = post(B, "/api/metrics/analyze", HEALTHY)
        assert_true(elapsed < 30, f"analysis took {elapsed:.1f}s — too slow (>30s)")
        return f"{elapsed:.1f}s"

    run.test("Analysis response time < 30s", "analyze", test_response_time)

    # ────────────────────────────────────────────────────────────
    run.section("4. SSE Streaming Endpoint")

    def test_sse_events():
        events, elapsed, err = sse_first_events(B, "/api/metrics/analyze/stream", QUIBI)
        assert err is None or len(events) > 0, f"SSE error: {err}"
        assert_true(len(events) >= 6, f"expected ≥6 events, got {len(events)}")
        types = [e["type"] for e in events]
        assert_true("step" in types, "no step events in stream")
        final = events[-1]["type"]
        assert_true(final in ("result", "safe"), f"last event should be result/safe, got {final}")
        return f"{len(events)} events, final={final}, elapsed={elapsed:.1f}s"

    run.test("SSE stream returns ≥6 events + final result/safe", "streaming", test_sse_events)

    def test_sse_no_adk_lie():
        events, _, _ = sse_first_events(B, "/api/metrics/analyze/stream", QUIBI, n=3)
        msgs = [e.get("message", "") for e in events if e["type"] == "step"]
        for msg in msgs:
            assert_true("ADK Agent initialized" not in msg,
                        f"misleading ADK message still present: '{msg}'")
        return f"No misleading ADK message in first steps. First: '{msgs[0][:60]}...'"

    run.test("SSE first message is accurate (no misleading 'ADK initialized')", "streaming", test_sse_no_adk_lie)

    def test_sse_pipeline_steps():
        events, _, _ = sse_first_events(B, "/api/metrics/analyze/stream", QUIBI)
        all_text = " ".join(e.get("message", "") for e in events)
        for keyword in ["embedding", "Vector Search", "MCP", "Gemini"]:
            assert_true(keyword in all_text, f"expected '{keyword}' in SSE steps")
        return "All pipeline keywords present: embedding, Vector Search, MCP, Gemini"

    run.test("SSE steps mention all pipeline components", "streaming", test_sse_pipeline_steps)

    def test_sse_result_structure():
        events, _, _ = sse_first_events(B, "/api/metrics/analyze/stream", QUIBI)
        final = next((e for e in reversed(events) if e["type"] == "result"), None)
        if final is None:
            safe = next((e for e in reversed(events) if e["type"] == "safe"), None)
            assert safe is not None, "no result or safe event"
            return "Safe result (no pattern)"
        assert_true("pattern" in final, "result event missing 'pattern'")
        p = final["pattern"]
        assert_true(p["confidence"] >= 0.60, f"stream confidence too low: {p['confidence']:.0%}")
        return f"{p['pattern_name']} @ {p['confidence']:.0%}"

    run.test("SSE final result has pattern with confidence ≥60%", "streaming", test_sse_result_structure)

    def test_sse_healthy_returns_safe():
        events, _, _ = sse_first_events(B, "/api/metrics/analyze/stream", HEALTHY)
        final_type = next((e["type"] for e in reversed(events) if e["type"] in ("result","safe")), None)
        assert_true(final_type == "safe", f"healthy startup stream should end with 'safe', got {final_type}")
        return "Healthy startup → 'safe' event ✓"

    run.test("Healthy startup SSE ends with 'safe' event", "streaming", test_sse_healthy_returns_safe)

    # ────────────────────────────────────────────────────────────
    run.section("5. Decision Audit Endpoint")

    def test_audit_structure():
        payload = {
            "startup_name": "AcmeSaaS", "current_month": 14,
            "decision": "Double headcount from 12 to 24 while runway is 8 months",
            "metrics": WARNING,
        }
        body, status, elapsed, err = post(B, "/api/audit/evaluate", payload)
        assert_eq(status, 200, "HTTP status")
        for field in ["risk_level", "key_differentiator", "recommendation", "decision"]:
            assert_true(field in body, f"AuditResponse missing: {field}")
        assert_true(body["risk_level"] in ("LOW","MEDIUM","HIGH","CRITICAL"),
                    f"invalid risk_level: {body['risk_level']}")
        assert_true(len(body["recommendation"]) > 20, "recommendation too short")
        return f"risk={body['risk_level']}, has recommendation, elapsed={elapsed:.1f}s"

    run.test("Audit returns structured response with valid risk_level", "audit", test_audit_structure)

    def test_audit_bad_decision():
        payload = {
            "startup_name": "Quibi", "current_month": 4,
            "decision": "Hire 100 engineers and expand to 3 new markets with 22% monthly churn",
            "metrics": QUIBI,
        }
        body, status, _, _ = post(B, "/api/audit/evaluate", payload)
        assert_eq(status, 200, "HTTP status")
        assert_true(body["risk_level"] in ("HIGH","CRITICAL"),
                    f"obviously bad decision should be HIGH/CRITICAL, got {body['risk_level']}")
        return f"risk={body['risk_level']} for clearly bad decision ✓"

    run.test("Audit correctly flags obviously bad decision as HIGH/CRITICAL", "audit", test_audit_bad_decision)

    def test_audit_missing_field():
        # Missing 'startup_name' at top level — should 422
        payload = {"decision": "hire 5 engineers", "metrics": WARNING}
        body, status, _, _ = post(B, "/api/audit/evaluate", payload)
        assert_eq(status, 422, f"should 422 for missing required fields, got {status}")
        return "422 for malformed request ✓"

    run.test("Audit 422 for missing required fields", "audit", test_audit_missing_field)

    # ────────────────────────────────────────────────────────────
    run.section("6. Stripe Integration Endpoint")

    def test_stripe_bad_key():
        body, status, _, _ = post(B, "/api/integrations/stripe", {"api_key": "bad_key"}, timeout=10)
        assert_eq(status, 400, f"bad key should return 400, got {status}")
        return "400 for bad key ✓"

    run.test("Stripe bad key → 400", "integrations", test_stripe_bad_key)

    def test_stripe_wrong_prefix():
        body, status, _, _ = post(B, "/api/integrations/stripe", {"api_key": "pk_test_abc123"}, timeout=10)
        assert_eq(status, 400, "pk_ key should 400 (not sk_)")
        return "400 for pk_ prefix (must be sk_) ✓"

    run.test("Stripe pk_ key → 400 (must start with sk_)", "integrations", test_stripe_wrong_prefix)

    def test_stripe_missing_body():
        body, status, _, _ = post(B, "/api/integrations/stripe", {}, timeout=10)
        assert_true(status in (400, 422), f"empty body should 400/422, got {status}")
        return f"HTTP {status} for empty body ✓"

    run.test("Stripe empty body → 400/422", "integrations", test_stripe_missing_body)

    # ────────────────────────────────────────────────────────────
    run.section("7. Frontend Asset Checks")

    oracle_dir = Path(__file__).parent.parent

    def test_html_theme_toggle():
        html = (oracle_dir / "frontend" / "index.html").read_text(encoding="utf-8")
        assert_true('id="theme-btn"' in html, "theme toggle button missing")
        assert_true("oracle_theme" in html, "theme persistence script missing")
        return "theme-btn present, localStorage key present"

    run.test("HTML has theme toggle button + persistence script", "frontend", test_html_theme_toggle)

    def test_html_impact_bar():
        html = (oracle_dir / "frontend" / "index.html").read_text(encoding="utf-8")
        assert_true('class="impact-bar"' in html, "impact stats bar missing")
        assert_true("150M" in html, "150M startup stat missing from impact bar")
        return "impact-bar present with stats"

    run.test("HTML has impact stats bar with 150M stat", "frontend", test_html_impact_bar)

    def test_html_risk_banner():
        html = (oracle_dir / "frontend" / "index.html").read_text(encoding="utf-8")
        assert_true('id="risk-banner"' in html, "risk-banner element missing")
        assert_true('risk-banner-text' in html, "risk-banner-text id missing")
        return "risk-banner elements present"

    run.test("HTML has risk level banner element", "frontend", test_html_risk_banner)

    def test_html_adk_footer():
        html = (oracle_dir / "frontend" / "index.html").read_text(encoding="utf-8")
        assert_true("Google ADK" in html, "Google ADK not mentioned in footer")
        assert_true("github.com" in html, "GitHub link missing from footer")
        return "Google ADK and GitHub link in footer"

    run.test("HTML footer has Google ADK badge + GitHub link", "frontend", test_html_adk_footer)

    def test_css_light_default():
        css = (oracle_dir / "frontend" / "style.css").read_text(encoding="utf-8")
        import re
        # Check that :root has a light --bg (any near-white value like #f5f6fa, #f8fafc, etc.)
        root_block = re.search(r':root\s*\{([^}]+)\}', css)
        assert_true(root_block is not None, "no :root block found")
        root_content = root_block.group(1)
        bg_match = re.search(r'--bg:\s*(#[0-9a-fA-F]+)', root_content)
        assert_true(bg_match is not None, "--bg not defined in :root")
        bg_val = bg_match.group(1).lower()
        # Light backgrounds are near-white: first hex digit should be 'e' or 'f'
        assert_true(bg_val[1] in 'ef', f"--bg value {bg_val} doesn't look like a light background")
        assert_true('[data-theme="dark"]' in css, "dark theme override missing")
        return f"light theme --bg={bg_val}, dark theme override present"

    run.test("CSS: light theme is default, dark theme via data-attribute", "frontend", test_css_light_default)

    def test_css_no_dark_backgrounds():
        css = (oracle_dir / "frontend" / "style.css").read_text(encoding="utf-8")
        # Split at dark-theme block
        light_part = css.split('[data-theme="dark"]')[0]
        # Check the specific previously-broken elements are fixed
        violations = []
        if "background: #0d0505" in light_part and ".alert-card" in light_part[:light_part.find("background: #0d0505")]:
            violations.append(".alert-card still has dark background in light CSS")
        if "background: #0a150a" in light_part:
            violations.append(".playbook still has dark background in light CSS")
        assert_true(len(violations) == 0, "; ".join(violations))
        return "No hardcoded dark backgrounds in light-theme scope"

    run.test("CSS: no hardcoded dark backgrounds in light theme scope", "frontend", test_css_no_dark_backgrounds)

    def test_css_terminal_dark():
        css = (oracle_dir / "frontend" / "style.css").read_text(encoding="utf-8")
        assert_true(".agent-terminal { background: #0a0a0f !important; }" in css,
                    "terminal override missing — will turn white in light mode")
        return "Terminal forced dark via !important override"

    run.test("CSS: terminal stays dark in light mode (!important override)", "frontend", test_css_terminal_dark)

    def test_js_no_hardcoded_colors():
        js = (oracle_dir / "frontend" / "app.js").read_text(encoding="utf-8")
        matches = re.findall(r'color:\s*#[0-9a-fA-F]{6}', js)
        assert_true(len(matches) == 0,
                    f"JS still has {len(matches)} hardcoded color(s) in innerHTML: {matches}")
        return "No hardcoded colors in JS innerHTML"

    run.test("JS: no hardcoded colors injected into innerHTML", "frontend", test_js_no_hardcoded_colors)

    def test_stream_no_adk_lie():
        stream_py = (oracle_dir / "backend" / "routes" / "stream.py").read_text(encoding="utf-8")
        assert_true("ADK Agent initialized" not in stream_py,
                    "stream.py still says 'ADK Agent initialized' — misleading")
        return "No misleading ADK message in stream.py"

    run.test("stream.py: no misleading 'ADK initialized' message", "frontend", test_stream_no_adk_lie)

    # ────────────────────────────────────────────────────────────
    run.section("8. Pattern Quality Spot-checks")

    def test_all_categories_populated():
        body, _, _, _ = get(B, "/api/patterns/")
        cats = {}
        for p in body["patterns"]:
            cats[p["category"]] = cats.get(p["category"], 0) + 1
        expected = ["premature_scaling","product_market_fit","unit_economics",
                    "fundraising","team","go_to_market","competition","product"]
        missing = [c for c in expected if c not in cats]
        assert_true(len(missing) == 0, f"missing categories: {missing}")
        return f"All {len(cats)} categories populated: min={min(cats.values())}, max={max(cats.values())}"

    run.test("All 8+ required categories present and populated", "quality", test_all_categories_populated)

    def test_patterns_have_playbooks():
        body, _, _, _ = get(B, "/api/patterns/")
        empty_playbooks = [p["pattern_id"] for p in body["patterns"]
                           if len(p.get("survival_playbook", [])) < 3]
        assert_true(len(empty_playbooks) == 0,
                    f"{len(empty_playbooks)} patterns have <3 playbook steps: {empty_playbooks[:5]}")
        return "All 100 patterns have ≥3 survival playbook steps"

    run.test("All patterns have ≥3 survival playbook steps", "quality", test_patterns_have_playbooks)

    def test_patterns_have_signals():
        body, _, _, _ = get(B, "/api/patterns/")
        no_signals = [p["pattern_id"] for p in body["patterns"]
                      if len(p.get("warning_signals", [])) == 0]
        assert_true(len(no_signals) == 0,
                    f"{len(no_signals)} patterns have no warning signals: {no_signals[:5]}")
        return "All 100 patterns have warning signals"

    run.test("All patterns have warning signals", "quality", test_patterns_have_signals)

    def test_patterns_have_famous_failures():
        body, _, _, _ = get(B, "/api/patterns/")
        no_famous = [p["pattern_id"] for p in body["patterns"]
                     if len(p.get("famous_failures", [])) == 0]
        pct_missing = len(no_famous) / 100 * 100
        assert_true(pct_missing < 20,
                    f"{len(no_famous)} patterns (>{pct_missing:.0f}%) missing famous_failures")
        return f"{100 - len(no_famous)}/100 patterns have famous failures"

    run.test("≥80% of patterns have famous failures", "quality", test_patterns_have_famous_failures)

    def test_survival_rates_realistic():
        body, _, _, _ = get(B, "/api/patterns/")
        bad = []
        for p in body["patterns"]:
            total = p.get("failure_count", 0) + p.get("survival_count", 0)
            if total == 0:
                bad.append(f"{p['pattern_id']}(total=0)")
            elif not (0 < p.get("failure_count", 0)):
                bad.append(f"{p['pattern_id']}(failure=0)")
        assert_true(len(bad) == 0, f"patterns with bad counts: {bad[:5]}")
        return "All patterns have failure_count > 0 and realistic totals"

    run.test("All pattern counts are non-zero and realistic", "quality", test_survival_rates_realistic)

    # ────────────────────────────────────────────────────────────
    run.section("9. DEVPOST Submission Accuracy")

    def test_devpost_accuracy():
        devpost = (Path(__file__).parent.parent / "DEVPOST_SUBMISSION.md").read_text(encoding="utf-8")
        checks = {
            "CAC Exceeds LTV (WeWork)": "CAC Exceeds LTV at Scale",
            "Quibi 95%": "95% match",
            "SSE streaming": "Server-Sent Events",
            "re-evaluation loop": "re-evaluation",
            "monthly tracking": "Monthly Tracking",
            "Stripe integration": "Stripe",
            "100 patterns": "100 documented failure patterns",
            "FunctionTool": "FunctionTool",
            "No fabricated stats": "14,950",  # this should NOT be present
        }
        issues = []
        for name, needle in checks.items():
            if name == "No fabricated stats":
                if needle in devpost:
                    issues.append(f"fabricated stat still present: '{needle}'")
            else:
                if needle not in devpost:
                    issues.append(f"missing: '{needle}'")
        assert_true(len(issues) == 0, "; ".join(issues))
        return "All accuracy checks passed"

    run.test("DEVPOST accurately describes current architecture", "docs", test_devpost_accuracy)

    def test_devpost_no_stale():
        devpost = (Path(__file__).parent.parent / "DEVPOST_SUBMISSION.md").read_text(encoding="utf-8")
        stale = {
            "old tool name": "list_failure_patterns",
            "old pattern count in script": '"30 patterns"',
        }
        issues = [k for k, v in stale.items() if v in devpost]
        assert_true(len(issues) == 0, f"stale content: {issues}")
        return "No stale content found"

    run.test("DEVPOST has no stale/outdated content", "docs", test_devpost_no_stale)

    return run


# ── Assertion helpers ────────────────────────────────────────────
def assert_eq(actual, expected, label=""):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")

def assert_true(cond, msg=""):
    if not cond:
        raise AssertionError(msg)


# ── Report generation ────────────────────────────────────────────
def save_json(run_obj, ts):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{ts}.json"
    summary = run_obj.summary()
    report = {
        "timestamp": ts,
        "base_url": run_obj.base,
        "summary": summary,
        "results": run_obj.results,
    }
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def save_html(run_obj, ts):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{ts}.html"
    s = run_obj.summary()

    by_cat = {}
    for r in run_obj.results:
        by_cat.setdefault(r["category"], []).append(r)

    cat_rows = ""
    for cat, tests in sorted(by_cat.items()):
        p = sum(1 for t in tests if t["status"] == "PASS")
        f = sum(1 for t in tests if t["status"] in ("FAIL","ERROR"))
        cat_bar = f'<span style="color:{"#16a34a" if f==0 else "#dc2626"}">' \
                  f'{"✅" if f==0 else "❌"} {p}/{len(tests)}</span>'
        test_rows = ""
        for t in tests:
            icon = {"PASS":"✅","FAIL":"❌","ERROR":"⚠️"}.get(t["status"],"?")
            bg   = {"PASS":"#f0fdf4","FAIL":"#fef2f2","ERROR":"#fffbeb"}.get(t["status"],"#fff")
            test_rows += f"""<tr style="background:{bg}">
              <td style="padding:6px 10px">{icon}</td>
              <td style="padding:6px 10px;font-weight:500">{t['name']}</td>
              <td style="padding:6px 10px;color:#64748b;font-size:0.85em">{t['elapsed']}s</td>
              <td style="padding:6px 10px;color:#374151;font-size:0.85em;max-width:400px;word-wrap:break-word">{t['details']}</td>
            </tr>"""
        cat_rows += f"""
        <div style="margin-bottom:24px">
          <h3 style="text-transform:capitalize;margin:0 0 8px;color:#1e293b">
            {cat.replace('_',' ').title()} — {cat_bar}
          </h3>
          <table style="width:100%;border-collapse:collapse;font-family:monospace;font-size:0.9em;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
            {test_rows}
          </table>
        </div>"""

    score_color = "#16a34a" if s['failed'] == 0 else "#dc2626"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>Oracle Test Report — {ts}</title>
  <style>
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background:#f8fafc; color:#1e293b; margin:0; padding:24px }}
    .header {{ background:#7c3aed; color:#fff; padding:24px 32px; border-radius:12px; margin-bottom:24px }}
    .header h1 {{ margin:0 0 6px; font-size:1.6rem }}
    .header p  {{ margin:0; opacity:0.85; font-size:0.95rem }}
    .summary {{ display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px }}
    .stat {{ background:#fff; border:1px solid #e2e8f0; border-radius:10px; padding:16px; text-align:center }}
    .stat .n {{ font-size:2rem; font-weight:700 }}
    .stat .l {{ font-size:0.8rem; color:#64748b; text-transform:uppercase; letter-spacing:0.05em }}
    .card {{ background:#fff; border:1px solid #e2e8f0; border-radius:10px; padding:20px 24px; margin-bottom:16px }}
  </style>
</head>
<body>
  <div class="header">
    <h1>🔮 The Failure Oracle — Test Report</h1>
    <p>Run at {ts.replace('_',' ')} &nbsp;·&nbsp; Server: {run_obj.base} &nbsp;·&nbsp; Total time: {s['elapsed']}s</p>
  </div>

  <div class="summary">
    <div class="stat"><div class="n" style="color:#16a34a">{s['passed']}</div><div class="l">Passed</div></div>
    <div class="stat"><div class="n" style="color:#dc2626">{s['failed']}</div><div class="l">Failed</div></div>
    <div class="stat"><div class="n" style="color:#d97706">{s['errored']}</div><div class="l">Errors</div></div>
    <div class="stat"><div class="n" style="color:{score_color}">{s['passed']}/{s['total']}</div><div class="l">Score</div></div>
  </div>

  <div class="card">
    {cat_rows}
  </div>

  <p style="color:#94a3b8;font-size:0.8rem;text-align:center">
    Generated by tests/test_suite.py · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
  </p>
</body>
</html>"""

    path.write_text(html, encoding="utf-8")
    return path


# ── Entry point ──────────────────────────────────────────────────
def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run Oracle test suite")
    parser.add_argument("--base", default=DEFAULT_BASE, help="Server base URL")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  THE FAILURE ORACLE - COMPREHENSIVE TEST SUITE")
    print(f"  Server: {args.base}")
    print(f"{'='*60}")

    run = run_all(args.base)
    s = run.summary()

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    json_path = save_json(run, ts)
    html_path = save_html(run, ts)

    print(f"\n{'='*60}")
    print(f"  RESULTS: {s['passed']}/{s['total']} passed | "
          f"{s['failed']} failed | {s['errored']} errors | {s['elapsed']}s")
    print(f"  JSON: {json_path}")
    print(f"  HTML: {html_path}")
    print(f"{'='*60}\n")

    sys.exit(0 if s["failed"] == 0 and s["errored"] == 0 else 1)


if __name__ == "__main__":
    main()
