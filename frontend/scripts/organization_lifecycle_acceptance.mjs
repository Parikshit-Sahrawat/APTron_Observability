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
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await page.getByRole('navigation', { name: 'Primary navigation' }).waitFor();
  }
  async function organizations() {
    await page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('button', { name: 'Organizations', exact: true }).click();
    const region = page.getByRole('region', { name: 'Monitored customer organizations' });
    await region.getByRole('heading', { name: 'Organizations', exact: true }).waitFor();
    await region.getByText('Loading Resource Management', { exact: true }).waitFor({ state: 'hidden' });
    return region;
  }
  try {
    await page.goto(ui.href);
    await login('test-admin');
    const token = await page.evaluate(() => sessionStorage.getItem('opscontrol.sessionToken'));
    const headers = { Authorization: 'Bearer ' + token };
    phase = 'seed-real-pagination';
    for (let index = 0; index < 26; index++) {
      const response = await page.request.post(api.origin + '/api/v1/organizations', {
        headers, data: { name: 'APTron lifecycle seed ' + String(index).padStart(2, '0'), code: 'LCSEED' + index, active: index % 2 === 0 },
      });
      assert.equal(response.status(), 201);
    }
    let region = await organizations();
    const search = region.getByLabel('Search organizations', { exact: true });
    const status = region.getByLabel('Organization status', { exact: true });
    phase = 'combined-status-search-pagination';
    await search.fill('APTron lifecycle seed');
    await status.selectOption('active');
    assert.equal(await region.getByRole('row').count(), 14);
    await status.selectOption('inactive');
    assert.equal(await region.getByRole('row').count(), 14);
    await status.selectOption('all');
    assert.equal(await region.getByRole('row').count(), 26);
    await region.getByRole('button', { name: 'Next', exact: true }).click();
    assert.equal(await region.getByRole('row').count(), 2);
    report.checks.push('26 real organizations: combined active/inactive search and both inventory pages');

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
    let saved;
    const routePattern = '**/api/v1/organizations';
    await page.route(routePattern, async route => {
      if (route.request().method() !== 'POST') return route.continue();
      posts++;
      if (posts !== 1) return route.continue();
      try {
        const response = await route.fetch();
        assert.equal(response.status(), 201);
        saved = await response.json();
        captured();
        await held;
        await route.fulfill({ response });
      } catch (error) {
        rejected(error);
        await route.abort();
      }
    });
    try {
      await dialog.getByRole('button', { name: 'Save', exact: true }).click();
      await received;
      assert.equal(await dialog.getByRole('button', { name: 'Saving…', exact: true }).isDisabled(), true);
      // Reentrant native submit while the unchanged real server response is held.
      await dialog.locator('form').evaluate(form => form.requestSubmit());
      await dialog.getByRole('button', { name: 'Close resource dialog', exact: true }).click();
      await page.keyboard.press('Escape');
      assert.equal(await dialog.isVisible(), true);
      release();
      await dialog.waitFor({ state: 'hidden' });
      await region.getByRole('row').filter({ hasText: 'ZZ APTron lifecycle target' }).waitFor();
    } finally {
      release();
      await page.unroute(routePattern);
    }
    assert.equal(posts, 1);
    assert.equal(await search.inputValue(), '');
    assert.equal(await status.inputValue(), 'all');
    assert.equal(await region.getByRole('button', { name: 'Previous', exact: true }).isEnabled(), true);
    report.checks.push('Real create reveals saved ID beyond page one despite old search/status; pending form rejects duplicate submit and close');

    phase = 'rename-deactivate-preserve';
    await search.fill('ZZ APTron lifecycle target');
    await region.getByRole('row').filter({ hasText: 'ZZ APTron lifecycle target' }).getByRole('button', { name: 'Edit', exact: true }).click();
    dialog = page.getByRole('dialog', { name: 'Edit Organization', exact: true });
    await dialog.getByLabel('Organization Name').fill('A APTron lifecycle renamed');
    await dialog.getByLabel('Active customer', { exact: true }).uncheck();
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
    assert.equal(persisted.active, false);
    await page.reload();
    region = await organizations();
    await region.getByRole('row').filter({ hasText: 'A APTron lifecycle renamed' }).waitFor();
    await region.getByLabel('Search organizations', { exact: true }).fill('LCTARGET');
    await region.getByLabel('Organization status', { exact: true }).selectOption('active');
    assert.equal(await region.getByRole('row').count(), 1);
    await region.getByLabel('Organization status', { exact: true }).selectOption('inactive');
    assert.equal(await region.getByRole('row').count(), 2);
    report.checks.push('Rename/deactivation retains canonical ID, code and creation time; reload and combined filters show persisted state');

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
        assert.equal(await dialog.getByLabel('Active customer', { exact: true }).isChecked(), false);
        const box = await dialog.boundingBox();
        assert.ok(box.x >= 0 && box.x + box.width <= width + 1);
        assert.ok(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth + 1));
        await page.screenshot({ path: join(out, `organizations-${mode.toLowerCase()}-${width}.png`), fullPage: true });
        await page.keyboard.press('Escape');
        await dialog.waitFor({ state: 'hidden' });
      }
    }
    report.checks.push('Persisted edit form is contained at desktop/tablet/mobile in both themes; Escape closes idle dialog');

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
