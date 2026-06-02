const API = '';  // Same origin

// ── Instant Demo Cache — stores real API results for instant replay ──────────
const _demoCache = {};   // key: startup_name → { events, challengerEvt, finalEvt }
const _DEMO_KEYS = { wework: 'WeWork (Q4 2019)', quibi: 'Quibi (Month 12 Projection)', theranos: 'Theranos (2015)', healthy: 'GrowthCo', dispute: 'HighVelocity AI' };

function _saveDemoResult(name, events, challengerEvt, finalEvt) {
  _demoCache[name] = { events, challengerEvt, finalEvt };
  try { localStorage.setItem('oracle_demo_' + name, JSON.stringify({ events: events.slice(-6), challengerEvt, finalEvt })); } catch(e) {}
}
function _loadDemoResult(name) {
  if (_demoCache[name]) return _demoCache[name];
  try {
    const s = localStorage.getItem('oracle_demo_' + name);
    if (s) { const d = JSON.parse(s); _demoCache[name] = d; return d; }
  } catch(e) {}
  return null;
}

// ── Demo Data ───────────────────────────────────────────────────
const DEMOS = {
  healthy: {
    startup_name: 'GrowthCo',
    current_month: 12,
    mrr: 120000,
    mrr_growth_rate: 0.22,
    churn_rate: 0.03,
    burn_rate: 80000,
    runway_months: 18,
    headcount: 10,
    nps: 58,
    cac: 1200,
    ltv: 14000,
    industry: 'B2B SaaS',
  },
  warning: {
    startup_name: 'Acme SaaS',
    current_month: 14,
    mrr: 85000,
    mrr_growth_rate: 0.18,
    churn_rate: 0.09,
    burn_rate: 120000,
    runway_months: 8,
    headcount: 12,
    nps: 31,
    cac: 1800,
    ltv: 9200,
    industry: 'B2B SaaS',
  },
  quibi: {
    startup_name: 'Quibi (Month 12 Projection)',
    current_month: 12,
    mrr: 420000,
    mrr_growth_rate: 0.02,
    churn_rate: 0.28,
    burn_rate: 8500000,
    runway_months: 8,
    headcount: 185,
    nps: 4,
    cac: 48000,
    ltv: 8000,
    industry: 'Consumer',
  },
  wework: {
    startup_name: 'WeWork (Q4 2019)',
    current_month: 20,
    mrr: 2900000,
    mrr_growth_rate: 0.14,
    churn_rate: 0.16,
    burn_rate: 22000000,
    runway_months: 7,
    headcount: 14000,
    nps: 18,
    cac: 38000,
    ltv: 19000,
    industry: 'Marketplace',
  },
  theranos: {
    startup_name: 'Theranos (2015)',
    current_month: 24,
    mrr: 18000,
    mrr_growth_rate: 0.01,
    churn_rate: 0.45,
    burn_rate: 5800000,
    runway_months: 6,
    headcount: 800,
    nps: -42,
    cac: 95000,
    ltv: 8000,
    industry: 'Healthtech',
  },
  fintech: {
    startup_name: 'NeoBank X (Q2 2023)',
    current_month: 18,
    mrr: 340000,
    mrr_growth_rate: 0.06,
    churn_rate: 0.14,
    burn_rate: 4200000,
    runway_months: 9,
    headcount: 62,
    nps: 22,
    cac: 320,
    ltv: 2100,
    industry: 'Fintech',
  },
  b2c: {
    startup_name: 'ConsumerApp Y',
    current_month: 10,
    mrr: 95000,
    mrr_growth_rate: 0.09,
    churn_rate: 0.19,
    burn_rate: 780000,
    runway_months: 11,
    headcount: 22,
    nps: 15,
    cac: 48,
    ltv: 210,
    industry: 'B2C',
  },
  // Mixed-signal scenario: some failure flags + strong counter-evidence → designed to trigger Challenger DISPUTE
  dispute: {
    startup_name: 'HighVelocity AI',
    current_month: 10,
    mrr: 260000,
    mrr_growth_rate: 0.38,   // 38% MoM — exceptional growth (strong counter-evidence)
    churn_rate: 0.07,         // 7% — above 5% threshold (failure signal)
    burn_rate: 750000,        // high burn relative to MRR (failure signal)
    runway_months: 9,         // short runway (failure signal)
    headcount: 28,
    nps: 68,                  // NPS 68 — excellent customer satisfaction (strong counter-evidence)
    cac: 2200,
    ltv: 18000,               // 8.2x LTV:CAC — exceptional unit economics (strong counter-evidence)
    industry: 'B2B SaaS',
  },
};

// ── SaaS Benchmarks for live field health ───────────────────────
const BENCHMARKS = {
  mrr_growth_rate: { good: 0.15, warn: 0.08, label: 'Monthly growth', fmt: v => `${(v*100).toFixed(0)}%`, goodMsg: '>15%', warnMsg: '8-15%', badMsg: '<8%' },
  churn_rate:      { good: 0.05, warn: 0.08, invert: true, label: 'Churn', fmt: v => `${(v*100).toFixed(0)}%`, goodMsg: '<5%', warnMsg: '5-8%', badMsg: '>8%' },
  runway_months:   { good: 18, warn: 9, label: 'Runway', fmt: v => `${v}mo`, goodMsg: '>18mo', warnMsg: '9-18mo', badMsg: '<9mo' },
  nps:             { good: 50, warn: 30, label: 'NPS', fmt: v => `${v}`, goodMsg: '>50', warnMsg: '30-50', badMsg: '<30' },
};

function getBenchmarkStatus(field, value) {
  const b = BENCHMARKS[field];
  if (!b) return null;
  const { good, warn, invert } = b;
  if (invert) return value <= good ? 'good' : value <= warn ? 'warn' : 'bad';
  return value >= good ? 'good' : value >= warn ? 'warn' : 'bad';
}

function attachLiveIndicators() {
  Object.entries(BENCHMARKS).forEach(([field, b]) => {
    const input = document.getElementById(field);
    if (!input) return;
    const wrap = input.parentElement;
    // Create indicator badge
    const badge = document.createElement('div');
    badge.className = 'bench-badge hidden';
    badge.id = `bench-${field}`;
    wrap.appendChild(badge);

    input.addEventListener('input', () => {
      const v = parseFloat(input.value);
      if (isNaN(v) || input.value === '') {
        badge.classList.add('hidden');
        input.classList.remove('field-good', 'field-warn', 'field-bad');
        return;
      }
      const status = getBenchmarkStatus(field, v);
      badge.classList.remove('hidden', 'bench-good', 'bench-warn', 'bench-bad');
      badge.classList.add(`bench-${status}`);
      input.classList.remove('field-good', 'field-warn', 'field-bad');
      input.classList.add(`field-${status}`);
      const icons = { good: '✓', warn: '▲', bad: '✗' };
      const msgs  = { good: b.goodMsg, warn: b.warnMsg, bad: b.badMsg };
      badge.textContent = `${icons[status]} ${b.fmt(v)} — target: ${msgs[status]}`;
    });
    // Trigger on existing value
    input.dispatchEvent(new Event('input'));
  });
}

const CAT_LABELS = {
  premature_scaling: 'Premature Scaling',
  product_market_fit: 'Product-Market Fit',
  unit_economics: 'Unit Economics',
  fundraising: 'Fundraising',
  team: 'Team',
  go_to_market: 'Go-To-Market',
  competition: 'Competition',
  product: 'Product',
  pivot: 'Pivot',
};

// ── App initialisation ───────────────────────────────────────────
window.addEventListener('load', () => {
  loadPatternLibrary();
  attachLiveIndicators();
  checkBackendHealth();
  loadLiveStats();
  renderHistory();
  renderTrendChart();
  initPortfolio();
  loadSharedReport();
  updateLiveMetrics();
});

async function loadLiveStats() {
  try {
    const res = await fetch(`${API}/api/stats`, { signal: AbortSignal.timeout(6000) });
    if (!res.ok) return;
    const d = await res.json();
    const bar = document.getElementById('live-stats-bar');
    if (!bar) return;
    bar.classList.remove('hidden');
    const fallback = document.getElementById('fallback-stats-bar');
    if (fallback) fallback.classList.add('hidden');

    const fmt = n => n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);

    function animateStat(id, value) {
      const el = document.getElementById(id);
      if (!el) return;
      const start = performance.now();
      const duration = 1000;
      const step = (now) => {
        const t = Math.min((now - start) / duration, 1);
        const ease = 1 - Math.pow(1 - t, 3);
        el.textContent = fmt(Math.round(value * ease));
        if (t < 1) requestAnimationFrame(step);
        else el.textContent = fmt(value);
      };
      requestAnimationFrame(step);
    }

    animateStat('ls-analyses',  d.total_analyses);
    animateStat('ls-monitored', d.startups_monitored);
    animateStat('ls-alerts',    d.alerts_today);
    animateStat('ls-patterns',  d.pattern_count);
    // Live integration proof — populated only if the backend exposes the fields
    if (typeof d.mcp_calls_24h === 'number')       animateStat('ls-mcp-calls',        d.mcp_calls_24h);
    if (typeof d.vector_searches_24h === 'number') animateStat('ls-vector-searches',  d.vector_searches_24h);
    if (typeof d.gemini_calls_24h === 'number')    animateStat('ls-gemini-calls',     d.gemini_calls_24h);
  } catch (_) {
    // Silently fail — live stats are additive, not required
  }
}

async function checkBackendHealth() {
  try {
    const res = await fetch(`${API}/api/health`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    document.getElementById('offline-banner')?.classList.add('hidden');
  } catch {
    document.getElementById('offline-banner')?.classList.remove('hidden');
  }
}

function fillDemo(type) {
  const d = DEMOS[type];
  Object.keys(d).forEach((key) => {
    const el = document.getElementById(key);
    if (!el) return;
    el.value = d[key];
    el.dispatchEvent(new Event('input'));
  });
  updateLiveMetrics();
}

async function playInstantDemo(demoKey) {
  const cached = _loadDemoResult(demoKey);
  _suppressFillDemoAutoRun = true;
  fillDemo(demoKey);
  _suppressFillDemoAutoRun = false;

  collapseExamples();

  // Hide old results
  ['alert-section','safe-section','challenger-panel','cocktail-panel',
   'oracle-score-card','risk-banner','premortem-cta'].forEach(id => {
    const el = document.getElementById(id); if (el) el.classList.add('hidden');
  });
  document.getElementById('tab-btn-escape')?.classList.remove('has-data');

  // Show terminal with instant replay
  const terminal = document.getElementById('agent-terminal');
  const termBody  = document.getElementById('terminal-body');
  const pill      = document.getElementById('terminal-pill');
  if (terminal) terminal.classList.remove('hidden');
  if (pill) pill.classList.add('hidden');
  if (termBody) termBody.innerHTML = '';

  const addLine = (icon, msg, cls='') => {
    if (!termBody) return;
    const p = document.createElement('div');
    p.className = 'terminal-line' + (cls ? ' '+cls : '');
    const hl = s => s.replace(/(MongoDB[^,.<\s]*|Gemini[^,.<\s]*|MCP|Vector Search|ADK)/g, '<span class="highlight">$1</span>');
    p.innerHTML = `${icon} ${hl(msg)}`;
    termBody.appendChild(p);
    termBody.scrollTop = termBody.scrollHeight;
  };

  const terminalLines = [
    ['>', 'Starting Oracle pipeline — MongoDB Voyage AI (embed) → Atlas Vector Search + BM25 RRF → MongoDB MCP → Gemini Flash scoring...'],
    ['[agent]', 'Oracle Pipeline starting — ADK SequentialAgent: Investigator → Challenger → Reporter'],
    ['[step]', 'Step 1 — Investigator: MongoDB Voyage AI voyage-4-large (1024-dim) embedding → MongoDB Atlas Vector Search + BM25 RRF → MCP category context → Gemini Flash scoring'],
    ['[search]', 'Hybrid retrieval: MongoDB Atlas Vector Search (cosine similarity) + Atlas Search (BM25) → Reciprocal Rank Fusion...'],
    ['[ok]', 'Vector Search: 10 vector results merged → top 5 candidates'],
    ['[agent]', 'Gemini Flash scoring 5 candidates in parallel (thinking_budget=0)...'],
  ];

  if (!cached) {
    // No cache — run real analysis
    addLine('[run]', 'Running live analysis... (first run takes ~40s, subsequent runs are instant)', 'terminal-warn');
    await runAnalysis();
    return;
  }

  // Instant replay with staggered terminal lines
  for (let i = 0; i < terminalLines.length; i++) {
    await new Promise(r => setTimeout(r, 80));
    addLine(terminalLines[i][0], terminalLines[i][1]);
  }

  const finalData = cached.finalEvt;
  const challengerData = cached.challengerEvt;

  if (finalData?.alert) {
    addLine('[warn]', `Pattern confirmed: ${finalData.pattern?.pattern_name} at ${Math.round((finalData.pattern?.confidence||0)*100)}% — Challenger adversarial verification complete`, 'terminal-alert');
  } else {
    addLine('[ok]', 'No dangerous failure patterns detected. Metrics look healthy.', 'terminal-safe');
  }

  await new Promise(r => setTimeout(r, 300));

  // Collapse terminal properly (update tp-label, not textContent which destroys child spans)
  collapseTerminal();
  const tpLabel = document.getElementById('tp-label');
  if (tpLabel) {
    tpLabel.textContent = finalData?.alert
      ? `${finalData.pattern?.pattern_name} — ${Math.round((finalData.pattern?.confidence||0)*100)}% match`
      : 'No dangerous patterns detected';
  }

  // Set _lastPayload from demo preset so back-to-form bar and monitoring work
  _lastPayload = DEMOS[demoKey] || null;

  _lastResult = finalData;
  renderResult(finalData);
  if (challengerData && finalData?.alert) renderChallenger(challengerData);
  saveSnapshot(finalData, DEMOS[demoKey]);

  // Show "instant demo" badge
  const badge = document.getElementById('instant-demo-badge');
  if (badge) { badge.classList.remove('hidden'); setTimeout(() => badge.classList.add('hidden'), 4000); }
}

function toggleGlossary() {
  const body = document.getElementById('glossary-body');
  const toggle = document.getElementById('glossary-toggle');
  body.classList.toggle('hidden');
  toggle.textContent = body.classList.contains('hidden') ? 'Show ▾' : 'Hide ▴';
}

// ── Theme Toggle ─────────────────────────────────────────────────
function updateThemeUI(theme) {
  const isDark = theme === 'dark';
  const iconHtml = isDark 
    ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>' 
    : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>';
  
  const btn = document.getElementById('theme-btn');
  if (btn) btn.innerHTML = iconHtml;
  
  const btnMobile = document.getElementById('theme-btn-mobile');
  if (btnMobile) btnMobile.innerHTML = iconHtml;

  const btnLanding = document.getElementById('theme-btn-landing');
  if (btnLanding) btnLanding.innerHTML = iconHtml;
}

function toggleTheme() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const next = isDark ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('oracle_theme', next);
  updateThemeUI(next);
}

// Sync button icon on load
window.addEventListener('DOMContentLoaded', () => {
  const theme = localStorage.getItem('oracle_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', theme);
  updateThemeUI(theme);

  // Restore the active tab from the URL hash on refresh
  // (the inline pre-paint script already hid the landing for deep links)
  const _hashTab = (location.hash || '').replace('#', '');
  if (['tab-dashboard','tab-auditor','tab-portfolio','tab-cohort','tab-library','tab-submit'].includes(_hashTab)) {
    switchTab(_hashTab);
  }

  // Landing motion & signature gauge
  initReveals();
  initCountUp();
  initHeroGauge();

  // Pre-fill form from shared URL (e.g. ?startup_name=Quibi&mrr=420000&...)
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has('startup_name')) {
    const fields = ['startup_name','current_month','mrr','mrr_growth_rate',
                    'churn_rate','burn_rate','runway_months','headcount',
                    'nps','cac','ltv','industry'];
    fields.forEach(key => {
      const el = document.getElementById(key);
      if (el && urlParams.has(key)) el.value = urlParams.get(key);
    });
    // Shared link → skip the landing and run the analysis immediately
    enterApp('tab-dashboard');
    updateLiveMetrics();
    // Clean URL without losing the page, then auto-run
    window.history.replaceState({}, '', window.location.pathname);
    setTimeout(() => runAnalysis(), 400);
  }
});

// ── Form Submit ─────────────────────────────────────────────────
document.getElementById('metrics-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  await runAnalysis();
});

// Store last result for download/share
let _lastResult = null;
let _lastPayload = null;

function collapseExamples() {
  ['demo-section','backtest-section'].forEach(id => {
    const el = document.getElementById(id) || document.querySelector('.' + id);
    if (el) el.classList.add('examples-collapsed');
  });
  const bar = document.getElementById('examples-restore-bar');
  if (bar) bar.classList.remove('hidden');
}

function expandExamples() {
  ['demo-section','backtest-section'].forEach(id => {
    const el = document.getElementById(id) || document.querySelector('.' + id);
    if (el) el.classList.remove('examples-collapsed');
  });
  const bar = document.getElementById('examples-restore-bar');
  if (bar) bar.classList.add('hidden');
  document.querySelector('.demo-section')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function runAnalysis() {
  const btnText    = document.getElementById('btn-text');
  const btnSpinner = document.getElementById('btn-spinner');
  btnText.classList.add('hidden');
  btnSpinner.classList.remove('hidden');

  collapseExamples();
  teardownStickyResultTabs();

  hide('alert-section');
  hide('safe-section');
  hide('early-warning-banner');
  hide('risk-banner');
  hide('challenger-panel');
  hide('accuracy-showcase');
  hide('alert-lib-link');
  hide('oracle-score-card');
  hide('osc-legend');
  hide('recovery-card');
  hide('escape-plan-panel');
  hide('cocktail-panel');
  hide('cascade-panel');
  hide('conf-forecast-section');
  hide('sources-block');

  const payload = {
    startup_name:    val('startup_name'),
    current_month:   num('current_month'),
    mrr:             num('mrr'),
    mrr_growth_rate: num('mrr_growth_rate'),
    churn_rate:      num('churn_rate'),
    burn_rate:       num('burn_rate'),
    runway_months:   num('runway_months'),
    headcount:       num('headcount'),
    nps:             num('nps'),
    cac:             num('cac'),
    ltv:             num('ltv'),
    industry:        val('industry'),
  };
  _lastPayload = payload;

  const terminal = document.getElementById('agent-terminal');
  const termBody = document.getElementById('terminal-body');
  const pill     = document.getElementById('terminal-pill');
  terminal.classList.remove('hidden');
  if (pill) pill.classList.add('hidden');
  termBody.innerHTML = '';

  const _stripEmoji = (s) => (s || '').replace(
    /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE00}-\u{FEFF}\u{1F000}-\u{1F02F}\u{1F0A0}-\u{1F0FF}\u{1F100}-\u{1F1FF}\u{1F200}-\u{1F2FF}\u{1F900}-\u{1F9FF}\u{2300}-\u{23FF}\u{2B50}\u{2B55}\u{2934}\u{2935}\u{25AA}-\u{25FE}\u{00A9}\u{00AE}]/gu, ''
  ).trim();

  function addTermLine(icon, msg, cls = '') {
    const p = document.createElement('div');
    p.className = 'terminal-line' + (cls ? ' ' + cls : '');
    const highlight = (s) => s.replace(/(MongoDB[^,.<\s]*|Gemini[^,.<\s]*|MCP|Vector Search|ADK)/g,
      '<span class="highlight">$1</span>');
    // Map emoji icons to clean text prefixes
    const iconMap = { '[agent]':'[agent]','[step]':'[step]','[ok]':'[ok]','[search]':'[search]','[db]':'[db]',
      '[run]':'[run]','[score]':'[score]','[retry]':'[retry]','[verify]':'[verify]','[warn]':'[warn]',
      '💾':'[save]','🌐':'[net]','>>':'>>' };
    const cleanIcon = iconMap[icon] || _stripEmoji(icon) || '>';
    const cleanMsg  = _stripEmoji(msg);
    p.innerHTML = `<span class="term-icon">${cleanIcon}</span> ${highlight(cleanMsg)}`;
    termBody.appendChild(p);
    termBody.scrollTop = termBody.scrollHeight;
  }

  addTermLine('>', 'Starting Oracle pipeline — MongoDB Voyage AI (embed) → Atlas Vector Search + BM25 RRF → MongoDB MCP → Gemini Flash scoring...');

  try {
    const response = await fetch(`${API}/api/metrics/analyze/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalData = null;
    let challengerData = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const evt = JSON.parse(line.slice(6));
          if (evt.type === 'step') {
            addTermLine(evt.icon || '>', evt.message);
          } else if (evt.type === 'result') {
            addTermLine('', `Pattern confirmed: <span class="highlight">${evt.pattern?.pattern_name}</span> — ${Math.round((evt.pattern?.confidence||0)*100)}% match score`, 'terminal-alert');
            finalData = {
              alert: true,
              startup_name: evt.startup_name,
              pattern: evt.pattern,
              cocktail: evt.cocktail || null,
              cascade: evt.cascade || null,
              message: evt.message,
              oracle_score: evt.oracle_score,
              score_band: evt.score_band,
              oracle_breakdown: evt.oracle_breakdown || null,
              trajectory: evt.trajectory || null,
              recovery_scenario: evt.recovery_scenario,
              escape_plan: evt.escape_plan,
            };
          } else if (evt.type === 'safe') {
            addTermLine('', evt.message, evt.uncharted?.is_uncharted ? 'terminal-warn' : 'terminal-safe');
            finalData = {
              alert: false,
              startup_name: payload.startup_name,
              cocktail: evt.cocktail || null,
              message: evt.message,
              oracle_score: evt.oracle_score,
              score_band: evt.score_band,
              oracle_breakdown: evt.oracle_breakdown || null,
              trajectory: evt.trajectory || null,
              uncharted: evt.uncharted || null,
            };
          } else if (evt.type === 'challenger') {
            challengerData = evt;
          } else if (evt.type === 'error') {
            addTermLine('⚠', evt.message, 'terminal-warn');
          }
        } catch (_) {}
      }
    }

    await new Promise(r => setTimeout(r, 800));
    collapseTerminal();

    if (finalData) {
      _lastResult = finalData;
      renderResult(finalData);
      saveSnapshot(finalData, payload); // monthly tracking
      if (challengerData && finalData.alert) renderChallenger(challengerData);
      // Cache result for instant demo replay
      const demoKey = Object.entries(_DEMO_KEYS).find(([k,v]) => v === payload.startup_name)?.[0];
      if (demoKey) _saveDemoResult(demoKey, [], challengerData, finalData);
    }
  } catch (err) {
    // SSE failed — fall back to regular endpoint
    try {
      addTermLine('', 'Streaming unavailable, using standard endpoint...');
      const res = await fetch(`${API}/api/metrics/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      collapseTerminal();
      _lastResult = data;
      renderResult(data);
      saveSnapshot(data, payload);
    } catch (err2) {
      collapseTerminal();
      alert('Error connecting to Oracle API. Is the server running?');
      console.error(err2);
    }
  } finally {
    btnText.classList.remove('hidden');
    btnSpinner.classList.add('hidden');
  }
}

// ── Terminal collapse / expand ───────────────────────────────────
function collapseTerminal() {
  const terminal = document.getElementById('agent-terminal');
  const pill     = document.getElementById('terminal-pill');
  const body     = document.getElementById('terminal-body');
  const lineCount = body ? body.children.length : 0;
  if (terminal) terminal.classList.add('hidden');
  if (pill) {
    const lbl = document.getElementById('tp-label');
    if (lbl) lbl.textContent = `Agent execution log — ${lineCount} steps`;
    pill.classList.remove('hidden');
  }
}

function toggleTerminal() {
  const terminal = document.getElementById('agent-terminal');
  const pill     = document.getElementById('terminal-pill');
  const btn      = document.getElementById('terminal-collapse-btn');
  if (!terminal) return;
  const isHidden = terminal.classList.contains('hidden');
  if (isHidden) {
    terminal.classList.remove('hidden');
    if (pill) pill.classList.add('hidden');
    // Scroll terminal into view
    terminal.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } else {
    terminal.classList.add('hidden');
    if (pill) pill.classList.remove('hidden');
  }
}

// ── Challenger Agent render ──────────────────────────────────────
function renderChallenger(c) {
  const panel = document.getElementById('challenger-panel');
  if (!panel) return;

  const isConfirm = c.verdict === 'CONFIRM';
  const invPct    = Math.round((c.investigator_confidence || 0) * 100);
  const challPct  = Math.round((c.confidence || 0) * 100);

  panel.className = `challenger-panel ${isConfirm ? 'chp-confirm' : 'chp-dispute'}`;

  document.getElementById('chp-icon').textContent  = isConfirm ? '[ok]' : '[run]';
  document.getElementById('chp-title').textContent = isConfirm
    ? 'Both agents confirm this pattern'
    : 'Agents disagree — review carefully';

  const badge = document.getElementById('chp-badge');
  badge.textContent = isConfirm ? 'CONFIRMED' : 'DISPUTED';
  badge.className = `chp-badge ${isConfirm ? 'chp-badge-confirm' : 'chp-badge-dispute'}`;

  document.getElementById('chp-reasoning').textContent = c.reasoning || '';

  const counterWrap = document.getElementById('chp-counter-wrap');
  const counterEl   = document.getElementById('chp-counter');
  if (c.strongest_counter && !isConfirm) {
    counterEl.textContent = c.strongest_counter;
    counterWrap.classList.remove('hidden');
  } else {
    counterWrap.classList.add('hidden');
  }

  document.getElementById('chp-inv-pct').textContent   = `${invPct}%`;
  document.getElementById('chp-chall-pct').textContent = `${challPct}%`;

  // Delta between agents
  const deltaEl = document.getElementById('chp-delta');
  if (deltaEl) {
    const dp = c.delta_pp ?? Math.abs(invPct - challPct);
    if (!isConfirm) {
      deltaEl.textContent = `Δ${dp}pp`;
      deltaEl.className = 'chp-delta chp-delta-dispute';
      deltaEl.title = `Confidence gap: ${dp}pp — agents disagree (>10pp threshold for DISPUTE)`;
    } else {
      deltaEl.textContent = dp > 0 ? `Δ${dp}pp` : '=';
      deltaEl.className = 'chp-delta chp-delta-confirm';
      deltaEl.title = `Confidence gap: ${dp}pp — within 10pp agreement threshold`;
    }
  }

  // Animate bars
  const invBar   = document.getElementById('chp-bar-inv');
  const challBar = document.getElementById('chp-bar-chall');
  if (invBar)   invBar.style.width   = '0%';
  if (challBar) challBar.style.width = '0%';
  setTimeout(() => {
    if (invBar)   invBar.style.width   = `${invPct}%`;
    if (challBar) challBar.style.width = `${challPct}%`;
    if (!isConfirm) challBar.style.background = '#f59e0b';
  }, 80);

  panel.classList.remove('hidden');
}

// ── 7. Counter animation ─────────────────────────────────────────
function animateCounter(el, target, suffix = '', duration = 1200) {
  const start = performance.now();
  const isFloat = typeof target === 'string' && target.includes('%');
  const targetNum = parseFloat(target);
  function step(now) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    const ease = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    const current = Math.round(targetNum * ease);
    el.textContent = current + suffix;
    if (progress < 1) requestAnimationFrame(step);
    else el.textContent = target;
  }
  requestAnimationFrame(step);
}

// ── Result Rendering ─────────────────────────────────────────────
function renderOracleScore(score, band, breakdown) {
  const card = document.getElementById('oracle-score-card');
  if (!card || typeof score !== 'number') return;

  const valEl       = document.getElementById('osc-value');
  const bandEl      = document.getElementById('osc-band');
  const barEl       = document.getElementById('osc-bar-fill');
  const tipEl       = document.getElementById('osc-tip');
  const auditBtn    = document.getElementById('osc-audit-btn');
  const breakdownEl = document.getElementById('osc-breakdown');

  const bandText = {
    strong:   'STRONG · Healthy trajectory',
    watch:    'WATCH · Monitor weekly',
    warning:  'WARNING · Course correct now',
    critical: 'CRITICAL · Take action this week',
  }[band] || band.toUpperCase();

  const ringColor = { strong: '#10b981', watch: '#f59e0b', warning: '#f97316', critical: '#ef4444' }[band] || '#6366f1';
  const radius = 44, circ = 2 * Math.PI * radius;
  const offset = circ * (1 - score / 100);

  // Inject animated ring gauge into the left column
  const oscLeft = card.querySelector('.osc-left');
  if (oscLeft) {
    let ringWrap = oscLeft.querySelector('.osc-ring-wrap');
    if (!ringWrap) {
      ringWrap = document.createElement('div');
      ringWrap.className = 'osc-ring-wrap';
      oscLeft.prepend(ringWrap);
    }
    ringWrap.innerHTML = `
      <svg class="osc-ring-svg" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="${radius}" fill="none" stroke="var(--border)" stroke-width="7"/>
        <circle cx="50" cy="50" r="${radius}" fill="none" stroke="${ringColor}" stroke-width="7"
          stroke-linecap="round" transform="rotate(-90 50 50)"
          stroke-dasharray="${circ.toFixed(1)}" stroke-dashoffset="${circ.toFixed(1)}"
          class="osc-ring-arc" data-target="${offset.toFixed(1)}"/>
        <text x="50" y="46" text-anchor="middle" fill="${ringColor}" class="osc-ring-num">${score}</text>
        <text x="50" y="62" text-anchor="middle" fill="var(--muted)" class="osc-ring-label">${band.toUpperCase()}</text>
      </svg>`;
    // Animate after paint
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const arc = ringWrap.querySelector('.osc-ring-arc');
      if (arc) arc.style.strokeDashoffset = offset.toFixed(1);
    }));
  }

  if (valEl)  { valEl.textContent = score; valEl.dataset.band = band; }
  if (bandEl) { bandEl.textContent = bandText; bandEl.dataset.band = band; }
  if (barEl)  { barEl.dataset.band = band; barEl.style.width = '0%'; setTimeout(() => barEl.style.width = `${score}%`, 80); }
  if (tipEl)  { tipEl.textContent = `Composite of all 11 metrics + pattern match. ${score}/100.`; }

  // Audit breakdown
  if (auditBtn && breakdownEl && breakdown?.rows) {
    auditBtn.classList.remove('hidden');
    auditBtn.textContent = 'Audit formula ▾';
    breakdownEl.classList.add('hidden');

    const rows = breakdown.rows.filter(r => r.label !== 'Base score');
    breakdownEl.innerHTML = `
      <table class="osc-audit-table">
        <thead><tr><th>Component</th><th>Impact</th><th>Calculation</th></tr></thead>
        <tbody>
          <tr class="osc-audit-base"><td>Base score</td><td>100</td><td>Starting point</td></tr>
          ${rows.map(r => {
            const v = r.value;
            const cls = v > 0 ? 'osc-bonus' : v < 0 ? 'osc-penalty' : 'osc-neutral';
            const sign = v > 0 ? '+' : '';
            return `<tr><td>${r.label}</td><td class="${cls}">${sign}${v}</td><td>${r.detail}</td></tr>`;
          }).join('')}
          <tr class="osc-audit-total"><td><strong>Final score</strong></td><td><strong>${score}</strong></td><td>${band.toUpperCase()}</td></tr>
        </tbody>
      </table>`;

    auditBtn.onclick = () => {
      const open = !breakdownEl.classList.contains('hidden');
      breakdownEl.classList.toggle('hidden', open);
      auditBtn.textContent = open ? 'Audit formula ▾' : 'Audit formula ▴';
    };
  } else if (auditBtn) {
    auditBtn.classList.add('hidden');
  }

  card.dataset.band = band;
  card.classList.remove('hidden');
  const legend = document.getElementById('osc-legend');
  if (legend) legend.classList.remove('hidden');
}

function renderRecovery(scenario) {
  const card = document.getElementById('recovery-card');
  if (!card || !scenario || !scenario.improvements?.length) {
    if (card) card.classList.add('hidden');
    return;
  }

  const deltaEl = document.getElementById('rec-delta');
  const listEl  = document.getElementById('rec-list');
  const subEl   = document.getElementById('rec-sub');

  if (deltaEl) deltaEl.textContent = `+${scenario.score_delta}`;
  if (subEl)   subEl.textContent   = `Pattern similarity would drop to ${Math.round((scenario.confidence || 0) * 100)}%`;
  if (listEl) {
    listEl.innerHTML = scenario.improvements.map(s => `<li>${s}</li>`).join('');
  }
  card.classList.remove('hidden');
}

function renderResult(data) {
  // Render Oracle Score on both paths (alert and safe)
  if (typeof data.oracle_score === 'number') {
    renderOracleScore(data.oracle_score, data.score_band || 'watch', data.oracle_breakdown);
  }

  // Trend delta + confidence trajectory forecast — backend trajectory preferred, localStorage fallback
  const startupName = _lastPayload?.startup_name || data.startup_name || '';
  renderTrendDelta(data, startupName);
  renderConfidenceForecast(startupName, data.trajectory);

  if (!data.alert) {
    hide('risk-banner');
    const safeSection = document.getElementById('safe-section');
    if (safeSection) {
      const u = data.uncharted;
      if (u && u.is_uncharted) {
        safeSection.querySelector('h2').textContent = 'Uncharted Territory';
        safeSection.querySelector('p').innerHTML =
          `Your metrics don't closely resemble any of the 100 documented failure patterns ` +
          `(best match: <strong>${u.best_confidence}%</strong>` +
          (u.closest_pattern ? ` with <em>${u.closest_pattern}</em>` : '') +
          `). This could mean you're operating outside known failure modes — or in an early stage ` +
          `before patterns become visible. Treat as low-confidence and re-run monthly.`;
        safeSection.classList.add('uncharted-card');
      } else {
        safeSection.querySelector('h2').textContent = 'No Dangerous Patterns Detected';
        safeSection.querySelector('p').innerHTML =
          `Your current metrics don't match any of the 100 documented high-risk failure patterns. Your trajectory looks healthy for this stage.`;
        safeSection.classList.remove('uncharted-card');
      }
    }
    collapseTerminal();
    teardownStickyResultTabs();
    show('safe-section');
    setTimeout(() => document.getElementById('safe-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
    return;
  }

  switchResultTab('result-tab-overview');

  // Recovery scenario only meaningful on alert
  if (data.recovery_scenario) renderRecovery(data.recovery_scenario);

  // Escape Plan — ranked interventions to drop below danger threshold
  if (data.escape_plan) renderEscapePlan(data.escape_plan);
  else { document.getElementById('tab-btn-escape')?.classList.remove('has-data'); }

  // Cocktail Detection — co-occurring failure patterns
  if (data.cocktail) renderCocktail(data.cocktail);
  else hide('cocktail-panel');

  // Failure Cascade Graph — $graphLookup collapse timeline
  if (data.cascade) renderCascade(data.cascade);

  // Pre-Mortem CTA — show whenever we have an alert
  const pmCta = document.getElementById('premortem-cta');
  if (pmCta) pmCta.classList.remove('hidden');

  // Back-to-form bar — stamp startup name
  const btfName = document.getElementById('btf-startup-name');
  if (btfName && _lastPayload?.startup_name) btfName.textContent = _lastPayload.startup_name;

  const p = data.pattern;
  const pct = Math.round(p.confidence * 100);

  // Risk level banner
  const banner = document.getElementById('risk-banner');
  const bannerIcon = document.getElementById('risk-banner-icon');
  const bannerLabel = document.getElementById('risk-banner-label');
  const bannerText = document.getElementById('risk-banner-text');
  if (banner) {
    let lvl, icon, cls, msg;
    if (pct >= 88) {
      lvl = 'CRITICAL'; icon = ''; cls = 'risk-banner-critical';
      msg = `${pct}% match — Crisis-level signal. Companies at this stage with these metrics failed in ${p.days_to_crisis} days on average. Act immediately.`;
      // Visceral screen shift — red vignette on CRITICAL
      document.documentElement.classList.add('body-critical');
      setTimeout(() => document.documentElement.classList.remove('body-critical'), 6000);
    } else if (pct >= 75) {
      lvl = 'HIGH RISK'; icon = ''; cls = 'risk-banner-high';
      msg = `${pct}% match — Strong warning signal. You have a narrow window to course-correct before this pattern becomes irreversible.`;
      document.documentElement.classList.remove('body-critical');
    } else {
      lvl = 'MODERATE'; icon = ''; cls = 'risk-banner-medium';
      msg = `${pct}% match — Early indicators present. Monitor closely and address the warning signals below.`;
      document.documentElement.classList.remove('body-critical');
    }
    banner.className = `risk-banner ${cls}`;
    bannerIcon.textContent = icon;
    bannerLabel.textContent = lvl;
    bannerText.textContent = msg;
    banner.classList.remove('hidden');
  }

  // Header
  setText('alert-title', `${p.pattern_name}`);
  const libLink = document.getElementById('alert-lib-link');
  if (libLink) {
    libLink.textContent = 'View in Pattern Library →';
    libLink.onclick = () => jumpToPattern(p.pattern_id);
    libLink.classList.remove('hidden');
  }

  // 2. Confidence bar — animate from 0 + 8. color coding
  const bar = document.getElementById('conf-bar');
  if (bar) {
    bar.style.width = '0%';
    bar.className = 'bar-fill ' + (pct >= 85 ? 'bar-danger' : pct >= 70 ? 'bar-warning' : 'bar-safe');
    setTimeout(() => { bar.style.width = `${pct}%`; }, 80);
  }

  // Confidence pct — count up
  const confEl = document.getElementById('conf-pct');
  if (confEl) {
    confEl.textContent = '0%';
    setTimeout(() => animateCounter(confEl, pct, '%'), 80);
  }

  // SVGRadial Gauge update
  const gaugeCircle = document.getElementById('gauge-fill-circle');
  if (gaugeCircle) {
    const radius = parseFloat(gaugeCircle.getAttribute('r')) || 40;
    const circumference = 2 * Math.PI * radius; // ~251.2
    gaugeCircle.style.strokeDasharray = circumference;
    const offset = circumference - (pct / 100) * circumference;
    gaugeCircle.style.strokeDashoffset = circumference; // reset first
    
    // Set gauge fill colors based on confidence level
    const fillClass = pct >= 85 ? 'gauge-danger' : pct >= 70 ? 'gauge-warning' : 'gauge-safe';
    gaugeCircle.className.baseVal = `radial-gauge-fill ${fillClass}`;
    
    setTimeout(() => {
      gaugeCircle.style.strokeDashoffset = offset;
    }, 80);
  }
  const confGaugeEl = document.getElementById('conf-pct-gauge');
  if (confGaugeEl) {
    confGaugeEl.textContent = '0%';
    setTimeout(() => animateCounter(confGaugeEl, pct, '%'), 80);
  }

  // Pattern ID badge
  setText('alert-pattern-id', p.pattern_id);

  // Narrative
  setText('alert-narrative', p.narrative);

  // Research sources — cross-reference pattern library (loaded at startup)
  renderPatternSources(p.pattern_id);

  // Category intelligence — computed from already-loaded pattern library
  renderCategoryIntel(p.pattern_id);

  // Gemini reasoning
  const reasoningBlock = document.getElementById('reasoning-block');
  const reasoningText = document.getElementById('reasoning-text');
  if (p.match_reasoning && reasoningBlock && reasoningText) {
    reasoningText.textContent = p.match_reasoning;
    reasoningBlock.classList.remove('hidden');
  } else if (reasoningBlock) {
    reasoningBlock.classList.add('hidden');
  }

  // Metric match table — your values vs actual pattern trigger thresholds
  const pl = _lastPayload;
  const tc = p.trigger_conditions || {};
  const ltvCacVal = pl.cac > 0 ? pl.ltv / pl.cac : 0;
  const ltvCac = ltvCacVal > 0 ? ltvCacVal.toFixed(1) : 'N/A';
  const burnMultVal = (pl.mrr * pl.mrr_growth_rate) > 0
    ? pl.burn_rate / (pl.mrr * pl.mrr_growth_rate) : 99;
  const burnMult = burnMultVal < 99 ? burnMultVal.toFixed(1) : '∞';

  // Build rows with pattern trigger thresholds when available
  const matchRows = [];

  // Churn
  const churnTrigger = tc.churn_rate_min != null ? `>${(tc.churn_rate_min*100).toFixed(0)}%` : '<5%';
  const churnTriggered = tc.churn_rate_min != null ? pl.churn_rate >= tc.churn_rate_min : pl.churn_rate > 0.08;
  matchRows.push({ metric: 'Monthly Churn', yours: `${(pl.churn_rate*100).toFixed(1)}%`, threshold: churnTrigger, status: churnTriggered ? 'bad' : pl.churn_rate > 0.05 ? 'warn' : 'good' });

  // MRR Growth
  const growthTrigger = tc.mrr_growth_rate_max != null ? `<${(tc.mrr_growth_rate_max*100).toFixed(0)}%` : '>15%';
  const growthBad = tc.mrr_growth_rate_max != null ? pl.mrr_growth_rate <= tc.mrr_growth_rate_max : pl.mrr_growth_rate < 0.08;
  matchRows.push({ metric: 'MRR Growth', yours: `${(pl.mrr_growth_rate*100).toFixed(1)}%`, threshold: growthTrigger, status: growthBad ? 'bad' : pl.mrr_growth_rate < 0.15 ? 'warn' : 'good' });

  // NPS
  const npsTrigger = tc.nps_max != null ? `<${tc.nps_max}` : '>50';
  const npsTriggered = tc.nps_max != null ? pl.nps <= tc.nps_max : pl.nps < 30;
  matchRows.push({ metric: 'NPS', yours: `${pl.nps}`, threshold: npsTrigger, status: npsTriggered ? 'bad' : pl.nps < 50 ? 'warn' : 'good' });

  // LTV:CAC
  const ltvTrigger = tc.ltv_cac_ratio_max != null ? `<${tc.ltv_cac_ratio_max}x` : '>3x';
  const ltvTriggered = tc.ltv_cac_ratio_max != null ? ltvCacVal <= tc.ltv_cac_ratio_max : ltvCacVal < 1;
  matchRows.push({ metric: 'LTV:CAC', yours: `${ltvCac}x`, threshold: ltvTrigger, status: ltvTriggered ? 'bad' : ltvCacVal < 3 ? 'warn' : 'good' });

  // Burn Multiple
  const burnTrigger = tc.burn_multiple_min != null ? `>${tc.burn_multiple_min}x` : '<1.5x';
  const burnTriggered = tc.burn_multiple_min != null ? burnMultVal >= tc.burn_multiple_min : burnMultVal > 4;
  matchRows.push({ metric: 'Burn Multiple', yours: `${burnMult}x`, threshold: burnTrigger, status: burnTriggered ? 'bad' : burnMultVal > 1.5 ? 'warn' : 'good' });

  // Runway
  const runwayTrigger = tc.runway_months_max != null ? `<${tc.runway_months_max}mo` : '>18mo';
  const runwayBad = tc.runway_months_max != null ? pl.runway_months <= tc.runway_months_max : pl.runway_months < 9;
  matchRows.push({ metric: 'Runway', yours: `${pl.runway_months}mo`, threshold: runwayTrigger, status: runwayBad ? 'bad' : pl.runway_months < 18 ? 'warn' : 'good' });

  // Backend trigger breakdown — which pattern conditions are met
  const trigBreakdownEl = document.getElementById('trigger-breakdown');
  if (trigBreakdownEl && p.trigger_breakdown?.length) {
    const metCount = p.trigger_breakdown.filter(r => r.met).length;
    const total    = p.trigger_breakdown.length;
    trigBreakdownEl.innerHTML = `
      <div class="tbd-header">
        <span class="tbd-title">Why this pattern matched</span>
        <span class="tbd-summary">${metCount}/${total} trigger conditions met · ✗ = threshold crossed (drives match) · ✓ = safe</span>
      </div>
      <div class="tbd-rows">
        ${p.trigger_breakdown.map(r => `
          <div class="tbd-row ${r.met ? 'tbd-met' : 'tbd-not-met'}">
            <span class="tbd-icon">${r.met ? '✗' : '✓'}</span>
            <span class="tbd-metric">${r.metric}</span>
            <span class="tbd-threshold">threshold: ${r.threshold}</span>
            <span class="tbd-current">${r.current}</span>
          </div>`).join('')}
      </div>`;
    trigBreakdownEl.classList.remove('hidden');
  } else if (trigBreakdownEl) {
    trigBreakdownEl.classList.add('hidden');
  }

  const statusIcon = { good: '✓', warn: '▲', bad: '✗' };
  const matchTable = document.getElementById('match-table');
  if (matchTable) {
    matchTable.innerHTML = matchRows.map(r => `
      <tr>
        <td>${r.metric}</td>
        <td class="mt-yours mt-${r.status}">${r.yours}</td>
        <td class="mt-target">${r.threshold}</td>
        <td class="mt-status mt-${r.status}">${statusIcon[r.status]}</td>
      </tr>`).join('');
  }

  // Signals + 4. early warning
  const sigList = document.getElementById('signals-list');
  sigList.innerHTML = '';
  let earliestDetectable = null;

  if (p.warning_signals_detected.length === 0) {
    const notice = document.createElement('li');
    notice.style.listStyle = 'none';
    notice.innerHTML = `<span style="color:var(--muted);font-size:0.85rem;font-style:italic">
      Pattern confirmed at ${Math.round(p.confidence*100)}% — individual signals need trend data
      (multiple snapshots) to confirm. Use <strong>Monthly Tracking</strong> to surface them as they emerge.
    </span>`;
    sigList.appendChild(notice);
  }

  p.warning_signals_detected.forEach((s) => {
    const li = document.createElement('li');
    const icon = s.status === 'DETECTED' ? '' : '';
    const cls  = s.status === 'DETECTED' ? 'sig-detected' : 'sig-emerging';
    const daysAgo = s.days_detectable
      ? `<span class="sig-days">detectable ~${s.days_detectable}d ago</span>`
      : '';
    li.innerHTML = `<span>${icon}</span><span class="${cls}">${s.signal}</span>${daysAgo}`;
    sigList.appendChild(li);
    if (s.days_detectable && (earliestDetectable === null || s.days_detectable > earliestDetectable)) {
      earliestDetectable = s.days_detectable;
    }
  });

  // 4. Early warning banner + accuracy showcase
  if (earliestDetectable && earliestDetectable > 0) {
    const banner = document.getElementById('early-warning-banner');
    const txt = document.getElementById('early-warning-text');
    txt.innerHTML = `The Oracle would have detected the earliest warning signal <strong>${earliestDetectable} days before</strong> this analysis — giving you time to act before the crisis became visible.`;
    banner.classList.remove('hidden');

    // Accuracy showcase: cite a famous failure if available
    const showcase = document.getElementById('accuracy-showcase');
    const headEl   = document.getElementById('as-headline');
    const subEl    = document.getElementById('as-sub');
    if (showcase && headEl && subEl) {
      const famousName = (p.famous_failures && p.famous_failures.length > 0)
        ? p.famous_failures[0].company : null;
      const totalWindow = earliestDetectable + (p.days_to_crisis || 90);
      if (famousName) {
        headEl.innerHTML = `Oracle would have flagged <strong>${famousName}</strong> <strong>${earliestDetectable} days</strong> before this crisis signal became undeniable.`;
        subEl.textContent = `Total early-warning window: ${totalWindow} days before projected crisis. That's the difference between correcting course and running out of time.`;
      } else {
        headEl.innerHTML = `Oracle detected signals <strong>${earliestDetectable} days</strong> before they became critical.`;
        subEl.textContent = `Total early-warning window: ${totalWindow} days. Act now — before this pattern becomes irreversible.`;
      }
      showcase.classList.remove('hidden');
    }
  } else {
    hide('accuracy-showcase');
  }

  // 7. Animated stat counters
  const total   = p.failure_count + p.survival_count;
  const failPct = Math.round((1 - p.survival_rate) * 100);
  const survPct = Math.round(p.survival_rate * 100);
  setTimeout(() => animateCounter(document.getElementById('fail-pct'), failPct, '%'), 200);
  setTimeout(() => animateCounter(document.getElementById('surv-pct'), survPct, '%'), 200);
  setTimeout(() => {
    const el = document.getElementById('total-cases');
    animateCounter(el, total, '', 1000);
    // Override to use toLocaleString at end
    setTimeout(() => { el.textContent = total.toLocaleString(); }, 1200);
  }, 200);
  setText('days-crisis', `~${p.days_to_crisis} days`);

  // Crisis trajectory timeline
  renderTimeline(p);

  // Render Trajectory Forecast Chart
  if (pl) {
    renderTrajectoryChart(p, pl);
  }

  // Playbook — numbered steps with staggered entrance
  const pbList = document.getElementById('playbook-list');
  pbList.innerHTML = '';
  p.survival_playbook.forEach((step, i) => {
    const li = document.createElement('li');
    li.className = 'playbook-step';
    li.style.animationDelay = `${i * 80}ms`;
    li.innerHTML = `<span class="pb-num">${i + 1}</span><span class="pb-text">${step}</span>`;
    pbList.appendChild(li);
  });

  // Famous failures
  const famList = document.getElementById('famous-list');
  famList.innerHTML = '';
  p.famous_failures.forEach((f) => {
    const div = document.createElement('div');
    div.className = 'famous-item';
    div.innerHTML = `
      <span class="famous-company">${f.company}</span>
      <span class="famous-outcome">${f.outcome === 'Failed' ? 'Failed' : '' + f.outcome}</span>
      <span class="famous-detail">${f.detail}</span>
    `;
    famList.appendChild(div);
  });

  // Show monitoring panel on alert (reset to unenrolled state)
  const monPanel = document.getElementById('monitor-panel');
  const monActive = document.getElementById('monitor-active');
  if (monPanel) monPanel.classList.remove('hidden');
  if (monActive) monActive.classList.add('hidden');
  const monBtn = document.getElementById('monitor-btn');
  if (monBtn) { monBtn.textContent = 'Watch My Startup'; monBtn.disabled = false; }

  if (document.getElementById('agent-terminal')?.classList.contains('hidden') === false) {
    collapseTerminal();
  }
  show('alert-section');
  // Small delay so layout settles after terminal collapse before scrolling
  setTimeout(() => {
    document.getElementById('alert-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setupStickyResultTabs();
  }, 80);
}

// ── Pattern Research Sources ─────────────────────────────────────
function renderPatternSources(patternId) {
  const block = document.getElementById('sources-block');
  const tagsEl = document.getElementById('sources-tags');
  if (!block || !tagsEl) return;

  const pattern = _allPatterns.find(p => p.pattern_id === patternId);
  const sources = pattern?.sources;
  if (!sources?.length) { block.classList.add('hidden'); return; }

  tagsEl.innerHTML = sources.map(s => `<span class="source-tag">${s}</span>`).join('');
  block.classList.remove('hidden');
}

// ── Category Intelligence ─────────────────────────────────────────
function renderCategoryIntel(patternId) {
  const el = document.getElementById('cat-intel');
  if (!el || !_allPatterns.length) { if (el) el.classList.add('hidden'); return; }

  // Find the matched pattern in the library to get its category
  const matched = _allPatterns.find(p => p.pattern_id === patternId);
  if (!matched) { el.classList.add('hidden'); return; }

  const category = matched.category;
  const inCategory = _allPatterns.filter(p => p.category === category);
  if (!inCategory.length) { el.classList.add('hidden'); return; }

  const totalFailed   = inCategory.reduce((s, p) => s + (p.failure_count || 0), 0);
  const totalSurvived = inCategory.reduce((s, p) => s + (p.survival_count || 0), 0);
  const totalCases    = totalFailed + totalSurvived;
  const survPct       = totalCases > 0 ? Math.round(totalSurvived / totalCases * 100) : 0;

  // Most dangerous pattern in category
  const worst = inCategory.reduce((a, b) => {
    const rateA = (a.failure_count + a.survival_count) > 0
      ? a.survival_count / (a.failure_count + a.survival_count) : 1;
    const rateB = (b.failure_count + b.survival_count) > 0
      ? b.survival_count / (b.failure_count + b.survival_count) : 1;
    return rateA < rateB ? a : b;
  });
  const worstSurv = worst ? Math.round(
    worst.survival_count / Math.max(worst.failure_count + worst.survival_count, 1) * 100
  ) : 0;

  const catLabel = (CAT_LABELS[category] || category.replace(/_/g, ' '));
  const color = survPct < 15 ? 'var(--danger)' : survPct < 30 ? 'var(--warning)' : 'var(--safe)';

  document.getElementById('ci-surv-rate').innerHTML =
    `<span style="color:${color};font-weight:700;font-size:1.1rem">${survPct}%</span> survival rate across <strong>${totalCases.toLocaleString()}</strong> documented cases in <strong>${catLabel}</strong>`;
  document.getElementById('ci-pattern-count').innerHTML =
    `<strong>${inCategory.length}</strong> failure patterns documented in this category`;
  document.getElementById('ci-worst').innerHTML = worst
    ? `Most fatal: <strong>${worst.name}</strong> — only <span style="color:var(--danger)">${worstSurv}%</span> survived`
    : '';

  el.classList.remove('hidden');
}

// ── Crisis Timeline ──────────────────────────────────────────────
function renderTimeline(p) {
  const el = document.getElementById('crisis-timeline');
  if (!el) return;

  const daysTo = p.days_to_crisis || 90;
  const detectable = p.warning_signals_detected
    .filter(s => s.days_detectable)
    .map(s => s.days_detectable);
  const maxDetectable = detectable.length > 0 ? Math.max(...detectable) : null;

  if (!maxDetectable) {
    el.classList.add('hidden');
    return;
  }

  el.classList.remove('hidden');

  const total = maxDetectable + daysTo;
  const todayPct = (maxDetectable / total * 100);

  const pastFill   = document.getElementById('ct-past-fill');
  const todayMarker = document.getElementById('ct-today-marker');
  const subtitle   = document.getElementById('ct-subtitle');
  const labelLeft  = document.getElementById('ct-label-left');
  const labelRight = document.getElementById('ct-label-right');

  // Position today marker and past fill
  pastFill.style.width    = `${todayPct}%`;
  todayMarker.style.left  = `${todayPct}%`;

  // Colour the future segment more urgently based on days remaining
  const urgency = daysTo < 60 ? 'ct-urgent' : daysTo < 120 ? 'ct-warning' : 'ct-moderate';
  el.dataset.urgency = urgency;

  subtitle.textContent = `${daysTo} days until projected crisis — act now`;
  labelLeft.textContent  = `~${maxDetectable} days ago`;
  labelRight.textContent = `~${daysTo} days`;
}

// ── 1. Download Report ───────────────────────────────────────────
function downloadReport() {
  if (!_lastResult || !_lastResult.alert) return;
  const p = _lastResult.pattern;
  const pl = _lastPayload;
  const total = p.failure_count + p.survival_count;
  const failPct = Math.round((1 - p.survival_rate) * 100);
  const survPct = Math.round(p.survival_rate * 100);

  const signals = p.warning_signals_detected
    .map(s => `| ${s.signal} | ${s.status} | ${s.days_detectable ? '~' + s.days_detectable + 'd ago' : 'Just emerged'} |`)
    .join('\n');
  const playbook = p.survival_playbook.map((s, i) => `${i+1}. ${s}`).join('\n');
  const failures = p.famous_failures
    .map(f => `| ${f.company} | ${f.outcome} | ${f.detail} |`)
    .join('\n');

  const oracleScore = _lastResult.oracle_score != null ? _lastResult.oracle_score : '—';
  const scoreBand   = _lastResult.score_band  || '';
  const challenger  = _lastResult.challenger;
  const escapePlan  = _lastResult.escape_plan;

  const escapeSection = escapePlan?.interventions?.length
    ? `## Escape Plan — Minimum Metric Changes to Exit Danger\n` +
      `Pattern match can drop from **${Math.round(p.confidence * 100)}% → ${Math.round((p.confidence - escapePlan.combined_drop) * 100)}%** if all actions below are taken.\n\n` +
      `| # | Metric | Current | Target | Difficulty | Risk Reduction |\n` +
      `|---|--------|---------|--------|------------|----------------|\n` +
      escapePlan.interventions.slice(0, 5).map((item, i) =>
        `| ${i+1} | ${item.metric} | ${item.current_value} | ${item.target_value} | ${item.difficulty} | −${item.estimated_confidence_drop}pp |`
      ).join('\n') + '\n\n---\n'
    : '';

  const challengerSection = challenger
    ? `## Challenger Agent Verdict\n**${challenger.verdict || 'CONFIRMED'}** — Confidence gap: ${challenger.confidence_gap != null ? challenger.confidence_gap + 'pp' : '—'}\n\n${challenger.reasoning || ''}\n\n---\n`
    : '';

  const md = `# The Failure Oracle — Risk Report

**Pattern:** ${p.pattern_name} (${p.pattern_id})
**Match Score:** ${Math.round(p.confidence * 100)}%
**Oracle Score:** ${oracleScore}/100 ${scoreBand ? `(${scoreBand.toUpperCase()})` : ''}
**Startup:** ${pl.startup_name} | Month ${pl.current_month}
**Industry:** ${pl.industry || 'N/A'}
**Generated:** ${new Date().toLocaleString()}

---

## What This Pattern Means

${p.narrative}

---

## Your Metrics

| Metric | Value |
|--------|-------|
| MRR | $${pl.mrr.toLocaleString()} |
| Monthly Growth | ${(pl.mrr_growth_rate * 100).toFixed(1)}% |
| Churn Rate | ${(pl.churn_rate * 100).toFixed(1)}% |
| Burn Rate | $${pl.burn_rate.toLocaleString()}/mo |
| Runway | ${pl.runway_months} months |
| NPS | ${pl.nps} |
| Headcount | ${pl.headcount || 'N/A'} |
| LTV:CAC | ${pl.cac > 0 ? (pl.ltv / pl.cac).toFixed(1) + 'x' : 'N/A'} |

---

## Warning Signals Detected

| Signal | Status | First Detectable |
|--------|--------|-----------------|
${signals || '| No signals detected | — | — |'}

---

## Historical Outcomes (${total.toLocaleString()} cases)

- **${failPct}% failed** within ${p.days_to_crisis} days
- **${survPct}% survived** (${p.survival_count} companies)

---

${challengerSection}${escapeSection}## Survival Playbook

${playbook || '_No playbook available for this pattern._'}

---

## Companies That Matched This Pattern

| Company | Outcome | Detail |
|---------|---------|--------|
${failures || '| — | — | — |'}

---

_Generated by The Failure Oracle · ${new Date().toLocaleDateString()}_
`;

  const blob = new Blob([md], { type: 'text/markdown' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  const safeName = pl.startup_name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  a.download = `oracle-report-${safeName}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── 5. Share Analysis ────────────────────────────────────────────
// ── Public Share Link ────────────────────────────────────────────
async function createPublicShare() {
  if (!_lastResult || !_lastPayload) return;
  const btn = document.getElementById('public-share-btn');
  const confirmEl = document.getElementById('public-share-confirm');
  const origText = btn?.innerHTML;
  if (btn) { btn.textContent = 'Generating link…'; btn.disabled = true; }

  try {
    const res = await fetch(`${API}/api/share/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        startup_name: _lastPayload.startup_name,
        payload: _lastPayload,
        result: _lastResult,
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const url = `${window.location.origin}${data.url_path}`;
    await navigator.clipboard.writeText(url);
    if (confirmEl) {
      confirmEl.textContent = `Public link copied — ${url.length > 50 ? url.slice(0, 50) + '…' : url}`;
      confirmEl.classList.remove('hidden');
      setTimeout(() => confirmEl.classList.add('hidden'), 4000);
    }
  } catch (err) {
    alert(`Could not create public link: ${err.message}`);
  } finally {
    if (btn) { btn.innerHTML = origText; btn.disabled = false; }
  }
}

// On page load, if URL has ?share=XXX, load that shared report
async function loadSharedReport() {
  const params = new URLSearchParams(window.location.search);
  const shareId = params.get('share');
  if (!shareId) return;

  try {
    const res = await fetch(`${API}/api/share/${shareId}`);
    if (!res.ok) return;
    const doc = await res.json();
    if (!doc?.result) return;

    // Pre-fill form fields from saved payload
    if (doc.payload) {
      Object.keys(doc.payload).forEach(k => {
        const el = document.getElementById(k);
        if (el && doc.payload[k] !== undefined) el.value = doc.payload[k];
      });
      updateLiveMetrics();
    }
    _lastResult  = doc.result;
    _lastPayload = doc.payload;

    // Render the saved result directly (skip running new analysis)
    renderResult(doc.result);
    saveSnapshot(doc.result, doc.payload);

    // Banner: viewing a shared snapshot
    const banner = document.createElement('div');
    banner.className = 'shared-banner';
    banner.innerHTML = `<span>Viewing a shared Oracle analysis snapshot · <a href="/">Run your own →</a></span>`;
    document.body.prepend(banner);
  } catch (err) {
    console.warn('Failed to load shared report', err);
  }
}

function shareAnalysis() {
  if (!_lastPayload) return;
  const params = new URLSearchParams();
  Object.entries(_lastPayload).forEach(([k, v]) => params.set(k, v));
  const url = `${window.location.origin}${window.location.pathname}?${params.toString()}`;
  navigator.clipboard.writeText(url).then(() => {
    const c = document.getElementById('share-confirm');
    c.classList.remove('hidden');
    setTimeout(() => c.classList.add('hidden'), 2500);
  });
}

// ── Board Deck Export ────────────────────────────────────────────
async function exportSlides() {
  if (!_lastResult?.pattern) return;
  const p   = _lastResult.pattern;
  const btn = document.getElementById('slides-btn');
  if (btn) { btn.textContent = 'Generating deck…'; btn.disabled = true; }

  try {
    const body = {
      startup_name:      _lastResult.startup_name || '',
      pattern_name:      p.pattern_name,
      confidence:        p.confidence,
      days_to_crisis:    p.days_to_crisis || 90,
      survival_rate:     p.survival_rate || 0,
      narrative:         p.narrative || '',
      warning_signals:   (p.warning_signals_detected || []).map(s => s.signal),
      survival_playbook: p.survival_playbook || [],
      famous_failures:   p.famous_failures || [],
      match_reasoning:   p.match_reasoning || '',
    };
    const res = await fetch(`${API}/api/export/slides`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    const safe = (_lastResult.startup_name || 'startup').replace(/\s+/g, '-').toLowerCase();
    a.href     = url;
    a.download = `oracle-board-deck-${safe}.html`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert(`Export failed: ${err.message}`);
  } finally {
    if (btn) {
      btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:0.3rem;vertical-align:-2px"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg> Export Board Deck';
      btn.disabled = false;
    }
  }
}

// ── Decision Audit ───────────────────────────────────────────────
async function runAudit() {
  const decision = document.getElementById('decision-text').value.trim();
  if (!decision) {
    showAuditError('Please describe the decision first.');
    return;
  }

  const btn = document.getElementById('audit-btn');
  btn.disabled = true;
  // Animate the button text to show Gemini is reasoning
  const reasoningMsgs = [
    'Gemini 3 is reasoning…',
    'Cross-referencing 100 patterns…',
    'Evaluating risk vectors…',
    'Forming recommendation…',
  ];
  let msgIdx = 0;
  btn.textContent = reasoningMsgs[0];
  const msgInterval = setInterval(() => {
    msgIdx = (msgIdx + 1) % reasoningMsgs.length;
    if (!btn.disabled) { clearInterval(msgInterval); return; }
    btn.textContent = reasoningMsgs[msgIdx];
  }, 1800);

  const metrics = {
    startup_name:    val('startup_name') || 'Your Startup',
    current_month:   num('current_month') || 12,
    mrr:             num('mrr') || 0,
    mrr_growth_rate: num('mrr_growth_rate') || 0,
    churn_rate:      num('churn_rate') || 0,
    burn_rate:       num('burn_rate') || 0,
    runway_months:   num('runway_months') || 12,
    headcount:       num('headcount') || 5,
    nps:             num('nps') || 40,
    cac:             num('cac') || 1000,
    ltv:             num('ltv') || 5000,
    industry:        val('industry') || 'B2B SaaS',
  };

  const context = document.getElementById('audit-context')?.value?.trim() || '';

  try {
    const res  = await fetch(`${API}/api/audit/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        decision,
        context: context || undefined,
        startup_name: metrics.startup_name,
        current_month: metrics.current_month,
        metrics
      }),
    });
    
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      const details = Array.isArray(errData.detail)
        ? errData.detail.map(d => `${d.loc.join('.')}: ${d.msg}`).join(', ')
        : (errData.detail || `HTTP Error ${res.status}`);
      throw new Error(details);
    }
    
    const data = await res.json();
    renderAudit(data);
  } catch (err) {
    showAuditError(`Audit Failed: ${err.message}`);
    console.error(err);
  } finally {
    clearInterval(msgInterval);
    btn.textContent = 'Audit This Decision';
    btn.disabled = false;
  }
}

function showAuditError(message) {
  const el = document.getElementById('audit-result');
  if (!el) return;
  el.className = 'audit-error-card';
  el.innerHTML = `
    <div class="audit-error-title">⚠ Analysis Interrupted</div>
    <p class="audit-error-message">${message}</p>
    <div style="font-size:0.75rem;color:var(--muted);margin-top:0.5rem">Ensure all numeric input fields (like MRR, Burn, LTV:CAC, Runway) are valid.</div>
  `;
  el.classList.remove('hidden');
  el.scrollIntoView({ behavior: 'smooth' });
}

function renderAudit(data) {
  const el  = document.getElementById('audit-result');
  const cls = `risk-${data.risk_level.toLowerCase()}`;

  const linked = data.related_pattern
    ? _allPatterns.find(p => p.pattern_id === data.related_pattern)
    : null;

  // Render *text* as bold (Gemini sometimes uses markdown asterisks)
  const renderMarkdown = (text) => (text || '')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+?)\*/g, '<strong>$1</strong>');

  // Make F-XXX pattern IDs clickable chips in any text string
  const linkPatternRefs = (text) => renderMarkdown(text || '').replace(/\b(F-\d{3})\b/g, (id) => {
    const p = _allPatterns.find(x => x.pattern_id === id);
    return `<span class="pattern-chip-inline" onclick="jumpToPattern('${id}')" title="${p ? p.name : id}">${id}</span>`;
  });

  // Convert a rationale paragraph into a bullet list (split on sentence boundaries)
  const rationaleToList = (text) => {
    if (!text) return '';
    const sentences = text
      .split(/(?<=[.!?])\s+(?=[A-Z"'(])/)
      .map(s => s.trim())
      .filter(s => s.length > 15);
    if (sentences.length <= 1) return `<p class="audit-rationale">${linkPatternRefs(text)}</p>`;
    return `<ul class="audit-bullets">${sentences.map(s =>
      `<li>${linkPatternRefs(s)}</li>`
    ).join('')}</ul>`;
  };

  let patternCard = '';
  if (linked) {
    const totalCases = (linked.survival_count || 0) + (linked.failure_count || 0);
    const computedSurvRate = linked.survival_rate != null ? linked.survival_rate
      : (totalCases > 0 ? (linked.survival_count / totalCases) : 0);
    const survRatePct = Math.round(computedSurvRate * 100);
    const survClass = survRatePct < 25 ? 'apc-surv-low' : 'apc-surv-ok';
    const catLabel = CAT_LABELS[linked.category] || (linked.category || '').replace(/_/g, ' ');

    patternCard = `
      <div class="audit-pattern-card" onclick="jumpToPattern('${linked.pattern_id}')" style="cursor:pointer" title="Click to view details in library">
        <div class="apc-label">Closest matching failure pattern ↗</div>
        <div class="apc-name">${linked.name}</div>
        <div class="apc-surv-hero ${survClass}">${survRatePct}%<span class="apc-surv-hero-label">survived</span></div>
        <div class="apc-meta">
          <span class="apc-id">${linked.pattern_id}</span>
          <span class="apc-cat">${catLabel}</span>
        </div>
        ${linked.famous_failures && linked.famous_failures.length > 0
          ? `<div class="apc-example">"${linked.famous_failures[0].company} — ${linked.famous_failures[0].detail}"</div>`
          : ''}
      </div>
    `;
  }

  // Risk banner colors
  const bannerColors = {
    CRITICAL: 'var(--danger)',
    HIGH: '#f97316',
    MEDIUM: 'var(--warning)',
    LOW: 'var(--safe)',
  };
  const bannerColor = bannerColors[data.risk_level] || 'var(--muted)';

  el.innerHTML = `
    <div class="audit-risk-banner" style="border-color:${bannerColor};background:${bannerColor}18">
      <span class="audit-risk-level" style="color:${bannerColor}">${data.risk_level} RISK</span>
      <span class="audit-risk-sub">Evaluated against ${(_allPatterns && _allPatterns.length) || '100'} documented failure patterns</span>
    </div>

    <div class="audit-body">
      <div class="audit-left-col">
        ${patternCard}
        ${data.key_differentiator ? `
        <div class="audit-section audit-section-diff">
          <div class="audit-section-label">What survivors did differently</div>
          <p class="audit-differentiator">${linkPatternRefs(data.key_differentiator)}</p>
        </div>` : ''}
      </div>

      <div class="audit-right-col">
        <div class="audit-recommendation-box" style="border-color:${bannerColor};background:${bannerColor}10">
          <div class="audit-rec-label">Recommendation</div>
          <div class="audit-rec-text">${linkPatternRefs(data.recommendation)}</div>
        </div>

        ${data.rationale ? `
        <div class="audit-section">
          <div class="audit-section-label">Why this decision is risky</div>
          ${rationaleToList(data.rationale)}
        </div>` : ''}

        <div class="audit-premortem-cta">
          <span class="audit-premortem-cta-text">Want to see what happens if you proceed anyway?</span>
          <button class="audit-premortem-cta-btn" onclick="
            const pmEl = document.getElementById('pm-decision-text');
            if (pmEl) pmEl.value = document.getElementById('decision-text').value || '';
            setTimeout(() => { if(pmEl) pmEl.scrollIntoView({behavior:'smooth', block:'center'}); }, 100);
          ">Run Pre-Mortem →</button>
        </div>
      </div>
    </div>
  `;
  el.classList.remove('hidden');
  el.scrollIntoView({ behavior: 'smooth' });
}

function riskIcon(level) {
  return { LOW: '', MEDIUM: '', HIGH: '', CRITICAL: '' }[level] || '';
}

// ── 3. Pattern Library ───────────────────────────────────────────
let _allPatterns = [];

async function loadPatternLibrary() {
  try {
    const res = await fetch(`${API}/api/patterns/`);
    const data = await res.json();
    _allPatterns = data.patterns || [];
    const countEl = document.getElementById('patterns-count'); if(countEl) countEl.textContent = `${_allPatterns.length} patterns`;
    renderPatternGrid(_allPatterns);
  } catch (e) {
    document.getElementById('patterns-grid').innerHTML = '<p style="color:var(--muted)">Could not load pattern library.</p>';
  }
}

let _patternViewMode = 'list'; // 'list' | 'heatmap'

function togglePatternView() {
  _patternViewMode = _patternViewMode === 'list' ? 'heatmap' : 'list';
  const btn = document.getElementById('pattern-view-toggle');
  if (btn) btn.textContent = _patternViewMode === 'list' ? 'Heatmap View' : 'List View';
  const filtered = _currentPatternCategory
    ? _allPatterns.filter(p => p.category === _currentPatternCategory)
    : _allPatterns;
  renderPatternGrid(filtered);
}

let _currentPatternCategory = '';

function renderPatternHeatmap(patterns) {
  const grid = document.getElementById('patterns-grid');
  const cats = [...new Set(patterns.map(p => p.category))].sort();
  const catColors = {
    premature_scaling: '#f97316', product_market_fit: '#ef4444', unit_economics: '#dc2626',
    fundraising: '#f59e0b', team: '#8b5cf6', go_to_market: '#3b82f6',
    competition: '#06b6d4', platform_risk: '#14b8a6', regulatory: '#84cc16',
    technical_debt: '#6366f1', pivot: '#ec4899', product: '#a855f7',
  };

  let html = '<div class="heatmap-legend"><span>Lower survival rate</span><div class="heatmap-legend-bar"></div><span>Higher survival rate</span></div>';
  html += '<div class="heatmap-grid">';

  patterns.forEach(p => {
    const total = (p.failure_count || 0) + (p.survival_count || 0);
    const surv = total > 0 ? Math.round((p.survival_count / total) * 100) : 0;
    const r = Math.round(239 - (surv / 100) * (239 - 16));
    const g = Math.round(68 + (surv / 100) * (185 - 68));
    const b = Math.round(68 + (surv / 100) * (129 - 68));
    const bg = `rgb(${r},${g},${b})`;
    html += `
      <div class="heatmap-cell" style="background:${bg}" title="${p.pattern_id}: ${p.name} — ${surv}% survived"
        onclick="jumpToPattern('${p.pattern_id}')">
        <span class="heatmap-cell-id">${p.pattern_id}</span>
        <span class="heatmap-cell-surv">${surv}%</span>
      </div>`;
  });
  html += '</div>';
  grid.innerHTML = html;
}

function filterPatterns(category) {
  _currentPatternCategory = category || '';
  document.querySelectorAll('.pf-btn').forEach(b => b.classList.remove('active'));
  
  if (typeof event !== 'undefined' && event && event.target && event.target.classList.contains('pf-btn')) {
    event.target.classList.add('active');
  } else {
    // Select the category button programmatically
    const buttons = document.querySelectorAll('.pf-btn');
    buttons.forEach(btn => {
      const onclickAttr = btn.getAttribute('onclick') || '';
      if ((!category && onclickAttr.includes("filterPatterns('')")) || 
          (category && onclickAttr.includes(`filterPatterns('${category}')`))) {
        btn.classList.add('active');
      }
    });
  }
  
  const filtered = category ? _allPatterns.filter(p => p.category === category) : _allPatterns;
  renderPatternGrid(filtered);
}

function renderPatternGrid(patterns) {
  const grid = document.getElementById('patterns-grid');
  if (!patterns.length) {
    grid.innerHTML = '<p style="color:var(--muted);padding:1rem">No patterns in this category.</p>';
    return;
  }
  if (_patternViewMode === 'heatmap') { renderPatternHeatmap(patterns); return; }
  grid.innerHTML = patterns.map(p => {
    const total = (p.failure_count || 0) + (p.survival_count || 0);
    const survRate = total > 0 ? Math.round((p.survival_count / total) * 100) : 0;
    const riskColor = survRate < 15 ? 'var(--danger)' : survRate < 30 ? 'var(--warning)' : 'var(--safe)';
    const catLabel = CAT_LABELS[p.category] || (p.category || '').replace(/_/g, ' ');

    // Warning signals list
    const signals = (p.warning_signals || []).slice(0, 4).map(s =>
      `<li>${s.signal} <span class="sig-days-small">${s.days_before_failure}d before</span></li>`
    ).join('');

    // Playbook steps
    const playbook = (p.survival_playbook || []).slice(0, 3).map((s, i) =>
      `<li>${i+1}. ${s}</li>`
    ).join('');

    // Famous failures
    const failures = (p.famous_failures || []).map(f =>
      `<span class="pc-failure-tag">${f.company}</span>`
    ).join('');

    // Sources
    const sources = (p.sources || []).map(s =>
      `<span class="pc-source-tag">${s}</span>`
    ).join('');

    return `
      <div class="pattern-card" data-pattern-id="${p.pattern_id}" onclick="togglePatternDetail(this)">
        <div class="pc-top">
          <div>
            <span class="pc-id">${p.pattern_id}</span>
            <span class="pc-cat">${catLabel}</span>
          </div>
          <span class="pc-surv" style="color:${riskColor}">${survRate}% survived</span>
        </div>
        <div class="pc-name">${p.name}</div>
        <div class="pc-surv-bar-wrap" title="${survRate}% survival rate — ${total} documented cases">
          <div class="pc-surv-bar" style="width:${survRate}%;background:${riskColor}"></div>
        </div>
        <div class="pc-stats">
          <span>${p.failure_count || 0} failed</span>
          <span>${p.survival_count || 0} survived</span>
          <span>${total} cases</span>
        </div>
        <div class="pc-detail hidden">
          <p class="pc-narrative">${p.narrative || ''}</p>
          ${signals ? `<div class="pc-section"><div class="pc-section-title">Early Warning Signals</div><ul class="pc-signal-list">${signals}</ul></div>` : ''}
          ${playbook ? `<div class="pc-section"><div class="pc-section-title">Survival Playbook</div><ul class="pc-playbook-list">${playbook}</ul></div>` : ''}
          ${failures ? `<div class="pc-section"><div class="pc-section-title">Known Cases</div><div class="pc-failures">${failures}</div></div>` : ''}
          ${sources ? `<div class="pc-section"><div class="pc-section-title">Sources</div><div class="pc-sources">${sources}</div></div>` : ''}
        </div>
        <div class="pc-expand-hint">Click to expand ▾</div>
      </div>`;
  }).join('');
}

function jumpToPattern(patternId) {
  // 1. Switch to Pattern Library tab
  if (typeof switchTab === 'function') switchTab('tab-library');

  // 2. Make sure the Pattern Library section is open
  const container = document.getElementById('patterns-container');
  const btn = document.getElementById('toggle-patterns-btn');
  if (container && container.classList.contains('hidden')) {
    container.classList.remove('hidden');
    const countEl = document.getElementById('patterns-count');
    const count = countEl ? countEl.textContent : '';
    if (btn) btn.innerHTML = `Hide Pattern Library (<span id="patterns-count">${count}</span>)`;
  }

  // Switch to list view so .pattern-card elements exist
  if (_patternViewMode === 'heatmap') {
    _patternViewMode = 'list';
    const vBtn = document.getElementById('pattern-view-toggle');
    if (vBtn) vBtn.textContent = 'Heatmap View';
  }

  // 2. Clear any active category filter so the card is visible
  filterPatterns('');

  // 3. Find the card
  const card = document.querySelector(`.pattern-card[data-pattern-id="${patternId}"]`);
  if (!card) {
    // Library not loaded yet — scroll to section and let user find it
    document.getElementById('patterns-section')?.scrollIntoView({ behavior: 'smooth' });
    return;
  }

  // 4. Expand it if collapsed
  const detail = card.querySelector('.pc-detail');
  const hint   = card.querySelector('.pc-expand-hint');
  if (detail && detail.classList.contains('hidden')) {
    detail.classList.remove('hidden');
    card.classList.add('expanded');
    if (hint) hint.textContent = 'Click to collapse ▴';
  }

  // 5. Scroll to it
  card.scrollIntoView({ behavior: 'smooth', block: 'center' });

  // 6. Flash highlight
  card.classList.add('pattern-card-highlight');
  setTimeout(() => card.classList.remove('pattern-card-highlight'), 2000);
}

function togglePatternDetail(card) {
  const detail = card.querySelector('.pc-detail');
  const hint = card.querySelector('.pc-expand-hint');
  detail.classList.toggle('hidden');
  card.classList.toggle('expanded');
  if (hint) hint.textContent = card.classList.contains('expanded') ? 'Click to collapse ▴' : 'Click to expand ▾';
}

// ── Category survival chart for How It Works ────────────────────
function renderCatChart() {
  const container = document.getElementById('hiw-cat-bars');
  if (!container || !_allPatterns.length) return;

  // Aggregate by category
  const cats = {};
  _allPatterns.forEach(p => {
    const cat = CAT_LABELS[p.category] || p.category;
    if (!cats[cat]) cats[cat] = { failed: 0, survived: 0 };
    cats[cat].failed   += p.failure_count  || 0;
    cats[cat].survived += p.survival_count || 0;
  });

  const sorted = Object.entries(cats)
    .map(([cat, d]) => {
      const total = d.failed + d.survived;
      return { cat, total, survRate: total > 0 ? Math.round(d.survived / total * 100) : 0 };
    })
    .sort((a, b) => a.survRate - b.survRate);

  container.innerHTML = sorted.map(({ cat, total, survRate }) => {
    const color = survRate < 15 ? 'var(--danger)' : survRate < 25 ? 'var(--warning)' : 'var(--safe)';
    return `
      <div class="cat-bar-row">
        <div class="cat-bar-label">${cat}</div>
        <div class="cat-bar-track">
          <div class="cat-bar-fill" style="width:${survRate}%;background:${color}"></div>
        </div>
        <div class="cat-bar-pct" style="color:${color}">${survRate}%</div>
        <div class="cat-bar-cases">${total} cases</div>
      </div>`;
  }).join('');
}

// ── How It Works Modal ──────────────────────────────────────────
function openHowItWorks() {
  document.getElementById('hiw-overlay').classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  switchHiwTab('hiw-panel-process'); // Always reset to first panel on click
  setTimeout(renderCatChart, 100);
}
function closeHowItWorks() {
  document.getElementById('hiw-overlay').classList.add('hidden');
  document.body.style.overflow = '';
}
function closeIfBackdrop(e) {
  if (e.target === document.getElementById('hiw-overlay')) closeHowItWorks();
}
function switchHiwTab(panelId) {
  // Hide all tab panels inside the modal
  document.querySelectorAll('.hiw-tab-panel').forEach(p => p.classList.add('hidden'));
  // Show the selected panel
  const target = document.getElementById(panelId);
  if (target) target.classList.remove('hidden');
  
  // Toggle the active class on corresponding navigation buttons
  document.querySelectorAll('.hiw-tab-btn').forEach(btn => btn.classList.remove('active'));
  const activeBtn = document.querySelector(`.hiw-tab-btn[data-panel="${panelId}"]`);
  if (activeBtn) activeBtn.classList.add('active');
  
  // Re-render chart if switching to database panel to guarantee proper SVG sizes
  if (panelId === 'hiw-panel-database') {
    setTimeout(renderCatChart, 50);
  }
}
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeHowItWorks(); });

// ── Helpers ─────────────────────────────────────────────────────
function val(id) { return document.getElementById(id)?.value || ''; }
function num(id) { return parseFloat(document.getElementById(id)?.value) || 0; }
function setText(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }
function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }

// Main Tab Switcher
function switchTab(tabId) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  const targetTab = document.getElementById(tabId);
  if (targetTab) targetTab.classList.remove('hidden');

  document.querySelectorAll('.nav-item, .mobile-nav-item').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll(`.nav-item[data-tab="${tabId}"], .mobile-nav-item[data-tab="${tabId}"]`).forEach(btn => btn.classList.add('active'));

  // Auto-prefill cohort form from last analysis when portfolio tab is opened
  if (tabId === 'tab-portfolio' && _lastResult && _lastPayload) {
    const industryEl = document.getElementById('cohort-industry');
    const scoreEl    = document.getElementById('cohort-score');
    const monthEl    = document.getElementById('cohort-month');
    if (industryEl && _lastPayload.industry) industryEl.value = _lastPayload.industry;
    if (scoreEl && _lastResult.oracle_score != null) scoreEl.value = _lastResult.oracle_score;
    if (monthEl && _lastPayload.current_month) monthEl.value = _lastPayload.current_month;
  }

  const contentArea = document.querySelector('.content-area');
  if (contentArea) contentArea.scrollTop = 0;

  // Reflect the active tab in the URL so a refresh keeps you here
  if (window.history && history.replaceState) {
    history.replaceState(null, '', '#' + tabId);
  }
}

// ── Landing hero (Option A entry screen) ─────────────────────────
// Dismiss the landing overlay and reveal the tabbed app. Optionally
// jump straight to a given tab (used by the landing nav chips).
function enterApp(tabId) {
  const hero = document.getElementById('landing-hero');
  if (hero && !hero.classList.contains('hidden')) {
    hero.classList.add('leaving');
    setTimeout(() => hero.classList.add('hidden'), 450);
  }
  document.body.classList.remove('landing-active');
  document.body.style.overflow = '';
  if (tabId) switchTab(tabId);
}

// Bring the landing hero back (clicking the brand logo = "home").
function showLanding() {
  const hero = document.getElementById('landing-hero');
  if (!hero) return;
  hero.classList.remove('hidden');
  void hero.offsetWidth;            // force reflow so the fade plays
  hero.classList.remove('leaving');
  document.body.classList.add('landing-active');
  hero.scrollTop = 0;
  const ca = document.querySelector('.content-area');
  if (ca) ca.scrollTop = 0;
  // Clear the route so this URL shows the landing on refresh
  if (window.history && history.replaceState) {
    history.replaceState(null, '', location.pathname + location.search);
  }
}

// ── Landing: scroll-reveal, count-up, signature gauge ────────────
// Progressive enhancement — JS adds the .reveal class, so if any of this
// fails the content stays fully visible.
function initReveals() {
  if (!('IntersectionObserver' in window)) return;
  const targets = document.querySelectorAll(
    '.lh-detail .lh-h2, .lh-detail .lh-lead, .lh-step, .lh-feature, .lh-company, .lh-tech span, .lh-demo, .lh-detail .lh-btn-primary, .lh-footer'
  );
  if (!targets.length) return;
  targets.forEach(el => el.classList.add('reveal'));
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      const el = e.target;
      const idx = el.parentElement ? Array.prototype.indexOf.call(el.parentElement.children, el) : 0;
      el.style.transitionDelay = (Math.max(0, idx % 6) * 70) + 'ms';
      el.classList.add('in-view');
      obs.unobserve(el);
    });
  }, { threshold: 0.15 });
  targets.forEach(el => obs.observe(el));
}

function initCountUp() {
  document.querySelectorAll('.lh-countup').forEach(el => {
    const target = parseFloat(el.dataset.count);
    if (isNaN(target)) return;
    const suffix = el.dataset.suffix || '';
    const startT = performance.now(), dur = 1400;
    (function step(now) {
      const t = Math.min(1, (now - startT) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = Math.round(target * eased) + suffix;
      if (t < 1) requestAnimationFrame(step);
      else el.textContent = target + suffix;
    })(performance.now());
  });
}

// The signature moment: animate WeWork's Oracle Score collapsing to 12/100
function initHeroGauge() {
  const sec = document.querySelector('.lh-demo-section');
  const numEl = document.getElementById('lh-gauge-num');
  const prog = document.getElementById('lh-gauge-prog');
  const verdict = document.getElementById('lh-gauge-verdict');
  if (!sec || !numEl || !prog || !verdict) return;
  const CIRC = 376.99;          // 2π · r(60)
  const target = 12;
  const colorFor = (s) => s >= 75 ? 'var(--safe)' : s >= 50 ? 'var(--warning)' : s >= 25 ? '#fb923c' : 'var(--danger)';
  let played = false;

  function play() {
    if (played) return;
    played = true;
    requestAnimationFrame(() => {
      prog.style.strokeDashoffset = String(CIRC * (1 - target / 100));
      prog.style.stroke = colorFor(target);
      const startT = performance.now(), dur = 2200, from = 100;
      (function step(now) {
        const t = Math.min(1, (now - startT) / dur);
        const eased = 1 - Math.pow(1 - t, 3);
        const val = Math.round(from + (target - from) * eased);
        numEl.textContent = String(val);
        numEl.style.color = colorFor(val);
        if (t < 1) requestAnimationFrame(step);
        else { verdict.textContent = 'Burn Multiple Death Spiral'; verdict.style.color = 'var(--danger)'; }
      })(performance.now());
    });
  }

  if ('IntersectionObserver' in window) {
    const obs = new IntersectionObserver((entries) => {
      entries.forEach(e => { if (e.isIntersecting) { play(); obs.disconnect(); } });
    }, { threshold: 0.4 });
    obs.observe(sec);
  } else {
    play();
  }
}

// Result Sub-tab Switcher
function switchResultTab(tabId) {
  document.querySelectorAll('.result-tab-content').forEach(el => el.classList.add('hidden'));
  const targetTab = document.getElementById(tabId);
  if (targetTab) targetTab.classList.remove('hidden');

  // Sync active state in both the inline nav and the sticky nav
  ['.result-tab-btn', '.srt-btn'].forEach(selector => {
    document.querySelectorAll(selector).forEach(btn => {
      const matches = btn.getAttribute('onclick')?.includes(tabId)
                   || btn.dataset.tab === tabId;
      btn.classList.toggle('active', !!matches);
    });
  });

  // Mirror has-data dot to sticky escape tab btn
  const srtEscape = document.getElementById('srt-btn-escape');
  const origEscape = document.getElementById('tab-btn-escape');
  if (srtEscape && origEscape) {
    srtEscape.classList.toggle('has-data', origEscape.classList.contains('has-data'));
  }
}

// Called by sticky nav buttons — switch tab AND scroll to top of section
function switchResultTabSticky(tabId) {
  switchResultTab(tabId);

  // Immediately hide sticky + disconnect observer so scroll animation
  // doesn't re-trigger the observer and cause flicker
  const sticky = document.getElementById('sticky-result-tabs');
  if (sticky) sticky.classList.add('hidden');
  if (_stickyTabsObserver) _stickyTabsObserver.disconnect();
  _stickyTabsObserver = null;

  const anchor = document.getElementById('result-tabs-nav');
  if (anchor) anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });

  // Reconnect observer after smooth scroll finishes (~600ms)
  setTimeout(() => setupStickyResultTabs(), 650);
}

// ── Sticky Result Tabs (IntersectionObserver) ─────────────────────
let _stickyTabsObserver = null;

function setupStickyResultTabs() {
  const anchor = document.getElementById('result-tabs-nav');
  const sticky = document.getElementById('sticky-result-tabs');
  if (!anchor || !sticky) return;

  if (_stickyTabsObserver) _stickyTabsObserver.disconnect();

  const contentArea = document.querySelector('.content-area') || document.documentElement;

  _stickyTabsObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      // Show sticky when original tabs have scrolled above viewport
      const above = !entry.isIntersecting && entry.boundingClientRect.top < 0;
      sticky.classList.toggle('hidden', !above);
    });
  }, { root: contentArea, threshold: 0 });

  _stickyTabsObserver.observe(anchor);
}

function teardownStickyResultTabs() {
  if (_stickyTabsObserver) { _stickyTabsObserver.disconnect(); _stickyTabsObserver = null; }
  document.getElementById('sticky-result-tabs')?.classList.add('hidden');
}

// ── Escape Plan ──────────────────────────────────────────────────
function renderEscapePlan(plan) {
  const panel  = document.getElementById('escape-plan-panel');
  const tabBtn = document.getElementById('tab-btn-escape');
  if (!panel || !plan || !plan.interventions?.length) {
    if (tabBtn) tabBtn.classList.remove('has-data');
    return;
  }
  if (tabBtn) tabBtn.classList.add('has-data');

  const afterConf = plan.current_confidence - plan.combined_drop;
  const escapeEl   = document.getElementById('ep-after-conf');
  const currentEl  = document.getElementById('ep-current-conf');
  const possibleEl = document.getElementById('ep-possible');
  const listEl     = document.getElementById('ep-list');

  if (currentEl) currentEl.textContent = `${plan.current_confidence}%`;
  if (escapeEl)  escapeEl.textContent  = `${afterConf}%`;

  if (possibleEl) {
    if (plan.escape_possible) {
      possibleEl.className = 'ep-possible-badge ep-can-escape';
      possibleEl.textContent = `Pattern escape achievable — implement all ${plan.interventions.length} intervention${plan.interventions.length !== 1 ? 's' : ''}`;
    } else {
      possibleEl.className = 'ep-possible-badge ep-deeply-entrenched';
      possibleEl.textContent = 'Pattern deeply entrenched — significant restructuring required';
    }
  }

  const diffIcon = { easy: '', medium: '', hard: '' };

  if (listEl) {
    listEl.innerHTML = plan.interventions.slice(0, 5).map((item, i) => `
      <div class="ep-item ep-diff-${item.difficulty}">
        <div class="ep-item-rank">${i + 1}</div>
        <div class="ep-item-body">
          <div class="ep-item-top">
            <span class="ep-metric">${item.metric}</span>
            <span class="ep-values">${item.current_value} → <strong>${item.target_value}</strong></span>
            <span class="ep-diff-badge">${diffIcon[item.difficulty] || ''} ${item.difficulty}</span>
            <span class="ep-drop-badge">−${item.estimated_confidence_drop}pp risk</span>
          </div>
          <p class="ep-action">${item.action}</p>
        </div>
      </div>
    `).join('');
  }

  // Panel is now always visible inside its tab; just ensure tab is accessible
}

// ── Confidence Trajectory Forecast ──────────────────────────────
function _linearProject(values, stepsAhead) {
  const n = values.length;
  if (n < 2) return null;
  const xMean = (n - 1) / 2;
  const yMean = values.reduce((a, b) => a + b, 0) / n;
  let num = 0, den = 0;
  values.forEach((y, x) => { num += (x - xMean) * (y - yMean); den += (x - xMean) ** 2; });
  const slope = den > 0 ? num / den : 0;
  const intercept = yMean - slope * xMean;
  return { slope, project: ahead => Math.max(0, Math.min(100, Math.round(intercept + slope * (n - 1 + ahead)))) };
}

function renderConfidenceForecast(startupName, backendTrajectory) {
  const section = document.getElementById('conf-forecast-section');
  if (!section) return;

  try {
    // ── Prefer backend trajectory projections (MongoDB-based) ───────────
    if (backendTrajectory && backendTrajectory.snapshots_used >= 2) {
      const t       = backendTrajectory;
      const dir     = t.direction;
      const vel     = t.oracle_score_velocity;
      const osc1    = t.projected_score_1mo;
      const osc3    = t.projected_score_3mo;

      const trendIcon  = dir === 'deteriorating' ? '↑' : dir === 'recovering' ? '↓' : '→';
      const trendColor = dir === 'deteriorating' ? 'var(--danger)' : dir === 'recovering' ? 'var(--safe)' : 'var(--warning)';

      const velEl = document.getElementById('cf-velocity');
      if (velEl && vel != null && Math.abs(vel) >= 0.5) {
        velEl.textContent = `Oracle Score ${dir} ~${Math.abs(vel).toFixed(1)} pts/run · ${t.snapshots_used} MongoDB runs`;
        velEl.style.color = vel < 0 ? 'var(--safe)' : vel > 0 ? 'var(--danger)' : 'var(--muted)';
      } else if (velEl) { velEl.textContent = `${t.snapshots_used} MongoDB snapshots`; velEl.style.color = 'var(--muted)'; }

      document.getElementById('cf-trend-icon').textContent  = trendIcon;
      document.getElementById('cf-trend-label').textContent = `Risk ${dir}`;
      document.getElementById('cf-trend-icon').style.color  = trendColor;

      // Risk % — show — for +2/+3 since backend only gives 1mo and 3mo Oracle Score
      [1, 2, 3].forEach(m => {
        const el = document.getElementById(`cf-proj-${m}`);
        if (el) { el.textContent = '—'; el.style.color = 'var(--muted)'; }
      });

      // Oracle Score projections from backend
      [[1, osc1], [3, osc3]].forEach(([m, val]) => {
        const el = document.getElementById(`cf-osc-${m}`);
        if (el && val != null) {
          el.textContent = `${val}`;
          el.style.color = val < 25 ? 'var(--danger)' : val < 50 ? 'var(--warning)' : 'var(--safe)';
        }
      });
      const mid = document.getElementById('cf-osc-2');
      if (mid && osc1 != null && osc3 != null) {
        const midVal = Math.round((osc1 + osc3) / 2);
        mid.textContent = `~${midVal}`;
        mid.style.color = midVal < 25 ? 'var(--danger)' : midVal < 50 ? 'var(--warning)' : 'var(--safe)';
      }

      section.classList.remove('hidden');
      return;
    }

    // ── Fallback: localStorage history ───────────────────────────────────
    const all = JSON.parse(localStorage.getItem('oracle_snapshots') || '[]');
    const snapshots = all
      .filter(s => s.startup_name?.toLowerCase().trim() === startupName?.toLowerCase().trim())
      .slice(0, 8)
      .reverse();

    if (snapshots.length < 2) { section.classList.add('hidden'); return; }

    const confReg  = _linearProject(snapshots.map(s => (s.match_score || 0) * 100));
    const proj     = [1, 2, 3].map(a => confReg.project(a));
    const oscValues = snapshots.map(s => s.oracle_score).filter(v => typeof v === 'number');
    const oscReg   = oscValues.length >= 2 ? _linearProject(oscValues) : null;
    const oscProj  = oscReg ? [1, 2, 3].map(a => oscReg.project(a)) : null;

    const slope     = confReg.slope;
    const trend     = slope > 1.5 ? 'worsening' : slope < -1.5 ? 'improving' : 'stable';
    const trendColor = trend === 'worsening' ? 'var(--danger)' : trend === 'improving' ? 'var(--safe)' : 'var(--warning)';
    const trendIcon  = trend === 'worsening' ? '↑' : trend === 'improving' ? '↓' : '→';

    const velEl = document.getElementById('cf-velocity');
    if (velEl && oscReg && Math.abs(oscReg.slope) >= 0.5) {
      const dir = oscReg.slope < 0 ? 'deteriorating' : 'recovering';
      velEl.textContent = `Oracle Score ${dir} ~${Math.abs(oscReg.slope).toFixed(1)} pts/run`;
      velEl.style.color = oscReg.slope < 0 ? 'var(--danger)' : 'var(--safe)';
    } else if (velEl) { velEl.textContent = ''; }

    document.getElementById('cf-trend-icon').textContent  = trendIcon;
    document.getElementById('cf-trend-label').textContent = `Risk ${trend}`;
    document.getElementById('cf-trend-icon').style.color  = trendColor;

    [1, 2, 3].forEach((m, i) => {
      const el = document.getElementById(`cf-proj-${m}`);
      if (el) { el.textContent = `${proj[i]}%`; el.style.color = proj[i] >= 75 ? 'var(--danger)' : proj[i] >= 60 ? 'var(--warning)' : 'var(--safe)'; }
      const oscEl = document.getElementById(`cf-osc-${m}`);
      if (oscEl && oscProj) {
        oscEl.textContent = `${oscProj[i]}`;
        oscEl.style.color = oscProj[i] < 25 ? 'var(--danger)' : oscProj[i] < 50 ? 'var(--warning)' : 'var(--safe)';
      } else if (oscEl) { oscEl.textContent = '—'; }
    });

    section.classList.remove('hidden');
  } catch (_) {
    section.classList.add('hidden');
  }
}

// ── Trend Delta Badge ────────────────────────────────────────────
function renderTrendDelta(currentResult, startupName) {
  const badge = document.getElementById('trend-delta-badge');
  if (!badge) return;

  try {
    // ── Prefer backend trajectory (MongoDB multi-snapshot) ──────────────
    const t = currentResult.trajectory;
    if (t && t.snapshots_used >= 2) {
      const dir        = t.direction;          // deteriorating | recovering | stable
      const delta      = t.oracle_score_delta; // pts vs last run (signed)
      const vel        = t.oracle_score_velocity; // pts/run (signed: + = worsening)
      const confDelta  = t.confidence_delta_pp;
      const daysAgo    = t.days_since_last;

      const dateLabel  = daysAgo != null
        ? (daysAgo === 0 ? 'today' : daysAgo === 1 ? '1 day ago' : `${daysAgo}d ago`)
        : '';

      let arrow, cls, parts = [];
      if (dir === 'deteriorating') {
        arrow = '↑'; cls = 'delta-up';
      } else if (dir === 'recovering') {
        arrow = '↓'; cls = 'delta-down';
      } else {
        arrow = '→'; cls = 'delta-flat';
      }

      if (delta != null && Math.abs(delta) >= 2)
        parts.push(`Oracle Score ${delta > 0 ? '+' : ''}${delta}`);
      if (Math.abs(confDelta) >= 2)
        parts.push(`match ${confDelta > 0 ? '+' : ''}${confDelta}pp`);
      if (vel != null && Math.abs(vel) >= 1)
        parts.push(`velocity ~${Math.abs(vel).toFixed(1)} pts/run`);

      const changePart = parts.length ? parts.join(' · ') : 'no significant change';
      const dirLabel   = dir === 'stable' ? 'Stable' : dir === 'deteriorating' ? 'Risk increasing' : 'Risk decreasing';
      const text       = `${dirLabel} — ${changePart}${dateLabel ? ` (last run: ${dateLabel})` : ''} · ${t.snapshots_used} MongoDB snapshots`;

      badge.className = `trend-delta-badge ${cls}`;
      badge.innerHTML = `<span class="tdb-arrow">${arrow}</span><span class="tdb-text">${text}</span>`;
      badge.classList.remove('hidden');
      return;
    }

    // ── Fallback: localStorage history ──────────────────────────────────
    const all = JSON.parse(localStorage.getItem('oracle_snapshots') || '[]');
    const history = all.filter(s =>
      s.startup_name && startupName &&
      s.startup_name.toLowerCase().trim() === startupName.toLowerCase().trim()
    );
    const prior = history[0];
    if (!prior) { badge.classList.add('hidden'); return; }

    const currentConf = currentResult.pattern?.confidence ?? 0;
    const priorConf   = prior.match_score ?? 0;
    const deltaPp     = Math.round((currentConf - priorConf) * 100);
    const currentScore = currentResult.oracle_score ?? null;
    const priorScore   = prior.oracle_score ?? null;
    const deltaScore   = (currentScore !== null && priorScore !== null)
                          ? Math.round(currentScore - priorScore) : null;

    let velocityLabel = '';
    const scoreHistory = history.map(s => s.oracle_score).filter(v => typeof v === 'number');
    if (scoreHistory.length >= 2 && currentScore !== null) {
      const allScores = [currentScore, ...scoreHistory];
      const n = allScores.length, xm = (n - 1) / 2, ym = allScores.reduce((a, b) => a + b) / n;
      let num = 0, den = 0;
      allScores.forEach((y, x) => { num += (x - xm) * (y - ym); den += (x - xm) ** 2; });
      const slope = den > 0 ? -(num / den) : 0;
      if (Math.abs(slope) >= 1)
        velocityLabel = ` · ~${Math.abs(slope).toFixed(1)} pts/run`;
    }

    const priorDate = new Date(prior.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    let arrow, cls, text;
    if (Math.abs(deltaPp) < 2 && (deltaScore === null || Math.abs(deltaScore) < 2)) {
      arrow = '→'; cls = 'delta-flat';
      text = `No significant change vs ${priorDate}${velocityLabel}`;
    } else if (deltaPp > 0 || (deltaScore !== null && deltaScore < 0)) {
      arrow = '↑'; cls = 'delta-up';
      const parts = [];
      if (Math.abs(deltaPp) >= 2) parts.push(`match +${deltaPp}pp`);
      if (deltaScore !== null && Math.abs(deltaScore) >= 2) parts.push(`Oracle Score ${deltaScore > 0 ? '+' : ''}${deltaScore}`);
      text = `Risk increasing — ${parts.join(', ')} vs ${priorDate}${velocityLabel}`;
    } else {
      arrow = '↓'; cls = 'delta-down';
      const parts = [];
      if (Math.abs(deltaPp) >= 2) parts.push(`match ${deltaPp}pp`);
      if (deltaScore !== null && Math.abs(deltaScore) >= 2) parts.push(`Oracle Score ${deltaScore > 0 ? '+' : ''}${deltaScore}`);
      text = `Risk decreasing — ${parts.join(', ')} vs ${priorDate}${velocityLabel}`;
    }
    badge.className = `trend-delta-badge ${cls}`;
    badge.innerHTML = `<span class="tdb-arrow">${arrow}</span><span class="tdb-text">${text}</span><span class="tdb-date">${priorDate}</span>`;
    badge.classList.remove('hidden');
  } catch (_) {
    badge.classList.add('hidden');
  }
}

// ── Monthly Tracking (localStorage) ─────────────────────────────
const STORAGE_KEY = 'oracle_snapshots';

function saveSnapshot(result, payload) {
  if (!result || !payload) return;
  try {
    const snapshots = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    const snap = {
      date: new Date().toISOString(),
      startup_name: payload.startup_name,
      mrr: payload.mrr,
      mrr_growth: payload.mrr_growth_rate,
      churn: payload.churn_rate,
      nps: payload.nps,
      runway: payload.runway_months,
      alert: result.alert,
      pattern_name: result.pattern?.pattern_name || null,
      match_score: result.pattern?.confidence || 0,
      oracle_score: result.oracle_score || null,
    };
    snapshots.unshift(snap);
    // Keep last 12 snapshots
    localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshots.slice(0, 12)));
    renderHistory();
    renderTrendChart();
  } catch (_) {}
}

function buildSparkline(snapshots) {
  if (snapshots.length < 2) return '';
  const W = 300, H = 52, PAD = 8;
  const scores = snapshots.map(s => s.match_score || 0);
  const max = Math.max(...scores, 0.1);
  const pts = scores.map((v, i) => {
    const x = PAD + (i / (scores.length - 1)) * (W - PAD * 2);
    const y = H - PAD - (v / max) * (H - PAD * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  // Colour: last point red if alert, green if safe
  const lastAlert = snapshots[snapshots.length - 1]?.alert;
  const lineColor = lastAlert ? '#ef4444' : '#10b981';
  const areaPoints = `${PAD},${H - PAD} ${pts.join(' ')} ${(W - PAD).toFixed(1)},${H - PAD}`;

  return `<div class="hs-sparkline">
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px">
      <defs>
        <linearGradient id="spk-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${lineColor}" stop-opacity="0.3"/>
          <stop offset="100%" stop-color="${lineColor}" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <polygon points="${areaPoints}" fill="url(#spk-grad)"/>
      <polyline points="${pts.join(' ')}" fill="none" stroke="${lineColor}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>
      ${scores.map((v, i) => {
        const x = PAD + (i / (scores.length - 1)) * (W - PAD * 2);
        const y = H - PAD - (v / max) * (H - PAD * 2);
        return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="${snapshots[i].alert ? '#ef4444' : '#10b981'}" stroke="var(--surface)" stroke-width="1.5"/>`;
      }).join('')}
    </svg>
    <div class="hs-spark-labels">
      <span>${new Date(snapshots[0].date).toLocaleDateString('en-US',{month:'short',day:'numeric'})}</span>
      <span style="color:var(--muted);font-size:0.7rem">Risk score trend</span>
      <span>${new Date(snapshots[snapshots.length-1].date).toLocaleDateString('en-US',{month:'short',day:'numeric'})}</span>
    </div>
  </div>`;
}

function renderHistory() {
  const el = document.getElementById('history-panel');
  if (!el) return;
  const snapshots = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
  if (!snapshots.length) { el.classList.add('hidden'); return; }
  el.classList.remove('hidden');

  const totalSnaps = snapshots.length;
  const rows = snapshots.slice(0, 6).map((s, i) => {
    const d = new Date(s.date);
    const dateStr = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const timeStr = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    const runNum = totalSnaps - i;
    const riskCls = s.alert ? 'danger' : 'safe';
    const patternLabel = s.alert
      ? `${Math.round(s.match_score * 100)}% — ${(s.pattern_name || 'Risk detected').length > 30 ? (s.pattern_name || 'Risk detected').slice(0, 30) + '…' : (s.pattern_name || 'Risk detected')}`
      : 'No pattern detected';
    const trend = i < snapshots.length - 1
      ? (s.match_score > snapshots[i + 1].match_score ? '↑' : s.match_score < snapshots[i + 1].match_score ? '↓' : '→')
      : '—';
    const trendCls = trend === '↑' ? 'up' : trend === '↓' ? 'down' : 'flat';
    return `<div class="hs-row hs-row-${riskCls}" style="--row-index:${i}">
      <div class="hs-row-left">
        <span class="hs-run-badge">#${runNum}</span>
        <div class="hs-time-stack">
          <span class="hs-date">${dateStr}</span>
          <span class="hs-time">${timeStr}</span>
        </div>
      </div>
      <span class="hs-name">${s.startup_name}</span>
      <span class="hs-score-pill ${riskCls}">${patternLabel}</span>
      <span class="hs-trend-icon ${trendCls}">${trend}</span>
    </div>`;
  }).join('');

  // Build sparkline SVG from all snapshots (oldest→newest left→right)
  const sparkData = snapshots.slice(0, 12).reverse();
  const sparkline = buildSparkline(sparkData);

  el.innerHTML = `
    <div class="hs-header">
      <span>Monthly Tracking</span>
      <button class="hs-clear" onclick="clearHistory()">Clear</button>
    </div>
    ${sparkline}
    <div class="hs-rows">${rows}</div>
    <p class="hs-tip">Run this monthly — failure patterns build over 3–6 months. Track your trajectory.</p>
  `;
}

function clearHistory() {
  localStorage.removeItem(STORAGE_KEY);
  renderHistory();
  renderTrendChart();
}

// ── Metric Trend Chart (Chart.js) ────────────────────────────────
let _trendChart = null;

function renderTrendChart() {
  const section = document.getElementById('trend-chart-section');
  const canvas  = document.getElementById('trend-chart');
  if (!section || !canvas || typeof Chart === 'undefined') return;

  const snapshots = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    .slice(0, 12)
    .reverse(); // oldest first

  if (snapshots.length < 2) {
    section.classList.add('hidden');
    return;
  }
  section.classList.remove('hidden');

  const labels  = snapshots.map((_, i) => `Run #${i + 1}`);
  const growth  = snapshots.map(s => +(((s.mrr_growth || 0) * 100).toFixed(1)));
  const churn   = snapshots.map(s => +(((s.churn || 0) * 100).toFixed(1)));
  const alerts  = snapshots.map(s => s.alert ? s.match_score * 100 : null);

  const isDark  = document.documentElement.getAttribute('data-theme') === 'dark';
  const gridC   = isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.06)';
  const textC   = isDark ? '#94a3b8' : '#64748b';

  if (_trendChart) { _trendChart.destroy(); _trendChart = null; }

  _trendChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'MRR Growth %',
          data: growth,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59,130,246,0.12)',
          fill: true,
          tension: 0.4,
          yAxisID: 'y',
          pointRadius: 4,
          pointHoverRadius: 6,
        },
        {
          label: 'Churn %',
          data: churn,
          borderColor: '#ef4444',
          backgroundColor: 'rgba(239,68,68,0.07)',
          fill: true,
          tension: 0.4,
          yAxisID: 'y',
          pointRadius: 4,
          pointHoverRadius: 6,
        },
        {
          label: 'Risk Match %',
          data: alerts,
          borderColor: '#f59e0b',
          backgroundColor: 'rgba(245,158,11,0.10)',
          fill: false,
          tension: 0.2,
          yAxisID: 'y2',
          borderDash: [4, 4],
          pointRadius: 5,
          pointStyle: 'triangle',
          spanGaps: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: { color: textC, font: { size: 11 }, boxWidth: 16 },
        },
        tooltip: {
          callbacks: {
            title: ctx => {
              const idx = ctx[0]?.dataIndex ?? 0;
              const d = new Date(snapshots[idx].date);
              const dateStr = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
              const timeStr = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
              return `Run #${idx + 1} · ${dateStr} at ${timeStr}  —  ${snapshots[idx].startup_name}`;
            },
            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y !== null ? ctx.parsed.y.toFixed(1) + '%' : '—'}`,
          },
        },
      },
      scales: {
        x: {
          ticks: { color: textC, font: { size: 10 } },
          grid:  { color: gridC },
        },
        y: {
          position: 'left',
          title: { display: true, text: 'Growth / Churn %', color: textC, font: { size: 10 } },
          ticks: { color: textC, font: { size: 10 }, callback: v => v + '%' },
          grid:  { color: gridC },
        },
        y2: {
          position: 'right',
          title: { display: true, text: 'Risk Match %', color: textC, font: { size: 10 } },
          ticks: { color: '#f59e0b', font: { size: 10 }, callback: v => v + '%' },
          grid:  { drawOnChartArea: false },
          min: 0, max: 100,
        },
      },
    },
  });
}

// ── Stripe Integration ────────────────────────────────────────────
// ── Transcript Extraction ─────────────────────────────────────────
function toggleTranscript() {
  const body = document.getElementById('transcript-body');
  const btn  = document.getElementById('transcript-toggle-btn');
  const open = body.classList.toggle('hidden');
  btn.classList.toggle('active', !open);
  if (!open) document.getElementById('transcript-input').focus();
}

async function extractFromTranscript() {
  const text = document.getElementById('transcript-input').value.trim();
  if (text.length < 30) return;

  const btn  = document.getElementById('transcript-btn');
  const note = document.getElementById('transcript-note');
  btn.textContent = 'Extracting with Gemini 3…';
  btn.disabled = true;
  note.classList.add('hidden');

  try {
    const res = await fetch(`${API}/api/metrics/extract-metrics`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // Fill form fields with extracted values
    const fields = ['startup_name','current_month','mrr','mrr_growth_rate',
                    'churn_rate','burn_rate','runway_months','headcount',
                    'nps','cac','ltv','industry'];
    fields.forEach(key => {
      const el = document.getElementById(key);
      if (el && data[key] !== undefined) el.value = data[key];
    });

    updateLiveMetrics();

    // Show extraction notes
    if (data.extraction_notes) {
      note.textContent = `✓ Extracted — ${data.extraction_notes}`;
      note.classList.remove('hidden');
    }

    // Collapse the transcript panel after filling
    setTimeout(() => {
      document.getElementById('transcript-body').classList.add('hidden');
      document.getElementById('transcript-toggle-btn').classList.remove('active');
    }, 2000);

  } catch (err) {
    note.textContent = 'Extraction failed — please enter metrics manually.';
    note.classList.remove('hidden');
  } finally {
    btn.textContent = 'Extract Metrics';
    btn.disabled = false;
  }
}

function openStripeModal() {
  document.getElementById('stripe-modal').classList.remove('hidden');
  document.getElementById('stripe-key-input').focus();
}

function closeStripeModal() {
  document.getElementById('stripe-modal').classList.add('hidden');
}

async function fetchStripeMetrics() {
  const key = document.getElementById('stripe-key-input').value.trim();
  if (!key || !key.startsWith('sk_')) {
    alert('Please enter a valid Stripe API key (starts with sk_test_ or sk_live_)');
    return;
  }
  const btn = document.getElementById('stripe-fetch-btn');
  btn.textContent = 'Connecting...';
  btn.disabled = true;

  try {
    const res = await fetch(`${API}/api/integrations/stripe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();

    // Auto-fill the form
    if (data.mrr) document.getElementById('mrr').value = Math.round(data.mrr);
    if (data.mrr_growth_rate !== undefined) document.getElementById('mrr_growth_rate').value = data.mrr_growth_rate.toFixed(3);
    if (data.churn_rate !== undefined) document.getElementById('churn_rate').value = data.churn_rate.toFixed(3);
    if (data.customer_count) document.getElementById('headcount').value = Math.max(1, Math.round(data.customer_count / 20));

    // Trigger live indicators
    ['mrr_growth_rate', 'churn_rate', 'runway_months', 'nps'].forEach(f => {
      const el = document.getElementById(f);
      if (el) el.dispatchEvent(new Event('input'));
    });

    closeStripeModal();
    // Show confirmation
    const tip = document.createElement('div');
    tip.className = 'stripe-connected-badge';
    tip.innerHTML = `<span>Stripe connected — MRR $${Math.round(data.mrr || 0).toLocaleString()}, ${data.customer_count || 0} customers</span>`;
    document.getElementById('input-section').insertBefore(tip, document.getElementById('metrics-form'));
    setTimeout(() => tip.remove(), 5000);
  } catch (err) {
    alert(`Stripe connection failed: ${err.message}`);
  } finally {
    btn.textContent = 'Import Metrics';
    btn.disabled = false;
  }
}

function togglePatterns() {
  const container = document.getElementById('patterns-container');
  const btn = document.getElementById('toggle-patterns-btn');
  const count = document.getElementById('patterns-count').textContent;
  if (container.classList.contains('hidden')) {
    container.classList.remove('hidden');
    btn.innerHTML = `Hide Pattern Library (<span id="patterns-count">${count}</span>)`;
  } else {
    container.classList.add('hidden');
    btn.innerHTML = `View Pattern Library (<span id="patterns-count">${count}</span>)`;
  }
}

// ── VC Portfolio Mode ────────────────────────────────────────────
function initPortfolio() {
  const container = document.getElementById('portfolio-entries');
  if (!container || container.children.length > 0) return;
  for (let i = 0; i < 3; i++) addPortfolioRow();
}

function addPortfolioRow() {
  const container = document.getElementById('portfolio-entries');
  if (!container) return;
  const idx = container.children.length + 1;
  const row = document.createElement('div');
  row.className = 'pf-row';
  row.innerHTML = `
    <input type="text"   placeholder="Company #${idx}" class="pf-name-in">
    <input type="number" placeholder="MRR ($)"     class="pf-mrr-in"     min="0" step="1000">
    <input type="number" placeholder="Churn %"     class="pf-churn-in"   min="0" max="100" step="0.1">
    <input type="number" placeholder="Runway (mo)" class="pf-runway-in"  min="0" max="120">
    <button class="pf-row-remove" onclick="this.parentElement.remove()" title="Remove">✕</button>
  `;
  container.appendChild(row);
}

function loadExamplePortfolio() {
  const container = document.getElementById('portfolio-entries');
  if (!container) return;
  // Clear existing rows
  container.innerHTML = '';
  // Example YC W24 cohort companies
  const examples = [
    { name: 'HealthTech AI',  mrr: 85000,  churn: 6,   runway: 16 },
    { name: 'NeoCommerce',    mrr: 320000, churn: 14,  runway: 8  },
    { name: 'DevToolsCo',     mrr: 55000,  churn: 2,   runway: 22 },
  ];
  examples.forEach((ex, i) => {
    addPortfolioRow();
    const rows = container.querySelectorAll('.pf-row');
    const row = rows[rows.length - 1];
    if (!row) return;
    const nameIn   = row.querySelector('.pf-name-in');
    const mrrIn    = row.querySelector('.pf-mrr-in');
    const churnIn  = row.querySelector('.pf-churn-in');
    const runwayIn = row.querySelector('.pf-runway-in');
    if (nameIn)   nameIn.value   = ex.name;
    if (mrrIn)    mrrIn.value    = ex.mrr;
    if (churnIn)  churnIn.value  = ex.churn;
    if (runwayIn) runwayIn.value = ex.runway;
  });
}

async function runPortfolio() {
  const container = document.getElementById('portfolio-entries');
  const btn       = document.getElementById('pf-run-btn');
  const btnText   = document.getElementById('pf-btn-text');
  const spinner   = document.getElementById('pf-btn-spinner');
  const resultEl  = document.getElementById('portfolio-result');

  const rows = Array.from(container.querySelectorAll('.pf-row'));
  const startups = rows.map(row => {
    const name   = row.querySelector('.pf-name-in')?.value?.trim();
    const mrr    = parseFloat(row.querySelector('.pf-mrr-in')?.value) || 0;
    const churn  = parseFloat(row.querySelector('.pf-churn-in')?.value) || 0;
    const runway = parseInt(row.querySelector('.pf-runway-in')?.value)  || 12;
    if (!name) return null;
    return {
      startup_name:    name,
      current_month:   12,
      mrr,
      mrr_growth_rate: 0.10,
      churn_rate:      churn / 100,
      burn_rate:       mrr * 1.3,
      runway_months:   runway,
      headcount:       15,
      nps:             35,
      cac:             1200,
      ltv:             8000,
      industry:        'B2B SaaS',
    };
  }).filter(Boolean);

  if (startups.length === 0) {
    alert('Add at least one company with a name.');
    return;
  }
  _portfolioLastMetrics = startups;

  btnText.classList.add('hidden');
  spinner.classList.remove('hidden');
  btn.disabled = true;
  resultEl.classList.add('hidden');

  try {
    const res = await fetch(`${API}/api/portfolio/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ startups }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderPortfolio(data);
    resultEl.classList.remove('hidden');
    resultEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (err) {
    alert(`Portfolio analysis failed: ${err.message}`);
  } finally {
    btnText.classList.remove('hidden');
    spinner.classList.add('hidden');
    btn.disabled = false;
  }
}

function renderPortfolio(data) {
  const summaryEl = document.getElementById('pf-summary');
  const gridEl    = document.getElementById('pf-grid');

  const riskColors = { CRITICAL: '#ef4444', HIGH: '#f97316', MODERATE: '#f59e0b', SAFE: '#10b981' };
  const riskBg     = { CRITICAL: 'rgba(239,68,68,0.06)', HIGH: 'rgba(249,115,22,0.06)', MODERATE: 'rgba(245,158,11,0.06)', SAFE: 'rgba(16,185,129,0.06)' };

  const atRisk = data.critical + data.high_risk;
  const portfolioHealth = data.safe === data.total ? 'All Clear' :
    data.critical > 0 ? 'Portfolio Alert' : 'Monitor Required';
  const healthColor = data.critical > 0 ? '#ef4444' : data.high_risk > 0 ? '#f97316' : '#10b981';

  summaryEl.innerHTML = `
    <div class="pf-danger-board">
      <div class="pf-danger-headline" style="color:${healthColor}">${portfolioHealth}</div>
      <div class="pf-danger-sub">${atRisk} of ${data.total} companies need immediate attention</div>
    </div>
    <div class="pf-sum-chips">
      <div class="pf-sum-chip pf-sum-critical"><span>${data.critical}</span> Critical</div>
      <div class="pf-sum-chip pf-sum-high"><span>${data.high_risk}</span> High Risk</div>
      <div class="pf-sum-chip pf-sum-moderate"><span>${data.moderate}</span> Moderate</div>
      <div class="pf-sum-chip pf-sum-safe"><span>${data.safe}</span> Safe</div>
    </div>
  `;

  gridEl.innerHTML = data.companies.map((c, i) => {
    const pct   = Math.round(c.confidence * 100);
    const color = riskColors[c.risk_level] || '#6366f1';
    const bg    = riskBg[c.risk_level] || 'transparent';
    const survPct = c.survival_rate != null ? Math.round(c.survival_rate * 100) : null;
    const days  = c.days_to_crisis ? `~${c.days_to_crisis}d` : '';

    const metricsForDive = _portfolioLastMetrics?.[i];
    const diveBtn = metricsForDive ? `
      <button class="pf-dive-btn" onclick='loadPortfolioCompany(${JSON.stringify(metricsForDive)})'>
        Deep Dive →
      </button>` : '';

    return `
      <div class="pf-company-card" style="border-left-color:${color};background:${bg}">
        <div class="pf-card-top">
          <div class="pf-card-rank">#${i + 1}</div>
          <div class="pf-card-name">${c.startup_name}</div>
          <div class="pf-card-badge" style="background:${color}20;color:${color};border-color:${color}40">${c.risk_level}</div>
        </div>

        ${c.pattern_name ? `
        <div class="pf-card-pattern">
          <span class="pf-card-pattern-name">${c.pattern_name}</span>
          <div class="pf-conf-track">
            <div class="pf-conf-fill" style="width:${pct}%;background:${color}"></div>
          </div>
          <span class="pf-conf-pct" style="color:${color}">${pct}%</span>
        </div>` : '<div class="pf-card-pattern pf-safe-tag">No dangerous pattern detected</div>'}

        <div class="pf-card-stats">
          ${survPct != null ? `<div class="pf-card-stat"><span class="pf-stat-big" style="color:${survPct < 20 ? '#ef4444' : '#10b981'}">${survPct}%</span><span class="pf-stat-tiny">survived</span></div>` : ''}
          ${days ? `<div class="pf-card-stat"><span class="pf-stat-big">${days}</span><span class="pf-stat-tiny">to crisis</span></div>` : ''}
        </div>

        ${c.match_reasoning ? `<div class="pf-card-reasoning">${c.match_reasoning}</div>` : ''}

        ${diveBtn}
      </div>`;
  }).join('');
}

// Store last portfolio metrics for "Deep Dive" buttons
let _portfolioLastMetrics = null;

function loadPortfolioCompany(metrics) {
  // Pre-fill the main form and switch to dashboard
  Object.entries(metrics).forEach(([k, v]) => {
    const el = document.getElementById(k);
    if (el) { el.value = v; el.dispatchEvent(new Event('input')); }
  });
  switchTab('tab-dashboard');
  updateLiveMetrics();
  setTimeout(() => document.getElementById('run-btn')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 300);
}

// ── Pattern Submission ────────────────────────────────────────────
async function submitPattern() {
  const name      = document.getElementById('sf-name')?.value.trim();
  const category  = document.getElementById('sf-category')?.value;
  const narrative = document.getElementById('sf-narrative')?.value.trim();
  const company   = document.getElementById('sf-company')?.value.trim();
  const role      = document.getElementById('sf-role')?.value.trim();
  const statusEl  = document.getElementById('sf-status');
  const btn       = document.getElementById('sf-submit-btn');
  const btnText   = document.getElementById('sf-btn-text');
  const spinner   = document.getElementById('sf-btn-spinner');

  if (!name || name.length < 5) { showSFStatus('Please enter a pattern name (min 5 characters).', 'error'); return; }
  if (!category) { showSFStatus('Please select a category.', 'error'); return; }
  if (!narrative || narrative.length < 30) { showSFStatus('Please describe the pattern (min 30 characters).', 'error'); return; }

  btn.disabled = true;
  btnText.classList.add('hidden');
  spinner.classList.remove('hidden');
  statusEl.classList.add('hidden');

  try {
    const res = await fetch(`${API}/api/patterns/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pattern_name: name, category, narrative, company: company || null, submitter_role: role || null }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showSFStatus('✓ ' + data.message, 'success');
    document.getElementById('sf-name').value     = '';
    document.getElementById('sf-narrative').value = '';
    document.getElementById('sf-company').value  = '';
    document.getElementById('sf-role').value     = '';
    document.getElementById('sf-category').value = '';
  } catch (err) {
    showSFStatus('Submission failed — please try again.', 'error');
  } finally {
    btn.disabled = false;
    btnText.classList.remove('hidden');
    spinner.classList.add('hidden');
  }
}

function showSFStatus(msg, type) {
  const el = document.getElementById('sf-status');
  if (!el) return;
  el.textContent = msg;
  el.className = `sf-status sf-${type}`;
  el.classList.remove('hidden');
}

// --- Live Education Panel Logic ---
const formInputs = document.querySelectorAll('#metrics-form input');
formInputs.forEach(input => {
  input.addEventListener('input', updateLiveMetrics);
});

function updateLiveMetrics() {
  const mrr = parseFloat(document.getElementById('mrr').value) || 0;
  const growth = parseFloat(document.getElementById('mrr_growth_rate').value) || 0;
  const burn = parseFloat(document.getElementById('burn_rate').value) || 0;
  const ltv = parseFloat(document.getElementById('ltv').value) || 0;
  const cac = parseFloat(document.getElementById('cac').value) || 0;
  const runway = parseFloat(document.getElementById('runway_months').value) || 0;
  const npsRaw = document.getElementById('nps').value;
  const nps = npsRaw !== '' ? parseFloat(npsRaw) : null;

  const netNewMrr = mrr * growth;
  const burnMultiple = netNewMrr > 0 ? (burn / netNewMrr) : 99;
  
  const burnEl = document.getElementById('live-burn');
  const burnBar = document.getElementById('live-burn-bar');
  if (burn > 0 && netNewMrr > 0) {
    burnEl.textContent = burnMultiple.toFixed(1) + 'x';
    burnEl.className = 'lm-value ' + (burnMultiple <= 1.5 ? 'healthy' : (burnMultiple <= 3 ? 'warning' : 'danger'));
    if (burnBar) {
      const pct = Math.max(0, Math.min(100, (1 - (burnMultiple / 4.0)) * 100)); // lower burn multiple is better
      burnBar.style.width = `${pct}%`;
      burnBar.className = 'lm-bar-fill ' + (burnMultiple <= 1.5 ? 'healthy' : (burnMultiple <= 3 ? 'warning' : 'danger'));
    }
  } else {
    burnEl.textContent = '--';
    burnEl.className = 'lm-value';
    if (burnBar) burnBar.style.width = '0%';
  }

  const ltvcac = cac > 0 ? (ltv / cac) : 0;
  const ltvEl = document.getElementById('live-ltvcac');
  const ltvBar = document.getElementById('live-ltvcac-bar');
  if (ltv > 0 && cac > 0) {
    ltvEl.textContent = ltvcac.toFixed(1) + 'x';
    ltvEl.className = 'lm-value ' + (ltvcac >= 3 ? 'healthy' : (ltvcac >= 1.5 ? 'warning' : 'danger'));
    if (ltvBar) {
      const pct = Math.max(0, Math.min(100, (ltvcac / 5.0) * 100)); // higher is better
      ltvBar.style.width = `${pct}%`;
      ltvBar.className = 'lm-bar-fill ' + (ltvcac >= 3 ? 'healthy' : (ltvcac >= 1.5 ? 'warning' : 'danger'));
    }
  } else {
    ltvEl.textContent = '--';
    ltvEl.className = 'lm-value';
    if (ltvBar) ltvBar.style.width = '0%';
  }

  const runwayEl = document.getElementById('live-runway');
  const runwayBar = document.getElementById('live-runway-bar');
  if (runway > 0) {
    runwayEl.textContent = runway + ' mo';
    runwayEl.className = 'lm-value ' + (runway >= 18 ? 'healthy' : (runway >= 9 ? 'warning' : 'danger'));
    if (runwayBar) {
      const pct = Math.max(0, Math.min(100, (runway / 24.0) * 100));
      runwayBar.style.width = `${pct}%`;
      runwayBar.className = 'lm-bar-fill ' + (runway >= 18 ? 'healthy' : (runway >= 9 ? 'warning' : 'danger'));
    }
  } else {
    runwayEl.textContent = '--';
    runwayEl.className = 'lm-value';
    if (runwayBar) runwayBar.style.width = '0%';
  }

  // NPS metric
  const npsEl = document.getElementById('live-nps-val');
  const npsBar = document.getElementById('live-nps-bar');
  if (nps !== null) {
    npsEl.textContent = (nps > 0 ? '+' : '') + nps;
    const npsSt = nps >= 50 ? 'healthy' : nps >= 20 ? 'warning' : 'danger';
    npsEl.className = 'lm-value ' + npsSt;
    if (npsBar) {
      npsBar.style.width = `${Math.max(0, Math.min(100, ((nps + 100) / 200) * 100))}%`;
      npsBar.className = 'lm-bar-fill ' + npsSt;
    }
  } else {
    if (npsEl) { npsEl.textContent = '--'; npsEl.className = 'lm-value'; }
    if (npsBar) npsBar.style.width = '0%';
  }

  // Composite health score (0–100)
  const compEl = document.getElementById('live-composite');
  const compBar = document.getElementById('live-composite-bar');
  const compDesc = document.getElementById('live-composite-desc');
  const netNewMrrComp = mrr * growth;
  const burnMulComp = netNewMrrComp > 0 ? (burn / netNewMrrComp) : 99;
  const ltvcacComp = cac > 0 ? (ltv / cac) : 0;
  const hasAnyData = (burn > 0 && mrr > 0 && growth > 0) || (ltv > 0 && cac > 0) || runway > 0;
  if (hasAnyData && compEl) {
    const burnPts  = (burn > 0 && netNewMrrComp > 0) ? (burnMulComp <= 1.5 ? 33 : burnMulComp <= 3 ? 18 : 0) : 0;
    const ltvcacPts = (ltv > 0 && cac > 0) ? (ltvcacComp >= 3 ? 33 : ltvcacComp >= 1.5 ? 18 : 5) : 0;
    const runwayPts = runway > 0 ? (runway >= 18 ? 34 : runway >= 9 ? 20 : 5) : 0;
    const score = burnPts + ltvcacPts + runwayPts;
    compEl.textContent = score + '/100';
    const compSt = score >= 60 ? 'healthy' : score >= 35 ? 'warning' : 'danger';
    compEl.className = 'lm-composite-value ' + compSt;
    if (compBar) { compBar.style.width = `${score}%`; compBar.className = 'lm-composite-bar ' + compSt; }
    if (compDesc) compDesc.textContent = score >= 60 ? 'Metrics look healthy — low failure risk'
      : score >= 35 ? 'Warning signals present — monitor closely'
      : 'Critical risk indicators — intervention needed';
  }
}

// Hook into fillDemo
let _suppressFillDemoAutoRun = false;
const originalFillDemo = fillDemo;
fillDemo = function(preset) {
  originalFillDemo(preset);
  updateLiveMetrics();
  if (_suppressFillDemoAutoRun) return;
  setTimeout(() => {
    const analyzeBtn = document.getElementById('analyze-btn');
    if (analyzeBtn) analyzeBtn.click();
  }, 50);
};

// ── Share to Slack ────────────────────────────────────────────────
async function shareToSlack() {
  if (!_lastResult?.alert || !_lastPayload) return;
  const p = _lastResult.pattern;
  const pct = Math.round(p.confidence * 100);
  const btn = document.getElementById('slack-share-btn');
  btn.textContent = 'Posting…';
  btn.disabled = true;

  try {
    const res = await fetch(`${API}/api/metrics/slack-share`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        startup_name:    _lastPayload.startup_name,
        pattern_name:    p.pattern_name,
        confidence:      p.confidence,
        days_to_crisis:  p.days_to_crisis,
        survival_rate:   p.survival_rate,
        match_reasoning: p.match_reasoning || null,
      }),
    });
    if (res.ok) {
      const c = document.getElementById('slack-confirm');
      c.classList.remove('hidden');
      setTimeout(() => c.classList.add('hidden'), 2500);
    } else {
      alert('Slack not configured — add SLACK_WEBHOOK_URL to your environment.');
    }
  } catch {
    alert('Slack share failed. Check SLACK_WEBHOOK_URL in your environment.');
  } finally {
    btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" style="margin-right:0.3rem;vertical-align:-2px"><path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zM15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z"/></svg> Share to Slack`;
    btn.disabled = false;
  }
}

// ── Continuous Monitoring ────────────────────────────────────────
async function enableMonitoring() {
  if (!_lastPayload) return;
  const btn = document.getElementById('monitor-btn');
  btn.textContent = 'Enabling…';
  btn.disabled = true;
  try {
    const res = await fetch(`${API}/api/metrics/watch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(_lastPayload),
    });
    const data = await res.json();
    if (data.watching) {
      document.getElementById('monitor-panel').classList.add('hidden');
      const active = document.getElementById('monitor-active');
      document.getElementById('ma-text').textContent =
        `Oracle is watching ${_lastPayload.startup_name} — re-analysis every 6 hours, results stored in MongoDB`;
      active.classList.remove('hidden');
    }
  } catch (e) {
    btn.textContent = 'Watch My Startup';
    btn.disabled = false;
  }
}

// ── Keyboard Shortcuts ────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  // Escape: close any open modal
  if (e.key === 'Escape') {
    const hiwOverlay = document.getElementById('hiw-overlay');
    if (hiwOverlay && !hiwOverlay.classList.contains('hidden')) {
      if (typeof closeHowItWorks === 'function') closeHowItWorks();
    }
    const stripeModal = document.getElementById('stripe-modal');
    if (stripeModal && !stripeModal.classList.contains('hidden')) {
      if (typeof closeStripeModal === 'function') closeStripeModal();
    }
  }

  // Cmd/Ctrl+Enter: submit form from anywhere on the page
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault();
    const activeEl = document.activeElement;
    // Don't trigger if user is in the audit textarea
    if (activeEl && activeEl.id === 'decision-text') return;
    runAnalysis();
  }
});

// ── Trajectory Forecast Chart ──────────────────────────────────────
let _trajectoryChartInstance = null;

function renderTrajectoryChart(p, pl) {
  const ctx = document.getElementById('trajectory-chart');
  if (!ctx) return;

  if (_trajectoryChartInstance) {
    _trajectoryChartInstance.destroy();
  }

  const runway = pl.runway_months || 12;
  const projectionMonths = Math.max(12, Math.round(runway * 1.5));
  
  const labels = [];
  const currentPath = [];
  const failurePath = [];
  const recoveryPath = [];

  for (let m = 0; m <= projectionMonths; m++) {
    labels.push(`M +${m}`);
    
    // Danger path
    const curVal = Math.max(0, runway - m);
    currentPath.push(curVal);

    // Exponential failure pattern spiral
    const failVal = Math.max(0, Math.round(runway * Math.pow(0.8, m) * (1 - (m / projectionMonths) * 0.4)));
    failurePath.push(failVal);

    // Playbook recovery path
    let recVal = runway;
    if (m === 0) {
      recVal = runway;
    } else {
      recVal = Math.min(24, Math.round(runway + (m * 0.8)));
    }
    recoveryPath.push(recVal);
  }

  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const gridColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
  const textColor = isDark ? '#94a3b8' : '#64748b';

  // Create glowing gradient backgrounds for trajectory lines
  const ctx2d = ctx.getContext('2d');
  const currentGradient = ctx2d.createLinearGradient(0, 0, 0, 240);
  currentGradient.addColorStop(0, 'rgba(239, 68, 68, 0.28)');
  currentGradient.addColorStop(1, 'rgba(239, 68, 68, 0.00)');

  const recoveryGradient = ctx2d.createLinearGradient(0, 0, 0, 240);
  recoveryGradient.addColorStop(0, 'rgba(16, 185, 129, 0.28)');
  recoveryGradient.addColorStop(1, 'rgba(16, 185, 129, 0.00)');

  _trajectoryChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Current Trajectory (Danger)',
          data: currentPath,
          borderColor: '#ef4444',
          backgroundColor: currentGradient,
          borderWidth: 3,
          tension: 0.3,
          fill: true
        },
        {
          label: 'Historical Pattern Path',
          data: failurePath,
          borderColor: '#f59e0b',
          borderWidth: 2,
          borderDash: [5, 5],
          tension: 0.3,
          fill: false
        },
        {
          label: 'Recovery Trajectory (Playbook)',
          data: recoveryPath,
          borderColor: '#10b981',
          backgroundColor: recoveryGradient,
          borderWidth: 3,
          tension: 0.3,
          fill: true
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          labels: {
            color: textColor,
            font: { family: 'Outfit', size: 11, weight: '500' }
          }
        },
        tooltip: {
          mode: 'index',
          intersect: false
        }
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { family: 'Inter', size: 10 } }
        },
        y: {
          grid: { color: gridColor },
          title: {
            display: true,
            text: 'Projected Runway (Months)',
            color: textColor,
            font: { family: 'Outfit', size: 11, weight: '600' }
          },
          ticks: { color: textColor, font: { family: 'Inter', size: 10 } },
          min: 0
        }
      }
    }
  });
}

// ── Agent Audio Debate / Debrief ──────────────────────────────────
let _speechSynthesisUtterances = [];
let _isDebatePlaying = false;

function toggleAudioWave(active) {
  const wave = document.getElementById('chp-audio-wave');
  if (wave) {
    if (active) wave.classList.remove('hidden');
    else wave.classList.add('hidden');
  }
}

function playAudioDebrief() {
  const synth = window.speechSynthesis;
  if (!synth) {
    alert('Web Speech API is not supported in your browser.');
    return;
  }

  const btn = document.getElementById('chp-play-btn');
  const statusEl = document.getElementById('chp-audio-status');
  const icon = document.getElementById('chp-play-icon');
  const text = document.getElementById('chp-play-text');

  if (_isDebatePlaying) {
    synth.cancel();
    _isDebatePlaying = false;
    toggleAudioWave(false);
    if (text) text.textContent = 'Listen to Agent Debate';
    if (statusEl) { statusEl.textContent = 'Debate stopped'; }
    if (icon) {
      icon.innerHTML = '<polygon points="5 3 19 12 5 21 5 3"></polygon>';
    }
    return;
  }

  const p = _lastResult?.pattern;
  if (!p) return;

  const matchedName = p.pattern_name;
  const pct = Math.round(p.confidence * 100);
  const reasoning = p.match_reasoning || "our standard warning markers are triggered";
  
  const challengerEl = document.getElementById('chp-reasoning');
  const challengerText = challengerEl ? challengerEl.textContent : "I recommend careful review of counter-indicators.";

  const script = [
    {
      role: 'Investigator Agent',
      pitch: 0.9,
      rate: 0.95,
      text: `Investigation report compiled. We have identified a strong ${pct} percent match with the failure archetype: ${matchedName}. The primary risk factors are clear: ${reasoning.slice(0, 160)}. The data points directly to a high probability of failure unless immediate pivots are made.`
    },
    {
      role: 'Challenger Agent',
      pitch: 1.15,
      rate: 1.05,
      text: `Let me challenge that absolute conclusion. While the ${pct} percent similarity is technically correct, our counter-evidence assessment shows important mitigating factors. ${challengerText.slice(0, 180)} We must not premature scale or over-generalize this risk.`
    },
    {
      role: 'Investigator Agent',
      pitch: 0.9,
      rate: 0.95,
      text: `Acknowledged, but the survival rate is only ${Math.round(p.survival_rate * 100)} percent. Founders who ignored these warning signs historically ran out of cash within ${p.days_to_crisis || 90} days. Skepticism is healthy, but inaction is fatal.`
    },
    {
      role: 'Challenger Agent',
      pitch: 1.15,
      rate: 1.05,
      text: `Agreed. Which is why the survival playbook must be deployed immediately. Focus on unit economics and retention. That is the path to beating the statistics.`
    }
  ];

  _speechSynthesisUtterances = [];
  _isDebatePlaying = true;
  toggleAudioWave(true);
  if (text) text.textContent = 'Stop Agent Debate';
  if (statusEl) { statusEl.style.display = 'inline'; statusEl.textContent = 'Speaking...'; }
  if (icon) {
    icon.innerHTML = '<rect x="4" y="4" width="16" height="16" fill="currentColor"></rect>';
  }

  const voices = synth.getVoices();
  
  function getVoiceForRole(role) {
    if (role === 'Investigator Agent') {
      return voices.find(v => v.name.includes('David') || v.name.includes('Google US English') || v.name.includes('Microsoft David') || v.lang.startsWith('en-US')) || voices[0];
    } else {
      return voices.find(v => v.name.includes('Zira') || v.name.includes('Google UK English Female') || v.name.includes('Microsoft Zira') || v.name.includes('Hazel') || v.lang.startsWith('en-GB') || v.lang.includes('en')) || voices[0];
    }
  }

  let index = 0;
  function speakNext() {
    if (index >= script.length || !_isDebatePlaying) {
      _isDebatePlaying = false;
      toggleAudioWave(false);
      if (text) text.textContent = 'Listen to Agent Debate';
      if (statusEl) { statusEl.textContent = 'Debate finished'; }
      if (icon) {
        icon.innerHTML = '<polygon points="5 3 19 12 5 21 5 3"></polygon>';
      }
      return;
    }

    const turn = script[index];
    const utter = new SpeechSynthesisUtterance(turn.text);
    const chosenVoice = getVoiceForRole(turn.role);
    if (chosenVoice) {
      utter.voice = chosenVoice;
    }
    utter.pitch = turn.pitch;
    utter.rate = turn.rate;

    if (statusEl) {
      statusEl.textContent = `${turn.role} speaking...`;
    }

    utter.onend = () => {
      index++;
      speakNext();
    };

    utter.onerror = () => {
      _isDebatePlaying = false;
      toggleAudioWave(false);
      if (text) text.textContent = 'Listen to Agent Debate';
      if (statusEl) statusEl.textContent = 'Debate finished';
      if (icon) icon.innerHTML = '<polygon points="5 3 19 12 5 21 5 3"></polygon>';
    };

    _speechSynthesisUtterances.push(utter);
    synth.speak(utter);
  }

  if (voices.length === 0) {
    synth.onvoiceschanged = () => {
      speakNext();
    };
  } else {
    speakNext();
  }
}

// ── Cocktail Detection ────────────────────────────────────────────
function renderCocktail(cocktail) {
  const panel = document.getElementById('cocktail-panel');
  if (!panel || !cocktail) { if (panel) panel.classList.add('hidden'); return; }

  const survPct = Math.round(cocktail.compound_survival_rate * 100);
  const countEl = document.getElementById('ctail-count');
  const survEl  = document.getElementById('ctail-survival-val');
  const patsEl  = document.getElementById('ctail-patterns');
  const sumEl   = document.getElementById('ctail-summary');

  if (countEl) countEl.textContent = cocktail.patterns.length;
  if (survEl)  { survEl.textContent = `${survPct}%`; survEl.style.color = survPct < 10 ? 'var(--danger)' : survPct < 25 ? 'var(--warning)' : 'var(--safe)'; }
  if (sumEl)   sumEl.textContent = cocktail.risk_summary;

  if (patsEl) {
    patsEl.innerHTML = cocktail.patterns.map((p, i) => {
      const conf = Math.round(p.confidence * 100);
      const surv = Math.round(p.survival_rate * 100);
      const survColor = surv < 15 ? 'var(--danger)' : surv < 30 ? 'var(--warning)' : 'var(--safe)';
      const domBadge = i === 0 ? '<span class="ctail-dominant-badge">DOMINANT</span>' : '';
      return `
        <div class="ctail-pattern-item">
          <div class="ctail-pattern-top">
            <span class="ctail-pattern-id">${p.pattern_id}</span>
            ${domBadge}
            <span class="ctail-pattern-name">${p.pattern_name}</span>
            <span class="ctail-pattern-conf">${conf}% match</span>
          </div>
          <div class="ctail-pattern-meta">
            <span class="ctail-pat-surv" style="color:${survColor}">${surv}% survival</span>
            <span class="ctail-pat-sep">·</span>
            <span class="ctail-pat-days">~${p.days_to_crisis}d to crisis</span>
            <span class="ctail-pat-sep">·</span>
            <span class="ctail-pat-cat">${p.category.replace(/_/g, ' ')}</span>
          </div>
        </div>`;
    }).join('');
  }

  panel.classList.remove('hidden');
}

// ── Failure Cascade Graph ($graphLookup) ──────────────────────────
function renderCascade(cascade) {
  const panel  = document.getElementById('cascade-panel');
  const tabBtn = document.getElementById('tab-btn-escape');
  if (!panel || !cascade || !cascade.has_cascade) {
    return;
  }
  // The reset (runAnalysis) hides this panel; unhide it now that we have data.
  panel.classList.remove('hidden');
  if (tabBtn) tabBtn.classList.add('has-data');

  // Header badges
  const depthBadge = document.getElementById('casc-depth-badge');
  const daysBadge  = document.getElementById('casc-days-badge');
  if (depthBadge) depthBadge.textContent = `Depth: ${cascade.max_depth}`;
  if (daysBadge)  daysBadge.textContent  = `Worst case: ${cascade.worst_case_days}d`;

  // SVG flow diagram
  const graphContainer = document.getElementById('cascade-graph-container');
  if (graphContainer) graphContainer.innerHTML = buildCascadeFlowSvg(cascade);

  // Interventions (Cascade Intervention Optimizer)
  const intPanel = document.getElementById('casc-interventions');
  const intList  = document.getElementById('casc-int-list');
  const realInts = (cascade.interventions || []).filter(i => i.action && i.action !== 'monitor' && i.action !== 'reduce_risk');
  if (intPanel && intList && realInts.length > 0) {
    intList.innerHTML = realInts.map(iv => {
      const urgencyClass = iv.urgency === 'CRITICAL' ? 'casc-int-critical' : 'casc-int-warning';
      const daysText = iv.days_to_act ? `Act within ${iv.days_to_act}d` : '';
      return `
        <div class="casc-int-item ${urgencyClass}">
          <div class="casc-int-item-header">
            <span class="casc-int-urgency-badge">${iv.urgency}</span>
            <span class="casc-int-target">→ prevents cascade to <strong>${iv.cascade_pattern_name}</strong></span>
            <span class="casc-int-days-hint">${daysText}</span>
          </div>
          <p class="casc-int-message">${iv.message}</p>
        </div>`;
    }).join('');
    intPanel.classList.remove('hidden');
  } else if (intPanel) {
    intPanel.classList.add('hidden');
  }

  // Calibration note + Bayesian update summary
  const calibEl = document.getElementById('casc-calibration');
  if (calibEl) {
    const steps = cascade.cascade_steps || [];
    const updatedSteps = steps.filter(s =>
      s.observed_count > 0 &&
      Math.abs((s.initial_probability || s.transition_probability) - s.transition_probability) >= 0.01
    );
    let bayesNote = '';
    if (updatedSteps.length > 0) {
      const parts = updatedSteps.map(s => {
        const init = Math.round((s.initial_probability || s.transition_probability) * 100);
        const curr = Math.round(s.transition_probability * 100);
        return `${s.pattern_name}: ${init}%→${curr}% (${s.observed_count} cases)`;
      });
      bayesNote = ` · Bayesian updates: ${parts.join(', ')}`;
    }
    calibEl.textContent = (cascade.cascade_calibration || '') + bayesNote;
  }
  // Panel always visible inside its tab
}

// ── SVG Cascade Flow Diagram — $graphLookup visualised as a node-edge graph
function buildCascadeFlowSvg(cascade) {
  const steps    = (cascade.cascade_steps || []).slice(0, 3);
  const rootNode = {
    id: cascade.root_pattern_id,
    name: cascade.root_pattern_name,
    isRoot: true,
    survivalRate: cascade.root_survival_rate || 0,
    daysFromNow: 0,
    cumulativeProbability: 1.0,
  };
  const allNodes = [rootNode, ...steps];

  // Layout
  const W = 340, NODE_H = 96, EDGE_H = 54, MX = 12, MY = 10;
  const totalW  = W + MX * 2;
  const totalH  = allNodes.length * NODE_H + (allNodes.length - 1) * EDGE_H + MY * 2 +
                  ((cascade.cascade_steps || []).length > 3 ? 22 : 0);

  // SVG cascade is always rendered on a dark background panel
  const isDark = true;

  // Node class + inline text fill for guaranteed contrast in both themes
  const nc = (prob, isRoot) => isRoot ? 'cnr' : prob >= 60 ? 'cnd' : prob >= 35 ? 'cnw' : 'cnl';
  const nameFill  = isDark ? '#f1f5f9' : '#1e293b';
  const pidFill   = isDark ? '#cbd5e1' : '#475569';
  const statDanger = isDark ? '#fca5a5' : '#dc2626';
  const statWarn   = isDark ? '#fde68a' : '#b45309';
  const statSafe   = isDark ? '#6ee7b7' : '#059669';
  const daytxtRoot = isDark ? '#ddd6fe' : '#5b21b6';
  const daytxtDang = isDark ? '#fca5a5' : '#991b1b';
  const daytxtWarn = isDark ? '#fde68a' : '#92400e';
  const daytxtLow  = isDark ? '#cbd5e1' : '#374151';
  const trigFill   = isDark ? '#94a3b8' : '#475569';
  const edgeClr    = isDark ? 'rgba(148,163,184,0.5)' : 'rgba(71,85,105,0.4)';
  const arrClr     = isDark ? 'rgba(148,163,184,0.6)' : 'rgba(71,85,105,0.5)';
  const trigBg     = isDark ? 'rgba(15,23,42,0.75)' : 'rgba(255,255,255,0.9)';
  const trigBorder = isDark ? 'rgba(100,116,139,0.35)' : 'rgba(71,85,105,0.3)';
  const moreFill   = isDark ? '#64748b' : '#94a3b8';

  // Wrap pattern name across two lines at ≤26 chars
  const wrap = (name) => {
    if (name.length <= 26) return [name, null];
    const words = name.split(' ');
    let ln1 = '', cur = '';
    for (const w of words) {
      const t = cur ? cur + ' ' + w : w;
      if (t.length <= 26) { cur = t; }
      else if (!ln1) { ln1 = cur; cur = w; }
      else { cur += ' ' + w; break; }
    }
    if (!ln1) return [cur, null];
    const ln2 = cur.trim();
    return [ln1, ln2.length > 28 ? ln2.slice(0, 26) + '…' : ln2];
  };

  const esc = (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  const p = [];
  p.push(`<svg viewBox="0 0 ${totalW} ${totalH}" xmlns="http://www.w3.org/2000/svg" class="casc-flow-svg" role="img" aria-label="Failure Cascade Flow">`);
  p.push(`<defs><marker id="ca-inline" markerWidth="9" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0,9 3.5,0 7" fill="${arrClr}"/></marker></defs>`);

  for (let i = 0; i < allNodes.length; i++) {
    const nd   = allNodes[i];
    const y    = MY + i * (NODE_H + EDGE_H);
    const x    = MX;
    const prob = nd.isRoot ? 100 : Math.round((nd.cumulative_probability || 0) * 100);
    const cls  = nc(prob, nd.isRoot);
    const surv = Math.round(((nd.isRoot ? nd.survivalRate : nd.survival_rate) || 0) * 100);
    const pid  = esc(nd.id || nd.pattern_id || '');
    const [ln1, ln2] = wrap(nd.name || nd.pattern_name || '?');

    // Node background
    p.push(`<rect x="${x}" y="${y}" width="${W}" height="${NODE_H}" rx="11" class="${cls}-rect"/>`);

    // Pattern ID pill (top-left)
    if (pid) {
      p.push(`<rect x="${x+9}" y="${y+8}" width="52" height="17" rx="8" class="${cls}-pill"/>`);
      p.push(`<text x="${x+35}" y="${y+20}" text-anchor="middle" class="casc-pid" fill="${pidFill}">${pid}</text>`);
    }

    // Day / YOU ARE HERE badge (top-right)
    const dlbl = nd.isRoot ? 'YOU ARE HERE' : `+${nd.daysFromNow || nd.days_from_now}d`;
    const dpw  = nd.isRoot ? 96 : 68;
    const dtxt = cls === 'cnr' ? daytxtRoot : cls === 'cnd' ? daytxtDang : cls === 'cnw' ? daytxtWarn : daytxtLow;
    p.push(`<rect x="${x+W-dpw-8}" y="${y+8}" width="${dpw}" height="17" rx="8" class="${cls}-daypill"/>`);
    p.push(`<text x="${x+W-dpw/2-8}" y="${y+20}" text-anchor="middle" class="${cls}-daytxt" fill="${dtxt}">${esc(dlbl)}</text>`);

    // Pattern name (1–2 lines) — always light in dark, dark in light
    const ny = ln2 ? y+44 : y+51;
    p.push(`<text x="${x+W/2}" y="${ny}" text-anchor="middle" class="${cls}-name" fill="${nameFill}" font-weight="700">${esc(ln1)}</text>`);
    if (ln2) p.push(`<text x="${x+W/2}" y="${y+59}" text-anchor="middle" class="${cls}-name" fill="${nameFill}" font-weight="700">${esc(ln2)}</text>`);

    // Survival + probability stats
    const statFill = surv < 15 ? statDanger : surv < 30 ? statWarn : statSafe;
    const stxt = nd.isRoot
      ? `${surv}% survival rate`
      : `${surv}% survive  ·  ${prob}% cumulative probability`;
    p.push(`<text x="${x+W/2}" y="${(ln2?y+79:y+74)}" text-anchor="middle" fill="${statFill}" font-size="10" font-weight="600">${esc(stxt)}</text>`);

    // Edge to next node (dashed line + arrowhead + trigger label)
    if (i < allNodes.length - 1) {
      const step = steps[i];
      const ax   = x + W / 2;
      const ay1  = y + NODE_H + 3;
      const ay2  = y + NODE_H + EDGE_H - 12;

      p.push(`<line x1="${ax}" y1="${ay1}" x2="${ax}" y2="${ay2}" stroke="${edgeClr}" stroke-width="2" stroke-dasharray="5 3" marker-end="url(#ca-inline)"/>`);

      if (step && step.trigger_metric) {
        const tstr = `${step.trigger_metric} ${step.trigger_direction === 'above' ? '>' : '<'} ${step.trigger_threshold}`;
        const tw   = Math.min(tstr.length * 7.0 + 20, W - 30);
        p.push(`<rect x="${x+W/2-tw/2}" y="${ay1+8}" width="${tw}" height="17" rx="4" fill="${trigBg}" stroke="${trigBorder}" stroke-width="1"/>`);
        p.push(`<text x="${ax}" y="${ay1+20}" text-anchor="middle" fill="${trigFill}" font-size="9" font-family="monospace">${esc(tstr)}</text>`);
      }

      if (step && step.observed_count > 0) {
        const initPct = Math.round((step.initial_probability || step.transition_probability) * 100);
        const currPct = Math.round(step.transition_probability * 100);
        const updated = initPct !== currPct;
        const obsLabel = updated
          ? `${initPct}%→${currPct}% (${step.observed_count} cases)`
          : `${step.observed_count} observed`;
        const pillW = Math.min(obsLabel.length * 6.5 + 16, 140);
        p.push(`<rect x="${x+W-pillW-4}" y="${ay1+8}" width="${pillW}" height="17" rx="8" class="casc-obs-pill"/>`);
        p.push(`<text x="${x+W-pillW/2-4}" y="${ay1+20}" text-anchor="middle" fill="${trigFill}" font-size="9">${obsLabel}</text>`);
      }
    }
  }

  if ((cascade.cascade_steps || []).length > 3) {
    const fy = MY + allNodes.length * (NODE_H + EDGE_H) + 4;
    p.push(`<text x="${MX+W/2}" y="${fy}" text-anchor="middle" fill="${moreFill}" font-size="11">+ ${cascade.cascade_steps.length - 3} more cascade steps…</text>`);
  }

  p.push('</svg>');
  return p.join('');
}

// ── Cohort Percentile Intelligence ($bucket + $facet) ────────────
async function runCohortIntelligence() {
  const industry = document.getElementById('cohort-industry')?.value.trim() || 'B2B SaaS';
  const score    = parseInt(document.getElementById('cohort-score')?.value) || 50;
  const month    = parseInt(document.getElementById('cohort-month')?.value) || 12;

  const btnText   = document.getElementById('cohort-btn-text');
  const spinner   = document.getElementById('cohort-spinner');
  const resultEl  = document.getElementById('cohort-result');
  if (btnText) btnText.classList.add('hidden');
  if (spinner) spinner.classList.remove('hidden');
  if (resultEl) resultEl.classList.add('hidden');

  try {
    const params = new URLSearchParams({ industry, oracle_score: score, current_month: month });
    const res = await fetch(`${API}/api/cascade/cohort/intelligence?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderCohortResult(data);
  } catch (err) {
    console.error('[cohort]', err);
    alert(`Cohort analysis failed: ${err.message}`);
  } finally {
    if (btnText) btnText.classList.remove('hidden');
    if (spinner) spinner.classList.add('hidden');
  }
}

function renderCohortResult(data) {
  const resultEl = document.getElementById('cohort-result');
  if (!resultEl) return;

  // Pre-fill inputs from response (sync if auto-triggered from analysis)
  const industryEl = document.getElementById('cohort-industry');
  const scoreEl    = document.getElementById('cohort-score');
  const monthEl    = document.getElementById('cohort-month');
  if (industryEl && data.industry) industryEl.value = data.industry;
  if (scoreEl    && data.oracle_score != null) scoreEl.value = data.oracle_score;
  if (monthEl    && data.current_month != null) monthEl.value = data.current_month;

  // Percentile card
  const percNum     = document.getElementById('cohort-perc-number');
  const percMsg     = document.getElementById('cohort-perc-message');
  const percCard    = document.getElementById('cohort-percentile-card');
  const sizeBadge   = document.getElementById('cohort-size-badge');
  const alertRate   = document.getElementById('cohort-alert-rate');

  const pct = data.percentile;
  const percLabel = document.getElementById('cohort-perc-label');
  if (pct != null) {
    // Correct ordinal suffix (1st, 2nd, 3rd, 4th, 11th, 12th, 13th, 33rd…)
    const suffix = (pct % 100 >= 11 && pct % 100 <= 13) ? 'th'
      : pct % 10 === 1 ? 'st' : pct % 10 === 2 ? 'nd' : pct % 10 === 3 ? 'rd' : 'th';
    if (percNum)   percNum.textContent   = pct;
    if (percLabel) percLabel.textContent = suffix + ' percentile';
  } else {
    if (percNum)   percNum.textContent   = '—';
    if (percLabel) percLabel.textContent = 'th percentile';
  }
  if (percMsg)  percMsg.textContent  = data.percentile_message || '—';
  if (sizeBadge) sizeBadge.textContent = `${data.total_in_cohort || 0} in cohort`;
  if (alertRate) alertRate.textContent = data.cohort_alert_rate_pct != null
    ? `${data.cohort_alert_rate_pct}% at risk` : '— at risk';

  // Color the percentile card by severity
  const sevMap = { critical: '#ef4444', warning: '#f59e0b', watch: '#f59e0b', healthy: '#10b981', strong: '#10b981', unknown: '#6b7280' };
  const sevColor = sevMap[data.percentile_severity] || '#6b7280';
  if (percCard) {
    percCard.style.borderLeftColor = sevColor;
    const numEl = percCard.querySelector('.cohort-perc-number');
    if (numEl) numEl.style.color = sevColor;
  }

  // Stats grid
  const statsGrid = document.getElementById('cohort-stats-grid');
  if (statsGrid) {
    statsGrid.innerHTML = `
      <div class="cohort-stat-item">
        <div class="cohort-stat-val">${data.cohort_avg_oracle_score ?? '—'}</div>
        <div class="cohort-stat-label">Cohort Avg Oracle Score</div>
      </div>
      <div class="cohort-stat-item">
        <div class="cohort-stat-val">${data.cohort_avg_churn_pct != null ? data.cohort_avg_churn_pct + '%' : '—'}</div>
        <div class="cohort-stat-label">Cohort Avg Churn</div>
      </div>
      <div class="cohort-stat-item">
        <div class="cohort-stat-val">${data.cohort_avg_runway_months != null ? data.cohort_avg_runway_months + 'mo' : '—'}</div>
        <div class="cohort-stat-label">Cohort Avg Runway</div>
      </div>
      <div class="cohort-stat-item">
        <div class="cohort-stat-val">${data.cohort_alert_rate_pct != null ? data.cohort_alert_rate_pct + '%' : '—'}</div>
        <div class="cohort-stat-label">Cohort At-Risk Rate</div>
      </div>`;
  }

  // Top failure patterns
  const patsRow = document.getElementById('cohort-patterns-row');
  if (patsRow && data.top_failure_patterns?.length) {
    patsRow.innerHTML = `
      <div class="cohort-pats-header">Top Failure Patterns in Your Cohort</div>
      <div class="cohort-pats-list">
        ${data.top_failure_patterns.map(p => `
          <div class="cohort-pat-item">
            <span class="cohort-pat-name">${p.pattern_name}</span>
            <span class="cohort-pat-freq">${p.frequency}×</span>
          </div>`).join('')}
      </div>`;
    patsRow.classList.remove('hidden');
  } else if (patsRow) {
    patsRow.classList.add('hidden');
  }

  // Survivor stats
  const survivorCard = document.getElementById('cohort-survivor-card');
  const survivorStats = document.getElementById('cohort-survivor-stats');
  if (survivorCard && survivorStats && data.survivor_avg_score != null) {
    survivorStats.innerHTML = `
      <div class="cohort-stat-item cohort-surv-stat">
        <div class="cohort-stat-val cohort-surv-val">${data.survivor_avg_score}</div>
        <div class="cohort-stat-label">Survivor Avg Score</div>
      </div>
      <div class="cohort-stat-item cohort-surv-stat">
        <div class="cohort-stat-val cohort-surv-val">${data.survivor_avg_churn_pct}%</div>
        <div class="cohort-stat-label">Survivor Avg Churn</div>
      </div>
      <div class="cohort-stat-item cohort-surv-stat">
        <div class="cohort-stat-val cohort-surv-val">${data.survivor_avg_runway_months}mo</div>
        <div class="cohort-stat-label">Survivor Avg Runway</div>
      </div>
      <div class="cohort-stat-item cohort-surv-stat">
        <div class="cohort-stat-val cohort-surv-val">${data.survivor_count}</div>
        <div class="cohort-stat-label">Survivors in Cohort</div>
      </div>`;
    survivorCard.classList.remove('hidden');
  } else if (survivorCard) {
    survivorCard.classList.add('hidden');
  }

  // Score distribution chart ($bucket aggregation visualization)
  if (data.score_distribution?.length > 0) {
    renderCohortDistChart(data.score_distribution, data.oracle_score);
  }

  // Methodology footnote
  const methEl = document.getElementById('cohort-methodology');
  if (methEl) methEl.textContent = data.methodology || '';

  resultEl.classList.remove('hidden');
}

// Retain reference so we can destroy before re-rendering
let _cohortChart = null;

function renderCohortDistChart(buckets, userScore) {
  const wrap   = document.getElementById('cohort-dist-wrap');
  const canvas = document.getElementById('cohort-dist-canvas');
  if (!wrap || !canvas || !buckets.length) return;

  // Destroy previous chart instance if it exists
  if (_cohortChart) { _cohortChart.destroy(); _cohortChart = null; }

  const LABELS = ['0–20', '20–40', '40–60', '60–80', '80–100'];
  const STARTS = [0, 20, 40, 60, 80];

  // Map buckets to ordered arrays
  const counts = STARTS.map(s => {
    const b = buckets.find(x => (typeof x._id === 'number' ? x._id : -1) === s);
    return b ? (b.count || 0) : 0;
  });

  // Determine which bucket the user is in
  const userBucketIdx = userScore != null
    ? Math.min(Math.floor(userScore / 20), 4)
    : -1;

  // Bar colours: red → amber → amber → green → green, highlighted bucket gets opacity 1
  const COLORS_BG = [
    'rgba(239,68,68,0.55)', 'rgba(245,158,11,0.55)', 'rgba(245,158,11,0.45)',
    'rgba(16,185,129,0.45)', 'rgba(16,185,129,0.55)',
  ];
  const COLORS_BORDER = [
    'rgba(239,68,68,1)', 'rgba(245,158,11,1)', 'rgba(245,158,11,1)',
    'rgba(16,185,129,1)', 'rgba(16,185,129,1)',
  ];
  const bgColors     = COLORS_BG.map((c, i) => i === userBucketIdx ? c.replace('0.55','0.85').replace('0.45','0.85') : c);
  const borderColors = COLORS_BORDER;
  const borderWidths = COLORS_BORDER.map((_, i) => i === userBucketIdx ? 2.5 : 1.5);

  // YOU ARE HERE annotation plugin
  const youAreHerePlugin = {
    id: 'youAreHere',
    afterDraw(chart) {
      if (userBucketIdx < 0) return;
      const { ctx, chartArea, scales } = chart;
      const meta = chart.getDatasetMeta(0);
      const bar  = meta.data[userBucketIdx];
      if (!bar) return;
      const x = bar.x;
      ctx.save();
      ctx.strokeStyle = 'rgba(124,58,237,0.9)';
      ctx.lineWidth   = 2;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(x, chartArea.top);
      ctx.lineTo(x, chartArea.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle    = 'rgba(124,58,237,0.9)';
      ctx.font         = 'bold 9px Inter, sans-serif';
      ctx.textAlign    = 'center';
      ctx.fillText('YOU', x, chartArea.top + 10);
      ctx.restore();
    },
  };

  _cohortChart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: LABELS,
      datasets: [{
        label: 'Startups in cohort',
        data: counts,
        backgroundColor: bgColors,
        borderColor: borderColors,
        borderWidth: borderWidths,
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => `Oracle Score ${LABELS[items[0].dataIndex]}`,
            label: (item) => {
              const suffix = item.dataIndex === userBucketIdx ? '  ← YOU ARE HERE' : '';
              return `${item.raw} startup${item.raw !== 1 ? 's' : ''}${suffix}`;
            },
          },
        },
      },
      scales: {
        x: {
          grid:  { display: false },
          ticks: { font: { size: 10 }, color: 'rgba(107,114,128,0.9)' },
        },
        y: {
          beginAtZero: true,
          grid:  { color: 'rgba(107,114,128,0.12)' },
          ticks: { stepSize: 1, font: { size: 10 }, color: 'rgba(107,114,128,0.9)' },
        },
      },
    },
    plugins: [youAreHerePlugin],
  });

  wrap.classList.remove('hidden');
}

// ── Oracle Pre-Mortem ─────────────────────────────────────────────
async function runPreMortem() {
  const decisionText = document.getElementById('pm-decision-text')?.value.trim();
  if (!decisionText || decisionText.length < 10) {
    alert('Please describe a strategic decision (min 10 characters).');
    return;
  }
  if (!_lastPayload) {
    alert('Run an analysis first — the Pre-Mortem uses your last analysis metrics as baseline.');
    switchTab('tab-dashboard');
    return;
  }

  const btnText    = document.getElementById('pm-btn-text');
  const btnSpinner = document.getElementById('pm-btn-spinner');
  const resultEl   = document.getElementById('pm-result');
  btnText.classList.add('hidden');
  btnSpinner.classList.remove('hidden');
  resultEl.classList.add('hidden');

  try {
    const res = await fetch(`${API}/api/audit/pre-mortem`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        startup_name: _lastPayload.startup_name || 'Your Startup',
        decision: decisionText,
        metrics: _lastPayload,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    renderPreMortemResult(data);
  } catch (err) {
    resultEl.innerHTML = `<div class="pm-error">Pre-Mortem failed: ${err.message}</div>`;
    resultEl.classList.remove('hidden');
    resultEl.scrollIntoView({ behavior: 'smooth' });
  } finally {
    btnText.classList.remove('hidden');
    btnSpinner.classList.add('hidden');
  }
}

function renderPreMortemResult(data) {
  const resultEl  = document.getElementById('pm-result');
  const verdictEl = document.getElementById('pm-verdict');
  const trajEl    = document.getElementById('pm-trajectory');
  const risksEl   = document.getElementById('pm-risks-opps');
  const patRiskEl = document.getElementById('pm-pattern-risk');
  if (!resultEl) return;

  // Verdict
  if (verdictEl) {
    const isPos  = data.verdict?.startsWith('POSITIVE');
    const isHigh = data.verdict?.startsWith('HIGH RISK');
    const isCaut = data.verdict?.startsWith('CAUTION');
    const vcls   = isHigh ? 'pm-verdict-high' : isCaut ? 'pm-verdict-caution' : isPos ? 'pm-verdict-positive' : 'pm-verdict-neutral';
    verdictEl.className = `pm-verdict ${vcls}`;
    verdictEl.textContent = data.verdict || '';
  }

  // Trajectory cards (+1, +3, +6)
  if (trajEl && data.trajectory?.length) {
    trajEl.innerHTML = `
      <div class="pm-traj-label">Oracle Score Trajectory</div>
      <div class="pm-traj-cards">
        ${data.trajectory.map(h => {
          const scoreColor = h.oracle_score >= 60 ? 'var(--safe)' : h.oracle_score >= 40 ? 'var(--warning)' : 'var(--danger)';
          const delta = h.oracle_score - (data.current_score || 50);
          const deltaStr = delta > 0 ? `+${delta}` : String(delta);
          const deltaCls = delta > 0 ? 'pm-delta-pos' : delta < 0 ? 'pm-delta-neg' : 'pm-delta-flat';
          return `
            <div class="pm-traj-card">
              <div class="pm-traj-month">Month +${h.month_offset}</div>
              <div class="pm-traj-score" style="color:${scoreColor}">${h.oracle_score}</div>
              <div class="pm-traj-band">${(h.score_band || '').toUpperCase()}</div>
              <div class="pm-traj-delta ${deltaCls}">${deltaStr} vs now</div>
            </div>`;
        }).join('')}
      </div>
      ${typeof data.current_score === 'number' ? `<div class="pm-current-score">Baseline Oracle Score: <strong>${data.current_score}</strong></div>` : ''}
    `;
  }

  // Key risks and opportunities
  if (risksEl) {
    const risks = data.key_risks || [];
    const opps  = data.key_opportunities || [];
    risksEl.innerHTML = `
      ${risks.length ? `
        <div class="pm-ro-block">
          <div class="pm-ro-label pm-ro-risk">Key Risks</div>
          <ul class="pm-ro-list">${risks.map(r => `<li>${r}</li>`).join('')}</ul>
        </div>` : ''}
      ${opps.length ? `
        <div class="pm-ro-block">
          <div class="pm-ro-label pm-ro-opp">Opportunities</div>
          <ul class="pm-ro-list">${opps.map(o => `<li>${o}</li>`).join('')}</ul>
        </div>` : ''}
    `;
  }

  // Month-6 pattern risk
  if (patRiskEl) {
    const pr = data.month6_pattern_risk;
    if (pr && pr.pattern_name) {
      const conf = Math.round((pr.confidence || 0) * 100);
      patRiskEl.innerHTML = `
        <div class="pm-pr-header">Month-6 Pattern Risk</div>
        <div class="pm-pr-body">
          <span class="pm-pr-name">${pr.pattern_name}</span>
          <span class="pm-pr-conf">${conf}% match</span>
          <span class="pm-pr-days">~${pr.days_to_crisis || 90}d to crisis if triggered</span>
        </div>
        <p class="pm-pr-note">${pr.match_reasoning || ''}</p>
      `;
      patRiskEl.classList.remove('hidden');
    } else {
      patRiskEl.classList.add('hidden');
    }
  }

  resultEl.classList.remove('hidden');
  resultEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function toggleWelcomeBanner() {
  const banner = document.getElementById('welcome-banner');
  const btn = document.getElementById('wb-toggle-btn');
  if (!banner || !btn) return;
  
  const isCollapsed = banner.classList.toggle('collapsed');
  btn.innerHTML = isCollapsed
    ? '<span class="wb-toggle-text">Show Guide</span> ▾'
    : '<span class="wb-toggle-text">Hide Guide</span> ▴';
}
