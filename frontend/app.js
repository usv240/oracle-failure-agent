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
  // Quibi: $1.75B raised, 175 employees, shut down 6 months after launch.
  // Burn rate ~$8.5M/month, 35K subscribers at peak, CAC astronomical.
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
  // WeWork: Burned $47B valuation to near-bankruptcy.
  // $47B raise on <$2B revenue, CAC >> LTV, burn rate $219M/month at peak.
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
  // Theranos: 10 years of fraud. $700M raised, <$100K real revenue,
  // 800+ employees burning cash on technology that never worked.
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

function fillDemo(type) {
  const d = DEMOS[type];
  Object.keys(d).forEach((key) => {
    const el = document.getElementById(key);
    if (el) el.value = d[key];
  });
}

// ── Form Submit ─────────────────────────────────────────────────
document.getElementById('metrics-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  await runAnalysis();
});

async function runAnalysis() {
  const btnText    = document.getElementById('btn-text');
  const btnSpinner = document.getElementById('btn-spinner');
  btnText.classList.add('hidden');
  btnSpinner.classList.remove('hidden');

  hide('alert-section');
  hide('safe-section');

  const payload = {
    startup_name:      val('startup_name'),
    current_month:     num('current_month'),
    mrr:               num('mrr'),
    mrr_growth_rate:   num('mrr_growth_rate'),
    churn_rate:        num('churn_rate'),
    burn_rate:         num('burn_rate'),
    runway_months:     num('runway_months'),
    headcount:         num('headcount'),
    nps:               num('nps'),
    cac:               num('cac'),
    ltv:               num('ltv'),
    industry:          val('industry'),
  };

  try {
    const res  = await fetch(`${API}/api/metrics/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    renderResult(data);
  } catch (err) {
    alert('Error connecting to Oracle API. Is the server running?');
    console.error(err);
  } finally {
    btnText.classList.remove('hidden');
    btnSpinner.classList.add('hidden');
  }
}

function renderResult(data) {
  if (!data.alert) {
    show('safe-section');
    return;
  }

  const p = data.pattern;

  // Header
  setText('alert-title', `⚠️ ${p.pattern_name}`);
  const pct = Math.round(p.confidence * 100);
  document.getElementById('conf-bar').style.width = `${pct}%`;
  setText('conf-pct', `${pct}%`);

  // Narrative
  setText('alert-narrative', p.narrative);

  // Signals
  const sigList = document.getElementById('signals-list');
  sigList.innerHTML = '';
  p.warning_signals_detected.forEach((s) => {
    const li = document.createElement('li');
    const icon = s.status === 'DETECTED' ? '🔴' : '🟡';
    const cls  = s.status === 'DETECTED' ? 'sig-detected' : 'sig-emerging';
    li.innerHTML = `<span>${icon}</span><span class="${cls}">${s.signal}</span>`;
    sigList.appendChild(li);
  });

  // Stats
  const total   = p.failure_count + p.survival_count;
  const failPct = Math.round((1 - p.survival_rate) * 100);
  const survPct = Math.round(p.survival_rate * 100);
  setText('fail-pct',    `${failPct}%`);
  setText('surv-pct',    `${survPct}%`);
  setText('total-cases', total.toLocaleString());
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

  // Output path
  setText('output-path', p.output_file || 'outputs/latest_alert.md');

  show('alert-section');
  document.getElementById('alert-section').scrollIntoView({ behavior: 'smooth' });
}

// ── Decision Audit ──────────────────────────────────────────────
async function runAudit() {
  const decision = document.getElementById('decision-text').value.trim();
  if (!decision) return alert('Please describe the decision first.');

  const btn = document.getElementById('audit-btn');
  btn.textContent = '⏳ Evaluating…';
  btn.disabled = true;

  // Reuse current form values for metrics
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
    <p style="font-size:0.75rem;color:#4b5563;margin-top:0.8rem;">
      📄 Saved to: outputs/latest_audit.md
    </p>
  `;
  el.classList.remove('hidden');
  el.scrollIntoView({ behavior: 'smooth' });
}

function riskIcon(level) {
  return { LOW: '🟢', MEDIUM: '🟡', HIGH: '🔴', CRITICAL: '💀' }[level] || '⚠️';
}

// ── Helpers ─────────────────────────────────────────────────────
function val(id) { return document.getElementById(id)?.value || ''; }
function num(id) { return parseFloat(document.getElementById(id)?.value) || 0; }
function setText(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }
function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }
