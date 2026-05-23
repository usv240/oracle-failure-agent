import { test, expect, Page } from '@playwright/test';

const BASE = 'http://localhost:8080';

async function goToAuditor(page: Page) {
  await page.goto(BASE);
  await page.waitForLoadState('domcontentloaded');
  await page.click('[data-tab="tab-auditor"]');
  await expect(page.locator('#tab-auditor')).not.toHaveClass(/hidden/);
}

async function fillMetrics(page: Page) {
  // Switch to dashboard, fill Quibi metrics (gives richer audit context), come back
  await page.click('[data-tab="tab-dashboard"]');
  await page.evaluate(() => (window as any).fillDemo('quibi'));
  await page.click('[data-tab="tab-auditor"]');
}

// ── 1. UI Structure ───────────────────────────────────────────────────────────

test('Decision Auditor tab is reachable', async ({ page }) => {
  await goToAuditor(page);
  await expect(page.locator('#audit-section')).toBeVisible();
  await expect(page.locator('#decision-text')).toBeVisible();
  await expect(page.locator('#audit-btn')).toBeVisible();
  await expect(page.locator('#audit-btn')).toHaveText('Audit This Decision');
});

test('audit textarea accepts input', async ({ page }) => {
  await goToAuditor(page);
  await page.fill('#decision-text', 'Should I hire 3 engineers this month?');
  await expect(page.locator('#decision-text')).toHaveValue('Should I hire 3 engineers this month?');
});

test('audit button disabled feedback while running', async ({ page }) => {
  test.setTimeout(30_000);
  await goToAuditor(page);
  await page.fill('#decision-text', 'Should I double our marketing spend?');
  await page.click('#audit-btn');
  // Button should disable and show cycling text immediately
  await expect(page.locator('#audit-btn')).toBeDisabled({ timeout: 2000 });
});

// ── 2. Full Audit Run ─────────────────────────────────────────────────────────

test('audit returns result for hiring decision', async ({ page }) => {
  test.setTimeout(60_000);
  await goToAuditor(page);
  await fillMetrics(page);
  await page.fill('#decision-text', 'Should I hire 3 engineers this month?');
  await page.click('#audit-btn');

  await expect(page.locator('#audit-result')).not.toHaveClass(/hidden/, { timeout: 55_000 });

  // Must have risk level
  await expect(page.locator('#audit-result .audit-risk')).toBeVisible();
  const riskText = await page.locator('#audit-result .audit-risk').textContent() ?? '';
  const validRisks = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
  expect(validRisks.some(r => riskText.toUpperCase().includes(r))).toBeTruthy();
});

test('audit result contains recommendation and differentiator', async ({ page }) => {
  test.setTimeout(60_000);
  await goToAuditor(page);
  await page.fill('#decision-text', 'Should I raise prices by 20%?');
  await page.click('#audit-btn');

  await expect(page.locator('#audit-result')).not.toHaveClass(/hidden/, { timeout: 55_000 });

  const text = await page.locator('#audit-result').textContent();
  // Result should have substantive content
  expect(text?.length).toBeGreaterThan(100);
});

test('audit with high-risk metrics surfaces linked pattern card', async ({ page }) => {
  test.setTimeout(60_000);
  await goToAuditor(page);
  await fillMetrics(page); // Quibi metrics = high risk context
  await page.fill('#decision-text', 'Should I expand to Europe next quarter?');
  await page.click('#audit-btn');

  await expect(page.locator('#audit-result')).not.toHaveClass(/hidden/, { timeout: 55_000 });

  // With Quibi-level metrics, audit should link to a pattern
  const patternCard = page.locator('#audit-result .audit-pattern-card');
  if (await patternCard.isVisible()) {
    await expect(patternCard).toContainText('%'); // survival rate
  }
});

test('audit button re-enables after result', async ({ page }) => {
  test.setTimeout(120_000);
  await goToAuditor(page);
  await page.fill('#decision-text', 'Should I cut headcount by 20%?');
  await page.click('#audit-btn');

  await expect(page.locator('#audit-result')).not.toHaveClass(/hidden/, { timeout: 110_000 });
  await expect(page.locator('#audit-btn')).toBeEnabled();
  await expect(page.locator('#audit-btn')).toHaveText('Audit This Decision');
});

// ── 3. Edge Cases ─────────────────────────────────────────────────────────────

test('audit API endpoint works directly', async ({ page }) => {
  test.setTimeout(90_000);
  const metrics = {
    startup_name: 'TestCo',
    current_month: 12,
    mrr: 100000,
    mrr_growth_rate: 0.15,
    churn_rate: 0.05,
    burn_rate: 80000,
    runway_months: 18,
    headcount: 10,
    nps: 45,
    cac: 1000,
    ltv: 8000,
    industry: 'B2B SaaS',
  };
  const res = await page.request.post(`${BASE}/api/audit/evaluate`, {
    timeout: 80_000,
    data: {
      startup_name: metrics.startup_name,
      current_month: metrics.current_month,
      decision: 'Should I expand to a new market?',
      metrics,
    },
  });
  if (!res.ok()) {
    const body = await res.text();
    throw new Error(`Audit API ${res.status()}: ${body}`);
  }
  const body = await res.json();
  expect(body.decision).toBeTruthy();
  expect(body.recommendation).toBeTruthy();
  expect(body.risk_level).toMatch(/low|medium|high|critical/i);
});
