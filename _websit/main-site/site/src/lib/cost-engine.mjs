// Money is stored in trillionths of the native currency. No binary floats.
const SCALE = 1_000_000n;
export function decimal(value) {
  if (typeof value !== 'string' || !/^\d{1,12}(\.\d{1,6})?$/.test(value)) throw new Error('decimal');
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole) * SCALE + BigInt(fraction.padEnd(6, '0'));
}
function tokens(value) {
  if (typeof value !== 'string' || !/^\d{1,15}$/.test(value)) throw new Error('tokens');
  return BigInt(value);
}
export function estimate({ input, cached, output, rates, credit = '0' }) {
  const i = tokens(input), c = tokens(cached), o = tokens(output);
  if (c > i) throw new Error('cache');
  const part = (count, rate) => count === 0n ? 0n : rate == null ? null : count * decimal(rate);
  const parts = [part(i - c, rates.input), part(c, rates.cached), part(o, rates.output)];
  const allowance = decimal(credit) * SCALE;
  if (parts.includes(null)) return { gross: null, net: null, parts };
  const gross = parts.reduce((a, b) => a + b, 0n);
  return { gross, net: gross > allowance ? gross - allowance : 0n, parts };
}
export function formatMoney(value) {
  if (value === null) return '—';
  const rounded = (value + 500_000n) / SCALE;
  return `${rounded / SCALE}.${(rounded % SCALE).toString().padStart(6, '0')}`;
}
export function convert(value, fx) {
  const rate = decimal(fx);
  if (!rate) throw new Error('fx');
  return value === null ? null : (value * rate + SCALE / 2n) / SCALE;
}
export function compareQuotes(a, b) {
  if (a.model !== b.model || a.currency !== b.currency || a.cost === null || b.cost === null) return null;
  return a.cost === b.cost ? 0 : a.cost < b.cost ? -1 : 1;
}
