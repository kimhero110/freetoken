import { decimal } from './cost-engine.mjs';
export function validatePricebook(book) {
  if (!/^\d{4}-\d{2}-\d{2}\.\d+$/.test(book.version) || book.unit !== 'per_million_tokens' || !Array.isArray(book.records) || !book.records.length) throw new Error('Invalid pricebook');
  const seen = new Set();
  for (const r of book.records) {
    if (!/^[a-z0-9-]+$/.test(r.platform) || typeof r.model !== 'string' || !r.model || typeof r.revision !== 'string' || !r.revision || !['USD', 'CNY'].includes(r.currency) || r.evidence !== 'documented') throw new Error('Invalid record');
    const url = new URL(r.source);
    if (url.protocol !== 'https:' || url.username || url.password) throw new Error('Invalid source');
    // Evidence dates follow the editorial team's Asia/Shanghai calendar.
    const today = new Date(Date.now() + 8 * 3600000).toISOString().slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(r.checked_at) || new Date(r.checked_at).toISOString().slice(0, 10) !== r.checked_at || r.checked_at > today) throw new Error('Invalid date');
    const key = `${r.platform}:${r.model}`;
    if (seen.has(key)) throw new Error('Duplicate model');
    seen.add(key);
    for (const period of ['peak', 'offpeak']) for (const rate of ['input', 'cached', 'output']) {
      if (!Object.hasOwn(r[period], rate)) throw new Error('Missing rate');
      if (r[period][rate] !== null) decimal(r[period][rate]);
    }
  }
  return book;
}
