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
      if (isNaN(v)) { badge.classList.add('hidden'); return; }
      const status = getBenchmarkStatus(field, v);
      badge.classList.remove('hidden', 'bench-good', 'bench-warn', 'bench-bad');
      badge.classList.add(`bench-${status}`);
      const icons = { good: '✅', warn: '⚠️', bad: '🔴' };
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

// ── URL Param Loading (for Share feature) ───────────────────────
window.addEventListener('load', () => {
  const params = new URLSearchParams(window.location.search);
  const fields = ['startup_name','current_month','mrr','mrr_growth_rate',
                  'churn_rate','burn_rate','runway_months','headcount',
                  'nps','cac','ltv','industry'];
  let loaded = false;
  fields.forEach(f => {
    const v = params.get(f);
    if (v) { const el = document.getElementById(f); if (el) { el.value = v; loaded = true; } }
  });
  if (loaded) setTimeout(() => runAnalysis(), 400);
  loadPatternLibrary();
  attachLiveIndicators();
});

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

  try {
    const fetchPromise = fetch(`${API}/api/metrics/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(r => r.json());

    // Terminal simulation
    const terminal = document.getElementById('agent-terminal');
    const termBody = document.getElementById('terminal-body');
    terminal.classList.remove('hidden');
    termBody.innerHTML = '';
    const lines = [
      `> Initializing Google ADK Agent...`,
      `> Translating metrics to semantic vector space...`,
      `> Querying <span class="highlight">MongoDB Atlas Vector Search</span> for historical matches...`,
      `> Passing candidates to <span class="highlight">Gemini 2.5 Flash (Vertex AI)</span>...`,
      `> ⚡ Analyzing risk thresholds and retrieving survival playbooks...`,
    ];
    for (let i = 0; i < lines.length; i++) {
      const p = document.createElement('div');
      p.className = 'terminal-line';
      p.innerHTML = lines[i];
      termBody.appendChild(p);
      await new Promise(r => setTimeout(r, 600 + Math.random() * 200));
    }

    const data = await fetchPromise;
    const finalP = document.createElement('div');
    finalP.className = 'terminal-line';
    finalP.innerHTML = data.alert
      ? `> ⚠️ Pattern match found at <span class="highlight">${Math.round((data.pattern?.confidence||0)*100)}% confidence</span>. Generating alert...`
      : `> ✅ No dangerous patterns detected. Metrics look healthy.`;
    termBody.appendChild(finalP);
    await new Promise(r => setTimeout(r, 500));
    terminal.classList.add('hidden');

    _lastResult = data;
    renderResult(data);
  } catch (err) {
    alert('Error connecting to Oracle API. Is the server running?');
    console.error(err);
  } finally {
    btnText.classList.remove('hidden');
    btnSpinner.classList.add('hidden');
  }
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
function renderResult(data) {
  if (!data.alert) {
    show('safe-section');
    return;
  }

  const p = data.pattern;
  const pct = Math.round(p.confidence * 100);

  // Header
  setText('alert-title', `⚠️ ${p.pattern_name}`);

  // 2. Confidence bar — animate from 0 + 8. color coding
  const bar = document.getElementById('conf-bar');
  bar.style.width = '0%';
  bar.className = 'bar-fill ' + (pct >= 85 ? 'bar-danger' : pct >= 70 ? 'bar-warning' : 'bar-safe');
  setTimeout(() => { bar.style.width = `${pct}%`; }, 80);

  // Confidence pct — count up
  const confEl = document.getElementById('conf-pct');
  confEl.textContent = '0%';
  setTimeout(() => animateCounter(confEl, pct, '%'), 80);

  // Pattern ID badge
  setText('alert-pattern-id', p.pattern_id);

  // Narrative
  setText('alert-narrative', p.narrative);

  // Metric match table (why it matched)
  const pl = _lastPayload;
  const ltvCac = pl.cac > 0 ? (pl.ltv / pl.cac).toFixed(1) : 'N/A';
  const burnMult = (pl.mrr * pl.mrr_growth_rate) > 0
    ? (pl.burn_rate / (pl.mrr * pl.mrr_growth_rate)).toFixed(1) : '∞';
  const matchRows = [
    { metric: 'Monthly Churn',    yours: `${(pl.churn_rate*100).toFixed(1)}%`,    healthy: '<5%',    status: pl.churn_rate > 0.08 ? 'bad' : pl.churn_rate > 0.05 ? 'warn' : 'good' },
    { metric: 'MRR Growth',       yours: `${(pl.mrr_growth_rate*100).toFixed(1)}%`, healthy: '>15%', status: pl.mrr_growth_rate < 0.08 ? 'bad' : pl.mrr_growth_rate < 0.15 ? 'warn' : 'good' },
    { metric: 'NPS',              yours: `${pl.nps}`,      healthy: '>50',  status: pl.nps < 30 ? 'bad' : pl.nps < 50 ? 'warn' : 'good' },
    { metric: 'Runway',           yours: `${pl.runway_months}mo`,  healthy: '>18mo', status: pl.runway_months < 9 ? 'bad' : pl.runway_months < 18 ? 'warn' : 'good' },
    { metric: 'LTV:CAC',          yours: `${ltvCac}x`,    healthy: '>3x',  status: parseFloat(ltvCac) < 1 ? 'bad' : parseFloat(ltvCac) < 3 ? 'warn' : 'good' },
    { metric: 'Burn Multiple',    yours: `${burnMult}x`,  healthy: '<1.5x',status: parseFloat(burnMult) > 4 ? 'bad' : parseFloat(burnMult) > 1.5 ? 'warn' : 'good' },
  ];
  const statusIcon = { good: '✅', warn: '⚠️', bad: '🔴' };
  const matchTable = document.getElementById('match-table');
  if (matchTable) {
    matchTable.innerHTML = matchRows.map(r => `
      <tr>
        <td>${r.metric}</td>
        <td class="mt-yours mt-${r.status}">${statusIcon[r.status]} ${r.yours}</td>
        <td class="mt-target">${r.healthy}</td>
      </tr>`).join('');
  }

  // Signals + 4. early warning
  const sigList = document.getElementById('signals-list');
  sigList.innerHTML = '';
  let earliestDetectable = null;
  p.warning_signals_detected.forEach((s) => {
    const li = document.createElement('li');
    const icon = s.status === 'DETECTED' ? '🔴' : '🟡';
    const cls  = s.status === 'DETECTED' ? 'sig-detected' : 'sig-emerging';
    const daysAgo = s.days_detectable
      ? `<span class="sig-days">⏱ detectable ~${s.days_detectable}d ago</span>`
      : '';
    li.innerHTML = `<span>${icon}</span><span class="${cls}">${s.signal}</span>${daysAgo}`;
    sigList.appendChild(li);
    if (s.days_detectable && (earliestDetectable === null || s.days_detectable > earliestDetectable)) {
      earliestDetectable = s.days_detectable;
    }
  });

  // 4. Early warning banner
  if (earliestDetectable && earliestDetectable > 0) {
    const banner = document.getElementById('early-warning-banner');
    const txt = document.getElementById('early-warning-text');
    txt.innerHTML = `The Oracle would have detected the earliest warning signal <strong>${earliestDetectable} days before</strong> this analysis — giving you time to act before the crisis became visible.`;
    banner.classList.remove('hidden');
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

  // Playbook
  const pbList = document.getElementById('playbook-list');
  pbList.innerHTML = '';
  p.survival_playbook.forEach((step) => {
    const li = document.createElement('li');
    li.textContent = step;
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
      <span class="famous-outcome">${f.outcome === 'Failed' ? '❌ Failed' : '⚠️ ' + f.outcome}</span>
      <span class="famous-detail">${f.detail}</span>
    `;
    famList.appendChild(div);
  });

  show('alert-section');
  document.getElementById('alert-section').scrollIntoView({ behavior: 'smooth' });
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

  const md = `# ⚠️ FAILURE PATTERN ALERT
**Pattern:** ${p.pattern_name} (${p.pattern_id})
**Confidence:** ${Math.round(p.confidence * 100)}%
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
- ❌ **${failPct}% failed** within ${p.days_to_crisis} days
- ✅ **${survPct}% survived** (${p.survival_count} companies)

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

// ── Decision Audit ───────────────────────────────────────────────
async function runAudit() {
  const decision = document.getElementById('decision-text').value.trim();
  if (!decision) return alert('Please describe the decision first.');

  const btn = document.getElementById('audit-btn');
  btn.textContent = '⏳ Evaluating…';
  btn.disabled = true;

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
      body: JSON.stringify({ decision, metrics }),
    });
    const data = await res.json();
    renderAudit(data);
  } catch (err) {
    alert('Error connecting to API.');
    console.error(err);
  } finally {
    btn.textContent = '📋 Audit This Decision';
    btn.disabled = false;
  }
}

function renderAudit(data) {
  const el  = document.getElementById('audit-result');
  const cls = `risk-${data.risk_level.toLowerCase()}`;
  el.innerHTML = `
    <div class="audit-risk ${cls}">
      ${riskIcon(data.risk_level)} <strong>${data.risk_level} RISK</strong>
    </div>
    <p style="margin:0.8rem 0;font-size:0.9rem;color:#94a3b8;">
      Based on <strong>${data.total_cases}</strong> similar historical cases:
      ✅ ${data.success_cases} succeeded · ❌ ${data.failure_cases} failed
    </p>
    <p style="margin-bottom:0.6rem;font-style:italic;color:#cbd5e1;">
      Key difference: ${data.key_differentiator}
    </p>
    <p style="font-size:0.92rem;">${data.recommendation}</p>
  `;
  el.classList.remove('hidden');
  el.scrollIntoView({ behavior: 'smooth' });
}

function riskIcon(level) {
  return { LOW: '🟢', MEDIUM: '🟡', HIGH: '🔴', CRITICAL: '💀' }[level] || '⚠️';
}

// ── 3. Pattern Library ───────────────────────────────────────────
let _allPatterns = [];

async function loadPatternLibrary() {
  try {
    const res = await fetch(`${API}/api/patterns/`);
    const data = await res.json();
    _allPatterns = data.patterns || [];
    document.getElementById('patterns-count').textContent = `${_allPatterns.length} patterns`;
    renderPatternGrid(_allPatterns);
  } catch (e) {
    document.getElementById('patterns-grid').innerHTML = '<p style="color:#64748b">Could not load pattern library.</p>';
  }
}

function filterPatterns(category) {
  document.querySelectorAll('.pf-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  const filtered = category ? _allPatterns.filter(p => p.category === category) : _allPatterns;
  renderPatternGrid(filtered);
}

function renderPatternGrid(patterns) {
  const grid = document.getElementById('patterns-grid');
  if (!patterns.length) {
    grid.innerHTML = '<p style="color:#64748b;padding:1rem">No patterns in this category.</p>';
    return;
  }
  grid.innerHTML = patterns.map(p => {
    const total = (p.failure_count || 0) + (p.survival_count || 0);
    const survRate = total > 0 ? Math.round((p.survival_count / total) * 100) : 0;
    const riskColor = survRate < 15 ? '#ef4444' : survRate < 30 ? '#f59e0b' : '#10b981';
    const catLabel = CAT_LABELS[p.category] || (p.category || '').replace(/_/g, ' ');

    // Warning signals list
    const signals = (p.warning_signals || []).slice(0, 4).map(s =>
      `<li>⚡ ${s.signal} <span class="sig-days-small">${s.days_before_failure}d before</span></li>`
    ).join('');

    // Playbook steps
    const playbook = (p.survival_playbook || []).slice(0, 3).map((s, i) =>
      `<li>${i+1}. ${s}</li>`
    ).join('');

    // Famous failures
    const failures = (p.famous_failures || []).map(f =>
      `<span class="pc-failure-tag">💀 ${f.company}</span>`
    ).join('');

    // Sources
    const sources = (p.sources || []).map(s =>
      `<span class="pc-source-tag">📚 ${s}</span>`
    ).join('');

    return `
      <div class="pattern-card" onclick="togglePatternDetail(this)">
        <div class="pc-top">
          <div>
            <span class="pc-id">${p.pattern_id}</span>
            <span class="pc-cat">${catLabel}</span>
          </div>
          <span class="pc-surv" style="color:${riskColor}">${survRate}% survived</span>
        </div>
        <div class="pc-name">${p.name}</div>
        <div class="pc-stats">
          <span>❌ ${p.failure_count || 0} failed</span>
          <span>✅ ${p.survival_count || 0} survived</span>
          <span>📊 ${total} cases</span>
        </div>
        <div class="pc-detail hidden">
          <p class="pc-narrative">${p.narrative || ''}</p>
          ${signals ? `<div class="pc-section"><div class="pc-section-title">⚡ Early Warning Signals</div><ul class="pc-signal-list">${signals}</ul></div>` : ''}
          ${playbook ? `<div class="pc-section"><div class="pc-section-title">🛡️ Survival Playbook</div><ul class="pc-playbook-list">${playbook}</ul></div>` : ''}
          ${failures ? `<div class="pc-section"><div class="pc-section-title">🏢 Known Cases</div><div class="pc-failures">${failures}</div></div>` : ''}
          ${sources ? `<div class="pc-section"><div class="pc-section-title">📚 Sources</div><div class="pc-sources">${sources}</div></div>` : ''}
        </div>
        <div class="pc-expand-hint">Click to expand ▾</div>
      </div>`;
  }).join('');
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
    const color = survRate < 15 ? '#ef4444' : survRate < 25 ? '#f59e0b' : '#10b981';
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
  setTimeout(renderCatChart, 100);
}
function closeHowItWorks() {
  document.getElementById('hiw-overlay').classList.add('hidden');
  document.body.style.overflow = '';
}
function closeIfBackdrop(e) {
  if (e.target === document.getElementById('hiw-overlay')) closeHowItWorks();
}
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeHowItWorks(); });

// ── Helpers ─────────────────────────────────────────────────────
function val(id) { return document.getElementById(id)?.value || ''; }
function num(id) { return parseFloat(document.getElementById(id)?.value) || 0; }
function setText(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }
function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }
