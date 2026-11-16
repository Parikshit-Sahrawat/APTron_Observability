import assert from 'node:assert/strict';
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
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ status: 'PASS', checks: ['render', 'sign-in', 'APTron-brand', 'authenticated-reload', 'no-page-errors'], scope: 'synthetic-disposable-staging', production_eligible: false }, null, 2));
} finally {
  await browser.close();
}
