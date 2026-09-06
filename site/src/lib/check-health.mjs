export function describeCheckHealth(value, english = false, now = Date.now()) {
  const unknown = english ? 'Automatic check: status unknown' : '自动检查：状态暂不可确认';
  if (!value || typeof value !== 'object') return unknown;
  const s = value;
  const updated = typeof s.updated_at === 'string' ? Date.parse(s.updated_at) : NaN;
  if (s.version !== 1 || s.monitoring !== 'ok' || !Number.isFinite(updated) || now - updated > 900000 || updated - now > 60000) return unknown;
  const checked = typeof s.last_check_at === 'string' ? Date.parse(s.last_check_at) : NaN;
  if (!Number.isFinite(checked) || checked > now + 60000 || !Number.isInteger(s.attempted) || !Number.isInteger(s.succeeded)) return unknown;
  const attempted = s.attempted, succeeded = s.succeeded;
  if (attempted < 0 || succeeded < 0 || succeeded > attempted || attempted > 10000) return unknown;
  const time = new Date(checked).toLocaleString(english ? 'en-US' : 'zh-CN');
  const abnormal = (typeof s.active_incidents === 'number' && s.active_incidents > 0) || s.check_status === 'failed';
  const label = s.check_status === 'dry_run' ? (english ? 'dry run' : '干跑，未提取') : abnormal ? (english ? 'needs attention' : '有异常待处理') : (english ? 'source check' : '来源检查');
  return english ? `${label}: ${time}, ${succeeded}/${attempted} sources fetched` : `${label}：${time}，成功抓取 ${succeeded}/${attempted} 个来源`;
}
