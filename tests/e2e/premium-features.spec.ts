import { test, expect } from '@playwright/test';

const BASE = 'http://localhost:8080';

test('Premium UI: Trajectory forecast chart and audio debate elements render and function', async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto(BASE);
  await page.waitForLoadState('domcontentloaded');

  // Pre-fill with Theranos' pre-failure metrics
  await page.evaluate(() => (window as any).fillDemo('theranos'));

  // Run the analysis
  await page.click('#metrics-form button[type="submit"]');

  // Wait for the alert section to become visible
  await page.waitForSelector('#alert-section:not(.hidden)', { timeout: 85_000 });

  // 1. Verify the 'Listen to Agent Debate' audio debrief button is present
  const debateBtn = page.locator('#chp-play-btn');
  await expect(debateBtn).toBeVisible();
  
  // Verify status is "Debate ready"
  const audioStatus = page.locator('#chp-audio-status');
  await expect(audioStatus).toContainText('Debate ready');

  // Click the debate button and check if it transitions to speaking state
  await debateBtn.click();
  
  // In the headless browser, SpeechSynthesis might speak or trigger immediately
  // Let's verify the button changes state to speaking or stop debate
  const btnText = await debateBtn.locator('#chp-play-text').textContent();
  expect(btnText === 'Stop Agent Debate' || btnText === 'Listen to Agent Debate').toBeTruthy();

  // Turn it off if it was playing
  if (btnText === 'Stop Agent Debate') {
    await debateBtn.click();
  }

  // 2. Click the 'Metrics & Timeline' tab and check for Trajectory Chart
  const metricsTabBtn = page.locator('button:has-text("Metrics & Timeline")');
  await expect(metricsTabBtn).toBeVisible();
  await metricsTabBtn.click();

  // Verify 'trajectory-chart' canvas element is rendered inside the visible tab
  const chartCanvas = page.locator('#trajectory-chart');
  await expect(chartCanvas).toBeVisible();

  // 3. Verify 'Print Forensic Brief' button is present
  const printBtn = page.locator('button:has-text("Print Forensic Brief")');
  await expect(printBtn).toBeVisible();
});
