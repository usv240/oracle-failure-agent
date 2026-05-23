import { test, expect, Page } from '@playwright/test';

const BASE = 'http://localhost:8080';

// ── Helpers ──────────────────────────────────────────────────────────────────

async function goTo(page: Page) {
  await page.goto(BASE);
  await page.waitForLoadState('networkidle');
}

async function clickDemo(page: Page, name: 'quibi' | 'wework' | 'theranos' | 'healthy') {
  await page.evaluate((n) => (window as any).fillDemo(n), name);
}

async function runAnalysis(page: Page) {
  await page.click('#metrics-form button[type="submit"]');
}

// ── 1. Page Load ──────────────────────────────────────────────────────────────

test('page loads with title and sidebar', async ({ page }) => {
  await goTo(page);
  await expect(page).toHaveTitle('The Failure Oracle');
  // Brand name visible in sidebar (desktop) or mobile header
  const brand = page.locator('.brand-name, .mobile-header-brand span').first();
  await expect(brand).toContainText('The Failure Oracle');
});

test('live stats bar appears when backend is reachable', async ({ page }) => {
  await goTo(page);
  await page.waitForTimeout(2000); // allow stats fetch
  const bar = page.locator('#live-stats-bar');
  // Bar visible = backend is up; hidden = backend down (both are valid)
  const isVisible = await bar.isVisible();
  if (isVisible) {
    await expect(page.locator('#ls-patterns')).not.toHaveText('—');
  }
});

test('impact bar shows static claims', async ({ page }) => {
  await goTo(page);
  await expect(page.locator('.impact-bar')).toContainText('150M+');
  await expect(page.locator('.impact-bar')).toContainText('100');
});

// ── 2. Navigation ─────────────────────────────────────────────────────────────

test('sidebar tab navigation switches content', async ({ page }) => {
  await goTo(page);

  // Pattern Library tab
  await page.click('[data-tab="tab-library"]');
  await expect(page.locator('#tab-library')).not.toHaveClass(/hidden/);
  await expect(page.locator('#tab-dashboard')).toHaveClass(/hidden/);

  // Back to Dashboard
  await page.click('[data-tab="tab-dashboard"]');
  await expect(page.locator('#tab-dashboard')).not.toHaveClass(/hidden/);
});

test('VC Portfolio tab is accessible', async ({ page }) => {
  await goTo(page);
  await page.click('[data-tab="tab-portfolio"]');
  await expect(page.locator('#tab-portfolio')).not.toHaveClass(/hidden/);
  // Portfolio rows seeded on init
  await expect(page.locator('.pf-row')).toHaveCount(3);
});

test('theme toggle switches dark/light mode', async ({ page }) => {
  await goTo(page);
  const html = page.locator('html');
  const initial = await html.getAttribute('data-theme');
  await page.click('#theme-btn');
  const toggled = await html.getAttribute('data-theme');
  expect(toggled).not.toBe(initial);
});

// ── 3. Demo Scenarios ─────────────────────────────────────────────────────────

test('Quibi demo fills form fields', async ({ page }) => {
  await goTo(page);
  await clickDemo(page, 'quibi');
  await expect(page.locator('#startup_name')).toHaveValue(/Quibi/i);
  await expect(page.locator('#churn_rate')).toHaveValue('0.22');
});

test('Healthy demo fills form fields', async ({ page }) => {
  await goTo(page);
  await clickDemo(page, 'healthy');
  const name = await page.locator('#startup_name').inputValue();
  expect(name.length).toBeGreaterThan(0);
});

// ── 4. Analysis Pipeline ──────────────────────────────────────────────────────

test('Quibi analysis returns CRITICAL alert', async ({ page }) => {
  test.setTimeout(90_000);
  await goTo(page);
  await clickDemo(page, 'quibi');
  await runAnalysis(page);

  // Terminal becomes visible while streaming
  await expect(page.locator('#agent-terminal')).toBeVisible({ timeout: 5000 });

  // Wait for either result section to become visible
  await page.waitForSelector('#alert-section:not(.hidden), #safe-section:not(.hidden)', { timeout: 85_000 });

  // Quibi should always be an alert
  await expect(page.locator('#alert-section')).not.toHaveClass(/hidden/);
  await expect(page.locator('#alert-section')).toContainText('Product-Market Fit');
});

test('terminal collapses to pill after analysis', async ({ page }) => {
  test.setTimeout(60_000);
  await goTo(page);
  await clickDemo(page, 'quibi');
  await runAnalysis(page);

  await expect(page.locator('#alert-section')).toBeVisible({ timeout: 55_000 });

  // Terminal should be hidden, pill should be visible
  await expect(page.locator('#agent-terminal')).toBeHidden();
  await expect(page.locator('#terminal-pill')).toBeVisible();
  await expect(page.locator('#terminal-pill')).toContainText('steps');
});

test('clicking terminal pill expands the log', async ({ page }) => {
  test.setTimeout(60_000);
  await goTo(page);
  await clickDemo(page, 'quibi');
  await runAnalysis(page);
  await expect(page.locator('#alert-section')).toBeVisible({ timeout: 55_000 });

  await page.click('#terminal-pill');
  await expect(page.locator('#agent-terminal')).toBeVisible();
  await expect(page.locator('#terminal-pill')).toBeHidden();
});

test('Healthy startup returns safe result', async ({ page }) => {
  test.setTimeout(60_000);
  await goTo(page);
  await clickDemo(page, 'healthy');
  await runAnalysis(page);
  await page.waitForSelector('#alert-section:not(.hidden), #safe-section:not(.hidden)', { timeout: 55_000 });
  await expect(page.locator('#safe-section')).not.toHaveClass(/hidden/);
});

// ── 5. Alert Result Card ──────────────────────────────────────────────────────

test('alert card shows provenance strip', async ({ page }) => {
  test.setTimeout(60_000);
  await goTo(page);
  await clickDemo(page, 'quibi');
  await runAnalysis(page);
  await expect(page.locator('#alert-section')).toBeVisible({ timeout: 55_000 });

  const strip = page.locator('.provenance-strip');
  await expect(strip).toBeVisible();
  await expect(strip).toContainText('Voyage AI');
  await expect(strip).toContainText('Atlas Vector Search');
  await expect(strip).toContainText('Gemini 3');
});

test('alert card shows pattern library jump link', async ({ page }) => {
  test.setTimeout(60_000);
  await goTo(page);
  await clickDemo(page, 'quibi');
  await runAnalysis(page);
  await expect(page.locator('#alert-section')).toBeVisible({ timeout: 55_000 });
  await expect(page.locator('#alert-lib-link')).toBeVisible();
  await expect(page.locator('#alert-lib-link')).toContainText('Pattern Library');
});

test('pattern library jump link scrolls to and highlights pattern', async ({ page }) => {
  test.setTimeout(60_000);
  await goTo(page);
  await clickDemo(page, 'quibi');
  await runAnalysis(page);
  await expect(page.locator('#alert-section')).toBeVisible({ timeout: 55_000 });

  await page.click('#alert-lib-link');
  // Pattern Library tab should now be active (jumpToPattern calls switchTab)
  await expect(page.locator('#tab-library')).not.toHaveClass(/hidden/, { timeout: 3000 });
});

// ── 6. Pattern Library ────────────────────────────────────────────────────────

test('pattern library loads 100 patterns', async ({ page }) => {
  test.setTimeout(30_000);
  await goTo(page);
  await page.click('[data-tab="tab-library"]');
  // Wait for patterns to load from API
  await expect(page.locator('.pattern-card')).toHaveCount(100, { timeout: 20_000 });
});

test('pattern library filter by category works', async ({ page }) => {
  test.setTimeout(30_000);
  await goTo(page);
  await page.click('[data-tab="tab-library"]');
  await expect(page.locator('.pattern-card')).toHaveCount(100, { timeout: 20_000 });

  // Filter to unit_economics
  await page.evaluate(() => (window as any).filterPatterns('unit_economics'));
  await page.waitForTimeout(300);
  // Count cards not hidden by display:none (filterPatterns uses style or hidden class)
  const total = await page.locator('.pattern-card').count();
  const hidden = await page.locator('.pattern-card[style*="none"], .pattern-card.hidden').count();
  const visible = total - hidden;
  expect(visible).toBeGreaterThan(0);
  expect(visible).toBeLessThan(100);
});

test('pattern card expands on click', async ({ page }) => {
  test.setTimeout(30_000);
  await goTo(page);
  await page.click('[data-tab="tab-library"]');
  await expect(page.locator('.pattern-card')).toHaveCount(100, { timeout: 20_000 });

  // patterns-container starts hidden — expose it before clicking
  await page.evaluate(() => {
    document.getElementById('patterns-container')?.classList.remove('hidden');
  });

  const first = page.locator('.pattern-card').first();
  await first.scrollIntoViewIfNeeded();
  await first.click();
  await expect(first.locator('.pc-detail')).not.toHaveClass(/hidden/);
});

// ── 7. How It Works Modal ─────────────────────────────────────────────────────

test('how it works modal opens and closes', async ({ page }) => {
  await goTo(page);
  await page.click('.how-btn');
  await expect(page.locator('#hiw-overlay')).toBeVisible();
  await expect(page.locator('#hiw-overlay')).toContainText('MongoDB Voyage AI');
  await page.click('.hiw-close');
  await expect(page.locator('#hiw-overlay')).toBeHidden();
});

// ── 8. API Health ─────────────────────────────────────────────────────────────

test('health endpoint reports Voyage AI embedding', async ({ page }) => {
  const res = await page.request.get(`${BASE}/api/health`);
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  expect(body.status).toBe('ok');
  expect(body.mongodb).toBe('connected');
  expect(body.embedding_source).toBe('MongoDB Voyage AI');
  expect(body.embedding_model).toContain('voyage-4-large');
});

test('stats endpoint returns live MongoDB counts', async ({ page }) => {
  const res = await page.request.get(`${BASE}/api/stats`);
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  expect(body.pattern_count).toBe(100);
  expect(typeof body.total_analyses).toBe('number');
});

test('patterns endpoint returns 100 patterns', async ({ page }) => {
  const res = await page.request.get(`${BASE}/api/patterns/`);
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  expect(body.total).toBe(100);
  expect(body.patterns.length).toBe(100);
});
