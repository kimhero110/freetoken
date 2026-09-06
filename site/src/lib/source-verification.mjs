export function describeSourceVerification(health, slug, english = false, now = Date.now()) {
  const unknown = english ? 'Automatic source check: unknown' : '来源自动核验：暂无可确认记录';
  const heartbeat = Date.parse(health?.updated_at);
  if (health?.monitoring !== 'ok' || health?.version !== 1 || !Number.isFinite(heartbeat) || now - heartbeat > 900000 || heartbeat > now + 60000) return unknown;
  const sources = Array.isArray(health.sources) ? health.sources.filter(s => s.platform === slug) : [];
  if (!sources.length) return unknown;
  const stamps = sources.map(s => Date.parse(s.checked_at));
  if (stamps.some(t => !Number.isFinite(t) || t > now + 60000)) return unknown;
  const oldest = Math.min(...stamps);
  const date = new Date(oldest).toLocaleString(english ? 'en-US' : 'zh-CN');
  if (now - oldest > 48 * 3600000) return english ? `Source check overdue; last ${date}` : `来源检查已过期；上次 ${date}`;
  if (sources.some(s => s.status === 'fetch_failed')) return english ? `Unable to verify all sources · ${date}` : `部分来源暂无法核验 · ${date}`;
  if (sources.every(s => s.status === 'verified_unchanged')) return english ? `Reviewed sources unchanged · ${date} (not an API test)` : `已审核来源未变 · ${date}（非 API 实测）`;
  if (sources.some(s => s.status === 'reviewed_rejected')) return english ? `Source version previously rejected · ${date}` : `包含已拒绝来源版本 · ${date}`;
  return english ? `Source fetched; changes need review · ${date}` : `已抓取，变更待核对 · ${date}`;
}
