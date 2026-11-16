import assert from 'node:assert/strict';
import { checkFoundation } from '../../frontend/scripts/aptron_foundation_acceptance.mjs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE);
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'domcontentloaded' });
  await page.getByRole('textbox', { name: 'Username' }).fill('test-north');
  await page.getByLabel('Password').fill('testing-only-StrongPassword-123!');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.locator('button.nav-button').first().waitFor({ state: 'visible', timeout: 30000 });
  assert.match(await page.title(), /APTron/i);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.locator('button.nav-button').first().waitFor({ state: 'visible', timeout: 30000 });
  assert.equal(await page.getByRole('button', { name: 'Sign in', exact: true }).count(), 0);
  await checkFoundation(page, {
    ui_url: 'http://127.0.0.1:5173',
    base_url: 'http://127.0.0.1:8000',
    customer_name: /Example North Lab/,
    viewer_username: 'test-reader',
    viewer_password: 'testing-only-StrongPassword-123!',
  }, process.argv[2]);
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ status: 'PASS', checks: ['render', 'sign-in', 'APTron-brand', 'authenticated-reload', 'compute-pipeline-api-navigation', 'retired-incident-bookmark', 'local-help-links', 'light-dark-desktop-tablet-mobile', 'keyboard-dialog-focus', 'real-viewer-role-filtering', 'no-page-errors'], scope: 'synthetic-disposable-staging', production_eligible: false }, null, 2));
} finally {
  await browser.close();
}
