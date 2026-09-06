import test from 'node:test';
import assert from 'node:assert/strict';
import { describeCheckHealth } from '../src/lib/check-health.mjs';

const now = Date.parse('2026-09-06T10:00:00Z');
const valid = {version: 1, monitoring: 'ok', updated_at: '2026-09-06T09:59:00Z',
  last_check_at: '2026-09-06T09:00:00Z', attempted: 4, succeeded: 4,
  active_incidents: 0, check_status: 'completed'};
test('stale, future, missing and invalid status cannot claim health', () => {
  for (const input of [null, {}, {...valid, updated_at: '2026-09-06T09:00:00Z'},
    {...valid, monitoring: 'unknown'}, {...valid, succeeded: 5},
    {...valid, updated_at: '2026-09-07T10:00:00Z'}]) {
    assert.match(describeCheckHealth(input, true, now), /status unknown/);
  }
});
test('coverage is not entire directory verification', () => {
  const text = describeCheckHealth(valid, true, now);
  assert.match(text, /4\/4 sources fetched/);
  assert.doesNotMatch(text, /verified/);
});
test('dry run and outstanding incidents stay visible', () => {
  assert.match(describeCheckHealth({...valid, check_status: 'dry_run'}, true, now), /dry run/);
  assert.match(describeCheckHealth({...valid, active_incidents: 1}, true, now), /needs attention/);
});


test('deployed CSP permits the exact telemetry endpoint', async () => {
  const { readFile } = await import('node:fs/promises');
  const headers = await readFile(new URL('../public/_headers', import.meta.url), 'utf8');
  const component = await readFile(new URL('../src/components/TelemetrySweep.astro', import.meta.url), 'utf8');
  const endpoint = component.match(/fetch\('([^']+)'/)[1];
  const connect = headers.match(/connect-src ([^;]+)/)[1].split(/\s+/);
  assert.ok(connect.includes(endpoint));
  assert.ok(!connect.includes('*'));
});
