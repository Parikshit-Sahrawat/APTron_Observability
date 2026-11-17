// Real synthetic PostgreSQL/API/browser state; no fabricated API responses.
import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';

export async function checkOrganizationLifecycle(browser, fixture, out) {
  const ui = new URL(fixture.ui_url);
  const api = new URL(fixture.base_url);
  assert.equal(ui.hostname, '127.0.0.1');
  assert.equal(api.hostname, '127.0.0.1');
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.name));
  const report = { status: 'NOT_RUN', scope: 'synthetic-disposable-staging-organizations', checks: [], production_eligible: false,
    limitations: ['Not independent owner UAT', 'No agent enrollment, Compute activation, native telemetry or HA certification'] };
  let phase = 'login';
  async function login(username) {
    await page.getByLabel('Username', { exact: true }).fill(username);
    await page.getByLabel('Password', { exact: true }).fill(fixture.password);
    const customerScope = page.waitForResponse(response =>
      new URL(response.url()).pathname === '/api/v1/auth/customer-scope' && response.request().method() === 'GET');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    const response = await customerScope;
    assert.equal(response.status(), 200);
    const directory = await response.json();
    // The real directory response normalizes the prior user's ALL/UUID filter.
    // Wait for that state to be applied before navigating into a keyed inventory.
    await page.waitForFunction(ids => {
      const mode = localStorage.getItem('opscontrol.customerSelectionMode');
      const selected = JSON.parse(localStorage.getItem('opscontrol.organizationIds') || '[]');
      return (mode === 'SELECTED' || (mode === 'ALL' && selected.length === ids.length))
        && selected.every(id => ids.includes(id));
    }, directory.map(customer => customer.id));
    await page.getByRole('navigation', { name: 'Primary navigation' }).waitFor();
  }
  async function organizations() {
    await page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('button', { name: 'Organizations', exact: true }).click();
    const region = page.getByRole('region', { name: 'Monitored customer organizations' });
    await region.getByRole('heading', { name: 'Organizations', exact: true }).waitFor();
    await region.getByText('Loading Resource Management', { exact: true }).waitFor({ state: 'hidden' });
    await region.getByRole('table').waitFor({ state: 'visible' });
    return region;
  }
  try {
    await page.goto(ui.href);
    await login('test-admin');
    // ALL is an explicit filter over the current active customer directory.
    // It does not grant access to inactive customers or bypass tenant scope.
    const principal = await page.evaluate(async base => {
      const response = await fetch(base + '/api/v1/auth/me', { headers: { Authorization: 'Bearer ' + sessionStorage.getItem('opscontrol.sessionToken') } });
      if (!response.ok) throw Error('Fixture authority unavailable');
      return response.json();
    }, api.origin);
    assert.equal(principal.all_customers_authorized, true);
    await page.locator('.org-context-button').click();
    await page.locator('.org-menu').getByRole('checkbox', { name: /^ALL customers/ }).check();
    await page.locator('.org-context-button').click();
    const token = await page.evaluate(() => sessionStorage.getItem('opscontrol.sessionToken'));
    const headers = { Authorization: 'Bearer ' + token, 'X-OpsControl-Customers': 'ALL' };
    phase = 'seed-real-pagination';
    for (let index = 0; index < 39; index++) {
      const response = await page.request.post(api.origin + '/api/v1/organizations', {
        headers, data: { name: 'APTron lifecycle seed ' + String(index).padStart(2, '0'), code: 'LCSEED' + index, active: index < 26 },
      });
      assert.equal(response.status(), 201);
    }
    let region = await organizations();
    const search = region.getByLabel('Search organizations', { exact: true });
    const status = region.getByLabel('Organization status', { exact: true });
    phase = 'organization-search-fill';
    await search.fill('APTron lifecycle seed');
    phase = 'organization-status-active';
    await status.selectOption('active');
    assert.equal(await region.getByRole('row').count(), 26);
    assert.deepEqual(await region.locator('tbody tr td:nth-child(2)').allTextContents(),
      Array.from({ length: 25 }, (_, index) => 'LCSEED' + index));
    phase = 'organization-status-inactive';
    await status.selectOption('inactive');
    assert.equal(await region.getByRole('row').count(), 1);
    await region.getByText('No organizations in this scope.', { exact: true }).waitFor();
    phase = 'organization-status-all-page-one';
    await status.selectOption('all');
    assert.equal(await region.getByRole('row').count(), 26);
    phase = 'organization-status-all-page-two';
    await region.getByRole('button', { name: 'Next', exact: true }).click();
    assert.equal(await region.getByRole('row').count(), 2);
    assert.equal(await region.locator('tbody tr td:nth-child(2)').textContent(), 'LCSEED25');
    report.checks.push('39 real fixtures: ALL exposes only 26 active customers; 13 inactive customers excluded; both inventory pages verified');

    phase = 'save-hidden-by-old-filter';
    await search.fill('no matching organization');
    await status.selectOption('inactive');
    await region.getByRole('button', { name: 'Create Organization', exact: true }).click();
    let dialog = page.getByRole('dialog', { name: 'Create Organization', exact: true });
    await dialog.getByLabel('Organization Name').fill('ZZ APTron lifecycle target');
    await dialog.getByLabel('Short Code').fill('LCTARGET');
    let captured, rejected, release;
    const received = new Promise((resolve, reject) => { captured = resolve; rejected = reject; });
    const held = new Promise(resolve => { release = resolve; });
    let posts = 0;
    let routeFinished;
    let routeFailure;
    const finished = new Promise(resolve => { routeFinished = resolve; });
    let saved;
    const routePattern = '**/api/v1/organizations';
    await page.route(routePattern, async route => {
      if (route.request().method() !== 'POST') return route.continue();
      posts++;
      if (posts !== 1) return route.continue();
      let completionAttempted = false;
      try {
        const response = await route.fetch();
        assert.equal(response.status(), 201);
        saved = await response.json();
        captured();
        await held;
        completionAttempted = true;
        await route.fulfill({ response });
      } catch (error) {
        routeFailure = error;
        rejected(error);
        // Never attempt a second completion after fulfill has handled a route.
        if (!completionAttempted) {
          try { await route.abort(); } catch (abortError) { routeFailure = abortError; }
        }
      } finally {
        routeFinished();
      }
    });
    try {
      await Promise.all([
        dialog.getByRole('button', { name: 'Save', exact: true }).click(),
        received,
      ]);
      assert.equal(await dialog.getByRole('button', { name: 'Saving…', exact: true }).isDisabled(), true);
      // Reentrant native submit while the unchanged real server response is held.
      await dialog.locator('form').evaluate(form => form.requestSubmit());
      await dialog.getByRole('button', { name: 'Close resource dialog', exact: true }).click();
      await page.keyboard.press('Escape');
      assert.equal(await dialog.isVisible(), true);
      release();
      await finished;
      if (routeFailure) throw routeFailure;
      await dialog.waitFor({ state: 'hidden' });
      await region.getByRole('row').filter({ hasText: 'ZZ APTron lifecycle target' }).waitFor();
    } finally {
      release();
      if (posts) await finished;
      await page.unroute(routePattern);
    }
    assert.equal(posts, 1);
    assert.equal(await search.inputValue(), '');
    assert.equal(await status.inputValue(), 'all');
    assert.equal(await region.getByRole('button', { name: 'Previous', exact: true }).isEnabled(), true);
    report.checks.push('Real create reveals saved ID beyond page one despite old search/status; pending form rejects duplicate submit and close');

    phase = 'rename-preserve';
    await search.fill('ZZ APTron lifecycle target');
    await region.getByRole('row').filter({ hasText: 'ZZ APTron lifecycle target' }).getByRole('button', { name: 'Edit', exact: true }).click();
    dialog = page.getByRole('dialog', { name: 'Edit Organization', exact: true });
    await dialog.getByLabel('Organization Name').fill('A APTron lifecycle renamed');
    await dialog.getByRole('button', { name: 'Save', exact: true }).click();
    await dialog.waitFor({ state: 'hidden' });
    await region.getByRole('row').filter({ hasText: 'A APTron lifecycle renamed' }).waitFor();
    assert.equal(await search.inputValue(), '');
    assert.equal(await status.inputValue(), 'all');
    const persistedResponse = await page.request.get(api.origin + '/api/v1/organizations/' + saved.id, { headers });
    assert.equal(persistedResponse.status(), 200);
    const persisted = await persistedResponse.json();
    assert.equal(persisted.id, saved.id);
    assert.equal(persisted.created_at, saved.created_at);
    assert.equal(persisted.name, 'A APTron lifecycle renamed');
    assert.equal(persisted.code, 'LCTARGET');
    assert.equal(persisted.active, true);
    await page.reload();
    region = await organizations();
    await region.getByRole('row').filter({ hasText: 'A APTron lifecycle renamed' }).waitFor();
    await region.getByLabel('Search organizations', { exact: true }).fill('LCTARGET');
    await region.getByLabel('Organization status', { exact: true }).selectOption('active');
    assert.equal(await region.getByRole('row').count(), 2);
    await region.getByLabel('Organization status', { exact: true }).selectOption('inactive');
    assert.equal(await region.getByRole('row').count(), 1);
    await region.getByLabel('Organization status', { exact: true }).selectOption('all');
    report.checks.push('Rename retains canonical ID, code and creation time; reload and combined filters show authorized persisted state');

    phase = 'server-conflict-preserves-form';
    await region.getByRole('button', { name: 'Create Organization', exact: true }).click();
    dialog = page.getByRole('dialog', { name: 'Create Organization', exact: true });
    await dialog.getByLabel('Organization Name').fill('APTron duplicate must not save');
    await dialog.getByLabel('Short Code').fill('LCTARGET');
    await dialog.getByRole('button', { name: 'Save', exact: true }).click();
    await dialog.getByRole('alert').waitFor();
    assert.equal(await dialog.getByLabel('Organization Name').inputValue(), 'APTron duplicate must not save');
    assert.equal(await dialog.getByRole('button', { name: 'Save', exact: true }).isEnabled(), true);
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    report.checks.push('Real duplicate-code rejection retains editable form and exposes an accessible error');

    phase = 'responsive-keyboard';
    for (const mode of ['Light', 'Dark']) {
      await page.getByRole('button', { name: mode + ' theme', exact: true }).click();
      for (const width of [1366, 768, 390]) {
        await page.setViewportSize({ width, height: 900 });
        await region.getByRole('row').filter({ hasText: 'A APTron lifecycle renamed' }).getByRole('button', { name: 'Edit', exact: true }).click();
        dialog = page.getByRole('dialog', { name: 'Edit Organization', exact: true });
        await dialog.waitFor();
        assert.equal(await dialog.getByLabel('Active customer', { exact: true }).isChecked(), true);
        const box = await dialog.boundingBox();
        assert.ok(box.x >= 0 && box.x + box.width <= width + 1);
        assert.ok(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth + 1));
        await page.screenshot({ path: join(out, `organizations-${mode.toLowerCase()}-${width}.png`), fullPage: true });
        await page.keyboard.press('Escape');
        await dialog.waitFor({ state: 'hidden' });
      }
    }
    report.checks.push('Persisted edit form is contained at desktop/tablet/mobile in both themes; Escape closes idle dialog');

    phase = 'deactivate-leaves-active-directory';
    await page.setViewportSize({ width: 1366, height: 900 });
    await region.getByRole('row').filter({ hasText: 'A APTron lifecycle renamed' }).getByRole('button', { name: 'Edit', exact: true }).click();
    dialog = page.getByRole('dialog', { name: 'Edit Organization', exact: true });
    await dialog.getByLabel('Active customer', { exact: true }).uncheck();
    const deactivation = page.waitForResponse(response => response.url() === api.origin + '/api/v1/organizations/' + saved.id && response.request().method() === 'PATCH');
    await dialog.getByRole('button', { name: 'Save', exact: true }).click();
    const deactivatedResponse = await deactivation;
    assert.equal(deactivatedResponse.status(), 200);
    const deactivated = await deactivatedResponse.json();
    assert.equal(deactivated.id, saved.id);
    assert.equal(deactivated.code, saved.code);
    assert.equal(deactivated.created_at, saved.created_at);
    assert.equal(deactivated.active, false);
    await dialog.waitFor({ state: 'hidden' });
    await region.getByText('Organization was saved but is unavailable in the authorized inventory. Refresh or review customer access.', { exact: true }).waitFor();
    await region.getByLabel('Search organizations', { exact: true }).fill('LCTARGET');
    assert.equal(await region.getByRole('row').count(), 1);
    const inactiveRead = await page.request.get(api.origin + '/api/v1/organizations/' + saved.id, { headers });
    assert.equal(inactiveRead.status(), 404);
    report.checks.push('Deactivation response preserves identity; inactive customer leaves ALL and direct scoped read fails closed');

    phase = 'viewer-tenant-denial';
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.getByRole('button', { name: 'Sign out', exact: true }).click();
    await login('test-reader');
    region = await organizations();
    assert.equal(await region.getByRole('button', { name: 'Create Organization', exact: true }).count(), 0);
    await region.getByLabel('Search organizations', { exact: true }).fill('LCTARGET');
    assert.equal(await region.getByRole('row').count(), 1);
    const viewerToken = await page.evaluate(() => sessionStorage.getItem('opscontrol.sessionToken'));
    const deniedRead = await page.request.get(api.origin + '/api/v1/organizations/' + saved.id, { headers: { Authorization: 'Bearer ' + viewerToken } });
    assert.equal(deniedRead.status(), 404);
    const deniedWrite = await page.request.patch(api.origin + '/api/v1/organizations/' + saved.id, { headers: { Authorization: 'Bearer ' + viewerToken }, data: { name: 'forged' } });
    assert.ok([403, 404].includes(deniedWrite.status()));
    assert.deepEqual(errors, []);
    report.checks.push('Real viewer cannot create, list/read another customer or mutate its organization via direct API');
    report.status = 'PASS';
  } catch (error) {
    report.status = 'FAIL';
    report.phase = phase;
    report.category = error.name;
    await page.screenshot({ path: join(out, 'organization-lifecycle-failed.png'), fullPage: true });
    throw new Error('Organization lifecycle failed at ' + phase + ' (' + error.name + ')');
  } finally {
    await writeFile(join(out, 'organization-lifecycle.json'), JSON.stringify(report, null, 2));
    await context.close();
  }
}
