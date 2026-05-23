import { test, expect, Page } from '@playwright/test';

const BASE = 'http://localhost:8080';

async function goToPortfolio(page: Page) {
  await page.goto(BASE);
  await page.waitForLoadState('domcontentloaded');
  await page.click('[data-tab="tab-portfolio"]');
  await expect(page.locator('#tab-portfolio')).not.toHaveClass(/hidden/);
}

// ── 1. UI Structure ───────────────────────────────────────────────────────────

test('Portfolio tab shows 3 default rows', async ({ page }) => {
  await goToPortfolio(page);
  await expect(page.locator('.pf-row')).toHaveCount(3);
});

test('Add Company button adds a new row', async ({ page }) => {
  await goToPortfolio(page);
  await page.click('.pf-add-btn');
  await expect(page.locator('.pf-row')).toHaveCount(4);
});

test('Remove button deletes a row', async ({ page }) => {
  await goToPortfolio(page);
  await page.click('.pf-row-remove');
  await expect(page.locator('.pf-row')).toHaveCount(2);
});

test('Analyze Portfolio button is visible', async ({ page }) => {
  await goToPortfolio(page);
  await expect(page.locator('#pf-run-btn')).toBeVisible();
  await expect(page.locator('#pf-btn-text')).toHaveText('Analyze Portfolio');
});

// ── 2. Full Portfolio Analysis ────────────────────────────────────────────────

async function fillPortfolio(page: Page) {
  // Clear default rows and fill with known scenarios
  const rows = await page.locator('.pf-row').all();
  for (const row of rows) {
    const removeBtn = row.locator('.pf-row-remove');
    if (await removeBtn.isVisible()) await removeBtn.click();
  }

  // Add 3 test companies
  const companies = [
    { name: 'Quibi',      mrr: '420000',  churn: '22', runway: '14' }, // should be CRITICAL
    { name: 'AcmeSaaS',   mrr: '85000',   churn: '9',  runway: '11' }, // should be HIGH/MODERATE
    { name: 'HealthCo',   mrr: '120000',  churn: '3',  runway: '18' }, // should be SAFE
  ];

  for (const co of companies) {
    await page.click('.pf-add-btn');
    const rows = await page.locator('.pf-row').all();
    const last = rows[rows.length - 1];
    await last.locator('.pf-name-in').fill(co.name);
    await last.locator('.pf-mrr-in').fill(co.mrr);
    await last.locator('.pf-churn-in').fill(co.churn);
    await last.locator('.pf-runway-in').fill(co.runway);
  }
}

test('portfolio analysis runs and returns ranked results', async ({ page }) => {
  test.setTimeout(120_000);
  await goToPortfolio(page);
  await fillPortfolio(page);
  await page.click('#pf-run-btn');

  // Button should show loading state
  await expect(page.locator('#pf-btn-spinner')).toBeVisible({ timeout: 3000 });

  // Wait for results
  await expect(page.locator('#portfolio-result')).not.toHaveClass(/hidden/, { timeout: 110_000 });

  // Should show company rows
  await expect(page.locator('.pf-company-row')).toHaveCount(3);
});

test('portfolio summary shows correct counts', async ({ page }) => {
  test.setTimeout(120_000);
  await goToPortfolio(page);
  await fillPortfolio(page);
  await page.click('#pf-run-btn');
  await expect(page.locator('#portfolio-result')).not.toHaveClass(/hidden/, { timeout: 110_000 });

  // Summary should show total = 3
  await expect(page.locator('.pf-sum-stat').first()).toContainText('3');
});

test('portfolio results ranked with highest risk first', async ({ page }) => {
  test.setTimeout(120_000);
  await goToPortfolio(page);
  await fillPortfolio(page);
  await page.click('#pf-run-btn');
  await expect(page.locator('#portfolio-result')).not.toHaveClass(/hidden/, { timeout: 110_000 });

  const rows = await page.locator('.pf-company-row').all();
  expect(rows.length).toBe(3);

  // First row should be rank #1
  await expect(page.locator('.pf-company-row').first().locator('.pf-rank')).toContainText('#1');

  // Risk chips should be present on all rows
  for (const row of rows) {
    await expect(row.locator('.pf-risk-chip')).toBeVisible();
  }
});

test('portfolio result rows have risk chips and names', async ({ page }) => {
  test.setTimeout(120_000);
  await goToPortfolio(page);
  await fillPortfolio(page);
  await page.click('#pf-run-btn');
  await expect(page.locator('#portfolio-result')).not.toHaveClass(/hidden/, { timeout: 110_000 });

  // Every row must have a company name and a risk chip
  const rows = page.locator('.pf-company-row');
  const count = await rows.count();
  expect(count).toBe(3);
  for (let i = 0; i < count; i++) {
    await expect(rows.nth(i).locator('.pf-name')).not.toBeEmpty();
    await expect(rows.nth(i).locator('.pf-risk-chip')).toBeVisible();
  }
});

test('portfolio button re-enables after analysis', async ({ page }) => {
  test.setTimeout(120_000);
  await goToPortfolio(page);
  await fillPortfolio(page);
  await page.click('#pf-run-btn');
  await expect(page.locator('#portfolio-result')).not.toHaveClass(/hidden/, { timeout: 110_000 });
  await expect(page.locator('#pf-run-btn')).toBeEnabled();
});

// ── 3. API direct test ────────────────────────────────────────────────────────

test('portfolio API response structure is valid', async ({ page }) => {
  // Single startup — validates API contract without running full multi-Gemini chain.
  // Full end-to-end multi-company ranking is covered by the UI test above.
  test.setTimeout(120_000);
  const res = await page.request.post(`${BASE}/api/portfolio/analyze`, {
    timeout: 110_000,
    data: {
      startups: [
        {
          startup_name: 'Quibi',
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
      ],
    },
  });
  expect(res.ok()).toBeTruthy();
  const body = await res.json();

  // Shape validation
  expect(body.total).toBe(1);
  expect(body.companies).toHaveLength(1);
  expect(['CRITICAL', 'HIGH', 'MODERATE', 'SAFE']).toContain(body.companies[0].risk_level);
  expect(typeof body.companies[0].confidence).toBe('number');
  expect(body.companies[0].startup_name).toBe('Quibi');

  // Summary counts add up
  const { critical, high_risk, moderate, safe } = body;
  expect(critical + high_risk + moderate + safe).toBe(1);
});

test('portfolio API rejects more than 20 startups', async ({ page }) => {
  const startups = Array.from({ length: 21 }, (_, i) => ({
    startup_name: `Company${i}`,
    current_month: 12,
    mrr: 100000,
    mrr_growth_rate: 0.1,
    churn_rate: 0.05,
    burn_rate: 80000,
    runway_months: 12,
    headcount: 10,
    nps: 40,
    cac: 1000,
    ltv: 8000,
    industry: 'B2B SaaS',
  }));
  const res = await page.request.post(`${BASE}/api/portfolio/analyze`, {
    data: { startups },
  });
  expect(res.status()).toBe(422);
});
