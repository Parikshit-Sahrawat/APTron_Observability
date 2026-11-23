import assert from 'node:assert/strict';
import { checkFoundation } from '../../frontend/scripts/aptron_foundation_acceptance.mjs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE);
const origin = process.env.SH02_ORIGIN;
const url = new URL(origin);
assert.equal(url.protocol, 'https:');
assert.equal(url.hostname, '127.0.0.1');
assert.match(process.env.SH02_SPKI, /^[A-Za-z0-9+/]{43}=$/);
// Only this freshly generated fixture certificate's SPKI is accepted by Chromium.
// Python independently verifies CA trust, hostname and untrusted-certificate denial.
const browser = await chromium.launch({ headless: true, args: [
  '--ignore-certificate-errors-spki-list=' + process.env.SH02_SPKI,
] });
try {
  const page = await browser.newPage();
  const errors = [];
  const wrongOrigins = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => {
    if (/^https?:/.test(r.url()) && new URL(r.url()).origin !== origin)
      wrongOrigins.push(new URL(r.url()).origin);
  });
  await page.goto(origin, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('Username', { exact: true }).fill('test-north');
  await page.getByLabel('Password', { exact: true }).fill('testing-only-StrongPassword-123!');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.getByRole('navigation', { name: 'Primary navigation' }).waitFor();
  await page.reload();
  await page.getByRole('navigation', { name: 'Primary navigation' }).waitFor();
  await checkFoundation(page, { ui_url: origin, base_url: origin,
    customer_name: /Example North Lab/, viewer_username: 'test-reader',
    viewer_password: 'testing-only-StrongPassword-123!' }, process.argv[2]);
  assert.deepEqual(errors, []);
  assert.deepEqual(wrongOrigins, []);
  console.log(JSON.stringify({ status: 'PASS', scope: 'SH-02',
    checks: ['TLS same-origin sign-in/reload', 'real viewer permissions',
      'existing foundation browser checks', 'no external HTTP origins', 'no page errors'],
    production_eligible: false }));
} finally { await browser.close(); }
