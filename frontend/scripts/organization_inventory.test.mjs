import assert from 'node:assert/strict';
import test from 'node:test';
import { organizationPage, organizationPageFor } from '../src/organizationInventory.js';

const rows = Array.from({ length: 53 }, (_, index) => ({
  id: `customer-${index}`, name: `Customer ${String(index).padStart(2, '0')}`,
  code: `C${index}`, active: index % 2 === 0,
}));

test('saving an organization beyond page one reveals its exact persisted identity', () => {
  const saved = { id: 'saved-customer', name: 'ZZ saved customer', code: 'ZZ', active: false };
  const inventory = [...rows, saved];
  const page = organizationPage(inventory, { page: organizationPageFor(inventory, saved.id) });
  assert.equal(page.page, 2);
  assert.deepEqual(page.visible.find(row => row.id === saved.id), saved);
  assert.deepEqual([page.start, page.end, page.total], [51, 54, 54]);
});

test('inactive status and identity search combine without changing the authorized records', () => {
  const before = structuredClone(rows);
  assert.deepEqual(organizationPage(rows, { status: 'inactive', query: ' c51 ' }).visible, [rows[51]]);
  assert.equal(organizationPage(rows, { status: 'active', query: 'customer-51' }).total, 0);
  assert.equal(organizationPage(rows, { status: 'all' }).total, 53);
  assert.deepEqual(rows, before);
});

test('filtering or revocation while on a later page never leaves an empty invalid page', () => {
  const filtered = organizationPage(rows, { status: 'inactive', page: 2 });
  assert.equal(filtered.page, 1);
  assert.deepEqual(filtered.visible.map(row => row.id), ['customer-51']);
  const revoked = organizationPage([], { page: 2 });
  assert.deepEqual([revoked.page, revoked.start, revoked.end, revoked.total], [0, 0, 0, 0]);
  assert.deepEqual(revoked.visible, []);
  assert.equal(organizationPageFor(rows, 'not-authorized'), 0);
});

test('saved organization moves to its new page after a rename without duplicating or dropping rows', () => {
  const renamed = rows.map(row => row.id === 'customer-0' ? { ...row, name: 'ZZ renamed' } : row)
    .sort((a, b) => a.name.localeCompare(b.name));
  const page = organizationPage(renamed, { page: organizationPageFor(renamed, 'customer-0') });
  assert.equal(page.visible.at(-1).id, 'customer-0');
  assert.equal(page.total, rows.length);
  assert.equal(renamed.filter(row => row.id === 'customer-0').length, 1);
});
