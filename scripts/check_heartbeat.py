"""Read-only probe for an independent host with its own alert destination.

The 15-minute window matched a daemon loop that rewrote the status file every
five minutes. That daemon stopped on 2026-09-23. GitHub Actions now publishes
the file, and a */5 schedule on this repository is often delayed by several
hours. Eight hours still reports a publisher that missed a couple of cycles.
"""
import sys
from datetime import datetime, timezone

# Keep in sync with site/src/lib/check-health.mjs HEARTBEAT_MAX_AGE_MS.
HEARTBEAT_MAX_AGE = 8 * 60 * 60


def healthy(value, now):
    try:
        updated = datetime.fromisoformat(value['updated_at'].replace('Z', '+00:00'))
        if updated.tzinfo is None:
            return False
        age = (now - updated).total_seconds()
        return (value['version'] == 1 and value['monitoring'] == 'ok' and -60 <= age <= HEARTBEAT_MAX_AGE
                and value.get('notification_failures') == 0)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def explain(value, now):
    if healthy(value, now):
        return ('CHECK_MONITOR_OK updated_at=%s monitoring=ok check_status=%s active_incidents=%s notification_failures=%s'
                % (value.get('updated_at'), value.get('check_status'), value.get('active_incidents'),
                   value.get('notification_failures')))
    reasons = []
    if isinstance(value, dict):
        if value.get('version') != 1:
            reasons.append('version')
        if value.get('monitoring') != 'ok':
            reasons.append('monitoring=' + str(value.get('monitoring'))[:32])
        try:
            updated = datetime.fromisoformat(str(value.get('updated_at')).replace('Z', '+00:00'))
            if updated.tzinfo is None:
                raise ValueError('TIMEZONE_REQUIRED')
            age = (now - updated).total_seconds()
            if age > HEARTBEAT_MAX_AGE:
                reasons.append('stale age=%d' % int(age))
            elif age < -60:
                reasons.append('future')
        except (TypeError, ValueError):
            reasons.append('updated_at')
        if value.get('notification_failures') != 0:
            reasons.append('notification_failures')
    return 'CHECK_MONITOR_UNAVAILABLE reason=' + (','.join(reasons) or 'unreadable')


def main():
    from .check_status import StatusError, default_repo, fetch_published, status_raw_url
    now = datetime.now(timezone.utc)
    try:
        value = fetch_published(default_repo())
        print(explain(value, now) + ' url=' + status_raw_url(default_repo()))
        ok = healthy(value, now)
    except StatusError as exc:
        print('CHECK_MONITOR_UNAVAILABLE reason=' + exc.code)
        ok = False
    return int(not ok)


if __name__ == '__main__':
    sys.exit(main())
