"""Read-only probe for an independent host with its own alert destination."""
import json
import sys
from datetime import datetime, timezone
from urllib.request import urlopen, Request


def healthy(value, now):
    try:
        updated = datetime.fromisoformat(value['updated_at'].replace('Z', '+00:00'))
        if updated.tzinfo is None:
            return False
        age = (now - updated).total_seconds()
        return (value['version'] == 1 and value['monitoring'] == 'ok' and -60 <= age <= 900
                and value.get('notification_failures') == 0)
    except (KeyError, TypeError, ValueError):
        return False


def main():
    try:
        request = Request('https://witkit.zone/ops/check-status.json', headers={'Cache-Control': 'no-cache'})
        with urlopen(request, timeout=10) as response:
            raw = response.read(8193)
            if len(raw) > 8192:
                return 1
        ok = healthy(json.loads(raw), datetime.now(timezone.utc))
    except Exception:
        ok = False
    print('CHECK_MONITOR_OK' if ok else 'CHECK_MONITOR_UNAVAILABLE')
    return int(not ok)


if __name__ == '__main__':
    sys.exit(main())
