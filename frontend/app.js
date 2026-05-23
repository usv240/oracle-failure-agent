const API = '';  // Same origin

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
    startup_name: 'Quibi (April 2020)',
    current_month: 4,
    mrr: 420000,
    mrr_growth_rate: 0.04,
    churn_rate: 0.22,
    burn_rate: 8500000,
    runway_months: 14,
    headcount: 185,
    nps: 8,
    cac: 48000,
    ltv: 12000,
    industry: 'Consumer',
  },
  wework: {
    startup_name: 'WeWork (Q3 2019)',
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
    if (el) el.value = d[key];
  });
}

function toggleGlossary() {
  const body = document.getElementById('glossary-body');
  const toggle = document.getElementById('glossary-toggle');
  body.classList.toggle('hidden');
  toggle.textContent = body.classList.contains('hidden') ? 'Show ▾' : 'Hide ▴';
}

// ── Theme Toggle ─────────────────────────────────────────────────
function toggleTheme() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const next = isDark ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('oracle_theme', next);
  document.getElementById('theme-btn').innerHTML = next === 'dark' ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>' : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>';
}

// Sync button icon on load
window.addEventListener('DOMContentLoaded', () => {
  const theme = localStorage.getItem('oracle_theme') || 'light';
  document.documentElement.setAttribute('data-theme', theme);
  const btn = document.getElementById('theme-btn');
  if (btn) btn.innerHTML = theme === 'dark' ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>' : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>';

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

async function runAnalysis() {
  const btnText    = document.getElementById('btn-text');
  const btnSpinner = document.getElementById('btn-spinner');
  btnText.classList.add('hidden');
  btnSpinner.classList.remove('hidden');

  hide('alert-section');
  hide('safe-section');
  hide('early-warning-banner');
  hide('risk-banner');
  hide('challenger-panel');
  hide('accuracy-showcase');
  hide('alert-lib-link');
  hide('oracle-score-card');
  hide('recovery-card');

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

  function addTermLine(icon, msg, cls = '') {
    const p = document.createElement('div');
    p.className = 'terminal-line' + (cls ? ' ' + cls : '');
    const highlight = (s) => s.replace(/(MongoDB[^,.<\s]*|Gemini[^,.<\s]*|MCP|Vector Search|ADK)/g,
      '<span class="highlight">$1</span>');
    p.innerHTML = `${icon} ${highlight(msg)}`;
    termBody.appendChild(p);
    termBody.scrollTop = termBody.scrollHeight;
  }

  addTermLine('>', 'Starting Oracle pipeline — MongoDB Voyage AI (embed) → Atlas Vector Search + BM25 RRF → MongoDB MCP → Gemini 3 scoring...');

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
              message: evt.message,
              oracle_score: evt.oracle_score,
              score_band: evt.score_band,
              recovery_scenario: evt.recovery_scenario,
            };
          } else if (evt.type === 'safe') {
            addTermLine('', evt.message, 'terminal-safe');
            finalData = {
              alert: false,
              startup_name: payload.startup_name,
              message: evt.message,
              oracle_score: evt.oracle_score,
              score_band: evt.score_band,
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
    document.getElementById('tp-label').textContent =
      `View agent execution log (${lineCount} steps)`;
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

  document.getElementById('chp-icon').textContent  = isConfirm ? '✅' : '⚡';
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
function renderOracleScore(score, band) {
  const card = document.getElementById('oracle-score-card');
  if (!card || typeof score !== 'number') return;

  const valEl  = document.getElementById('osc-value');
  const bandEl = document.getElementById('osc-band');
  const barEl  = document.getElementById('osc-bar-fill');
  const tipEl  = document.getElementById('osc-tip');

  // Band labels and tips come from backend's score_band field
  const bandText = {
    strong:   'STRONG · Healthy trajectory',
    watch:    'WATCH · Monitor weekly',
    warning:  'WARNING · Course correct now',
    critical: 'CRITICAL · Take action this week',
  }[band] || band.toUpperCase();

  if (valEl)  { valEl.textContent = score; valEl.dataset.band = band; }
  if (bandEl) { bandEl.textContent = bandText; bandEl.dataset.band = band; }
  if (barEl)  { barEl.dataset.band = band; barEl.style.width = '0%'; setTimeout(() => barEl.style.width = `${score}%`, 80); }
  if (tipEl)  { tipEl.textContent = `Composite of all 11 metrics + pattern match. ${score}/100.`; }

  card.dataset.band = band;
  card.classList.remove('hidden');
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
  if (subEl)   subEl.textContent   = `Match confidence would drop to ${Math.round((scenario.confidence || 0) * 100)}%`;
  if (listEl) {
    listEl.innerHTML = scenario.improvements.map(s => `<li>${s}</li>`).join('');
  }
  card.classList.remove('hidden');
}

function renderResult(data) {
  // Render Oracle Score on both paths (alert and safe)
  if (typeof data.oracle_score === 'number') {
    renderOracleScore(data.oracle_score, data.score_band || 'watch');
  }

  if (!data.alert) {
    hide('risk-banner');
    show('safe-section');
    return;
  }

  switchResultTab('result-tab-overview');

  // Recovery scenario only meaningful on alert
  if (data.recovery_scenario) renderRecovery(data.recovery_scenario);

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

  show('alert-section');
  document.getElementById('alert-section').scrollIntoView({ behavior: 'smooth' });
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

  const md = `#FAILURE PATTERN ALERT
**Pattern:** ${p.pattern_name} (${p.pattern_id})
**Pattern Match Score:** ${Math.round(p.confidence * 100)}%
**Startup:** ${pl.startup_name} | Month ${pl.current_month}
**Generated:** ${new Date().toLocaleString()}

---

## What This Pattern Means
${p.narrative}

---

## Warning Signals
| Signal | Status | First Detectable |
|--------|--------|-----------------|
${signals || '| No signals detected | — | — |'}

---

## Your Metrics
| Metric | Value |
|--------|-------|
| MRR | $${pl.mrr.toLocaleString()} |
| Monthly Growth | ${(pl.mrr_growth_rate*100).toFixed(1)}% |
| Churn Rate | ${(pl.churn_rate*100).toFixed(1)}% |
| Burn Rate | $${pl.burn_rate.toLocaleString()}/mo |
| Runway | ${pl.runway_months} months |
| NPS | ${pl.nps} |
| LTV:CAC | ${pl.cac > 0 ? (pl.ltv/pl.cac).toFixed(1) : 'N/A'}x |

---

## Historical Outcomes (${total.toLocaleString()} cases)
- **${failPct}% failed** within ${p.days_to_crisis} days
- **${survPct}% survived** (${p.survival_count} companies)

---

## Survival Playbook
${playbook}

---

## Companies That Matched This Pattern
| Company | Outcome | Detail |
|---------|---------|--------|
${failures}

---
*Generated by The Failure Oracle*
`;

  const blob = new Blob([md], { type: 'text/markdown' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `oracle-report-${pl.startup_name.replace(/\s+/g,'-').toLowerCase()}.md`;
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

  try {
    const res  = await fetch(`${API}/api/audit/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        decision,
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

  let patternCard = '';
  if (linked) {
    const totalCases = (linked.survival_count || 0) + (linked.failure_count || 0);
    const computedSurvRate = linked.survival_rate != null ? linked.survival_rate : (totalCases > 0 ? (linked.survival_count / totalCases) : 0);
    const survRatePct = Math.round(computedSurvRate * 100);
    const survClass = survRatePct < 25 ? 'apc-surv-low' : 'apc-surv-ok';
    const catLabel = CAT_LABELS[linked.category] || (linked.category || '').replace(/_/g, ' ');

    patternCard = `
      <div class="audit-pattern-card" onclick="jumpToPattern('${linked.pattern_id}')" style="cursor:pointer" title="Click to view details in library">
        <div class="apc-label">Closest matching failure pattern ↗</div>
        <div class="apc-name">${linked.name}</div>
        <div class="apc-meta">
          <span class="apc-id">${linked.pattern_id}</span>
          <span class="apc-cat">${catLabel}</span>
          <span class="apc-surv ${survClass}">
            ${survRatePct}% survival rate
          </span>
        </div>
        ${linked.famous_failures && linked.famous_failures.length > 0
          ? `<div class="apc-example">"${linked.famous_failures[0].company} — ${linked.famous_failures[0].detail}"</div>`
          : ''}
      </div>
    `;
  }

  el.innerHTML = `
    <div class="audit-risk ${cls}">
      ${riskIcon(data.risk_level)} <strong>${data.risk_level} RISK</strong>
    </div>
    ${patternCard}
    <div class="audit-section">
      <div class="audit-section-label">Key differentiator</div>
      <p class="audit-differentiator">${data.key_differentiator}</p>
    </div>
    <div class="audit-section">
      <div class="audit-section-label">Recommendation</div>
      <p class="audit-recommendation">${data.recommendation}</p>
    </div>
    ${data.rationale ? `
    <div class="audit-section">
      <div class="audit-section-label">Analysis</div>
      <p class="audit-rationale">${data.rationale}</p>
    </div>` : ''}
    <p class="audit-footer">Evaluated against 100 documented failure patterns</p>
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

function filterPatterns(category) {
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

  const contentArea = document.querySelector('.content-area');
  if (contentArea) contentArea.scrollTop = 0;
}

// Result Sub-tab Switcher
function switchResultTab(tabId) {
  document.querySelectorAll('.result-tab-content').forEach(el => el.classList.add('hidden'));
  const targetTab = document.getElementById(tabId);
  if (targetTab) targetTab.classList.remove('hidden');

  document.querySelectorAll('.result-tab-btn').forEach(btn => {
    if (btn.getAttribute('onclick')?.includes(tabId)) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
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

  const rows = snapshots.slice(0, 6).map((s, i) => {
    const d = new Date(s.date);
    const dateStr = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const scoreStr = s.alert ? `<span class="hs-score hs-danger">${Math.round(s.match_score * 100)}% — ${s.pattern_name || 'Risk detected'}</span>`
                             : `<span class="hs-score hs-safe">No pattern</span>`;
    const trend = i < snapshots.length - 1
      ? (s.match_score > snapshots[i + 1].match_score ? '↑' : s.match_score < snapshots[i + 1].match_score ? '↓' : '→')
      : '';
    const trendCls = trend === '↑' ? 'hs-up' : trend === '↓' ? 'hs-down' : 'hs-flat';
    return `<div class="hs-row">
      <span class="hs-date">${dateStr}</span>
      <span class="hs-name">${s.startup_name}</span>
      ${scoreStr}
      <span class="hs-trend ${trendCls}">${trend}</span>
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

  const labels  = snapshots.map(s => new Date(s.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
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

  summaryEl.innerHTML = `
    <div class="pf-sum-stat"><div class="pf-sum-num">${data.total}</div><div class="pf-sum-label">Total</div></div>
    <div class="pf-sum-stat"><div class="pf-sum-num pf-critical">${data.critical}</div><div class="pf-sum-label">Critical</div></div>
    <div class="pf-sum-stat"><div class="pf-sum-num pf-high">${data.high_risk}</div><div class="pf-sum-label">High Risk</div></div>
    <div class="pf-sum-stat"><div class="pf-sum-num pf-moderate">${data.moderate}</div><div class="pf-sum-label">Moderate</div></div>
    <div class="pf-sum-stat"><div class="pf-sum-num pf-safe">${data.safe}</div><div class="pf-sum-label">Safe</div></div>
  `;

  gridEl.innerHTML = data.companies.map((c, i) => {
    const pct      = Math.round(c.confidence * 100);
    const chipCls  = `pf-chip-${c.risk_level.toLowerCase()}`;
    const days     = c.days_to_crisis ? `~${c.days_to_crisis}d to crisis` : '';
    const pattern  = c.pattern_name ? `<span class="pf-pattern">${c.pattern_name}</span>` : '';
    const reason   = c.match_reasoning ? `<div class="pf-reasoning">${c.match_reasoning}</div>` : '';
    return `
      <div class="pf-company-row">
        <span class="pf-rank">#${i + 1}</span>
        <span class="pf-name">${c.startup_name}</span>
        ${pattern}
        <span class="pf-risk-chip ${chipCls}">${c.risk_level} ${pct > 0 ? pct + '%' : ''}</span>
        <span class="pf-days">${days}</span>
        ${reason}
      </div>`;
  }).join('');
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
      const pct = Math.max(0, Math.min(100, (runway / 24.0) * 100)); // higher is better
      runwayBar.style.width = `${pct}%`;
      runwayBar.className = 'lm-bar-fill ' + (runway >= 18 ? 'healthy' : (runway >= 9 ? 'warning' : 'danger'));
    }
  } else {
    runwayEl.textContent = '--';
    runwayEl.className = 'lm-value';
    if (runwayBar) runwayBar.style.width = '0%';
  }
}

// Hook into fillDemo
const originalFillDemo = fillDemo;
fillDemo = function(preset) {
  originalFillDemo(preset);
  updateLiveMetrics();
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
