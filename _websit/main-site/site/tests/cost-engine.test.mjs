import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { estimate, formatMoney, convert, decimal, compareQuotes } from '../src/lib/cost-engine.mjs';
import { validatePricebook } from '../src/lib/pricebook.mjs';
const base = { input: '1000000', cached: '0', output: '1000000', rates: { input: '0.44', cached: '0.014', output: '1.32' } };
test('documented monthly rates and cache partition', () => {
  assert.equal(formatMoney(estimate(base).gross), '1.760000');
  assert.equal(formatMoney(estimate({ ...base, cached: '1000000' }).gross), '1.334000');
  assert.equal(formatMoney(estimate({ ...base, cached: '500000' }).gross), '1.547000');
});
test('unknown is not free, unless the unknown price has no usage', () => {
  const rates = { ...base.rates, cached: null };
  assert.equal(estimate({ ...base, rates, cached: '1' }).net, null);
  assert.equal(formatMoney(estimate({ ...base, rates }).net), '1.760000');
});
test('credit is capped at cost and exchange is explicit', () => {
  assert.equal(formatMoney(estimate({ ...base, credit: '1' }).net), '0.760000');
  assert.equal(estimate({ ...base, credit: '100' }).net, 0n);
  assert.equal(formatMoney(convert(estimate(base).net, '7.1')), '12.496000');
  assert.throws(() => convert(1n, '0'));
});
test('reject invalid, negative, exponential, overflow and fractional token inputs', () => {
  for (const input of ['-1', '1.1', '1e6', '', 'NaN', '1000000000000000']) assert.throws(() => estimate({ ...base, input }));
  assert.throws(() => estimate({ ...base, cached: '1000001' }));
  for (const value of ['-1', '1e3', '0.0000001', '1000000000000', 'Infinity']) assert.throws(() => decimal(value));
});
test('exact arithmetic retains small and large token charges', () => {
  const small = estimate({ input: '1', cached: '0', output: '0', rates: { input: '0.000001' } });
  assert.equal(small.gross, 1n);
  const big = estimate({ input: '999999999999999', cached: '0', output: '0', rates: { input: '999999999999.999999' } });
  assert.equal(big.gross, 999999999999999n * 999999999999999999n);
});
test('comparison uses actual workload and refuses different currencies/models', () => {
  const usage = { input: '1000000', cached: '0', output: '10000000' };
  const a = { model: 'same-revision', currency: 'USD', cost: estimate({ ...usage, rates: { input: '1', output: '8' } }).net };
  const b = { ...a, cost: estimate({ ...usage, rates: { input: '6', output: '4' } }).net };
  assert.equal(formatMoney(a.cost), '81.000000'); assert.equal(formatMoney(b.cost), '46.000000');
  assert.equal(compareQuotes(a, b), 1);
  assert.equal(compareQuotes(a, { ...b, currency: 'CNY' }), null);
  assert.equal(compareQuotes(a, { ...b, model: 'other' }), null);
  assert.equal(compareQuotes(a, { ...b, cost: null }), null);
});
test('pricebook validates evidence, decimals, dates and unique identity', () => {
  const book = JSON.parse(readFileSync(new URL('../../data/pricing/pricebook.json', import.meta.url)));
  assert.equal(validatePricebook(book), book);
  for (const mutate of [r => r.peak.input = -1, r => r.source = 'http://example.com', r => r.checked_at = '2026-02-30', r => r.currency = 'INVALID', r => delete r.peak.input]) {
    const copy = structuredClone(book); mutate(copy.records[0]); assert.throws(() => validatePricebook(copy));
  }
  assert.throws(() => validatePricebook({ ...book, records: [book.records[0], book.records[0]] }));
});
