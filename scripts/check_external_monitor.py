"""Independent heartbeat with durable, bounded notification attempts.

Monitor health and extract/check failures are separate alerts. The status
document stays healthy while active_incidents is non-zero. This module pages
the existing Feishu webhook once per actionable incident id, after the same
extract/fetch source has failed on consecutive observations, and sends at
most one daily digest of what is still open. Acceptance lives in the
automation-state ledger under history.extract_incident_alerts.
"""
import argparse
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .check_state import GitState
from .check_status import default_repo, refresh_public_status
from .feishu_notifier import send_feishu_card

ALERT_KEY = 'extract_incident_alerts'
_INCIDENT = re.compile(
    r'(?:extract|fetch|call):[a-f0-9]{24}|workflow:update\.yml:(?:execution|running|schedule)\Z')
_MAX_INCIDENTS = 20
_RETRY_SECONDS = 900
_MAX_ATTEMPTS = 4
_WORKFLOW_EXECUTION = 'workflow:update.yml:execution'


def alert_min_streak():
    """Consecutive extract/fetch failures required before the first page.

    Unset, blank, or non-numeric values use 2. Values outside 1..20 clamp.
    """
    raw = os.environ.get('INCIDENT_ALERT_MIN_STREAK', '2').strip()
    if not raw:
        return 2
    try:
        value = int(raw)
    except ValueError:
        return 2
    return min(20, max(1, value))


def digest_enabled():
    """Daily digest defaults on. off/0/false/no disables it."""
    raw = os.environ.get('INCIDENT_DIGEST', 'on').strip().lower()
    if not raw or raw in {'on', '1', 'true', 'yes'}:
        return True
    if raw in {'off', '0', 'false', 'no'}:
        return False
    return True


def actionable_incidents(incidents):
    """Ids that need a person. pending_review, deferred, and dry-run are absent.

    discover.yml problems remain on the status page and do not page here.
    """
    found = []
    for item in incidents or []:
        if isinstance(item, str) and _INCIDENT.fullmatch(item) and item not in found:
            found.append(item)
    return sorted(found)[:_MAX_INCIDENTS]


def eligible_incidents(incidents, streaks, *, minimum, workflow_deferred=False):
    """Ids that should page now.

    streaks=None means the caller did not measure observations, so every
    actionable id is eligible (the previous once-per-id behavior). A measured
    extract/fetch streak pages only at `minimum`. Calls and update.yml
    workflow ids page on first sight. A deferred pause drops execution only.
    """
    ready = []
    for item in actionable_incidents(incidents):
        if workflow_deferred and item == _WORKFLOW_EXECUTION:
            continue
        if streaks is not None and item.startswith(('extract:', 'fetch:')):
            count = streaks.get(item) if isinstance(streaks, dict) else None
            if isinstance(count, int) and not isinstance(count, bool) and count < minimum:
                continue
        ready.append(item)
    return ready


def digest_incidents(incidents, *, workflow_deferred=False):
    """Open actionable ids for the daily card, including those still below the streak."""
    found = actionable_incidents(incidents)
    if workflow_deferred:
        found = [item for item in found if item != _WORKFLOW_EXECUTION]
    return found


def _card(title, content):
    return {'msg_type': 'interactive', 'card': {'header': {'title': {'tag': 'plain_text', 'content': title}},
            'elements': [{'tag': 'div', 'text': {'tag': 'plain_text', 'content': content[:600]}}]}}


def _repo_slug():
    try:
        return default_repo()
    except Exception:
        return 'kimhero110/freetoken'


def _utc_day(now):
    return datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m-%d')


def _alert_book(state):
    book = state['history'].get(ALERT_KEY)
    if not isinstance(book, dict):
        book = {}
        state['history'][ALERT_KEY] = book
    if not isinstance(book.get('open'), dict):
        book['open'] = {}
    return book


def notify_incidents(store, incidents, send, *, now=None, streaks=None, workflow_deferred=False, minimum=None):
    """Page once for eligible ids not yet accepted. Return 1 when that send fails."""
    now = time.time() if now is None else now
    minimum = alert_min_streak() if minimum is None else minimum
    ready = eligible_incidents(incidents, streaks, minimum=minimum, workflow_deferred=workflow_deferred)
    waiting = [item for item in actionable_incidents(incidents) if item not in ready]
    current = set(ready)
    owner = uuid.uuid4().hex

    def reserve(state):
        book = state['history'].get(ALERT_KEY)
        if (not isinstance(book, dict) or not isinstance(book.get('open'), dict)) and not current:
            return None
        book = _alert_book(state)
        open_map = book['open']
        for key in list(open_map):
            if key not in current:
                open_map.pop(key, None)
        due = []
        for key in sorted(current):
            record = open_map.get(key)
            if not isinstance(record, dict):
                record = {'accepted': False, 'attempts': 0, 'next': now, 'event': uuid.uuid4().hex}
                open_map[key] = record
            if record.get('accepted') or record.get('attempts', 0) >= _MAX_ATTEMPTS or record.get('next', 0) > now:
                continue
            record.update(owner=owner, attempts=record.get('attempts', 0) + 1, next=now + _RETRY_SECONDS)
            due.append(key)
        return due or None

    claimed = store.update(reserve)
    if not claimed:
        if waiting and not ready:
            print('INCIDENT_ALERT waiting %d' % len(waiting))
        else:
            print('INCIDENT_ALERT idle')
        return 0
    shown = claimed[:8]
    extra = len(claimed) - len(shown)
    content = '提取或检查出现需要人工处理的新故障（%d）：%s' % (len(claimed), ', '.join(shown))
    if extra:
        content += '，以及另外 %d 个' % extra
    content += '。extract 和 fetch 要同一来源连续失败满 %d 次才发这张卡片；工作流和未决调用看到就发。' % minimum
    content += '发出后编号消失前不重复。待审 pending_review、延期和未付费干跑不会告警。'
    content += ' https://github.com/%s/actions/workflows/update.yml' % _repo_slug()
    try:
        accepted = bool(send(_card('FreeToken 检查失败', content)))
    except Exception:
        accepted = False

    def finish(state):
        book = state['history'].get(ALERT_KEY)
        if not isinstance(book, dict) or not isinstance(book.get('open'), dict):
            return None
        for key in claimed:
            record = book['open'].get(key)
            if isinstance(record, dict) and record.get('owner') == owner:
                record['accepted'] = accepted
        return None

    store.update(finish)
    print('INCIDENT_ALERT sent' if accepted else 'INCIDENT_ALERT retry')
    return 0 if accepted else 1


def _digest_card(incidents, streaks, minimum):
    streaks = streaks if isinstance(streaks, dict) else {}
    shown = incidents[:8]
    parts = []
    waiting = 0
    for item in incidents:
        count = streaks.get(item)
        below = (item.startswith(('extract:', 'fetch:')) and isinstance(count, int)
                 and not isinstance(count, bool) and count < minimum)
        if below:
            waiting += 1
        if item in shown:
            parts.append('%s×%d' % (item, count) if isinstance(count, int) and not isinstance(count, bool) else item)
    extra = len(incidents) - len(shown)
    content = '仍打开的检查故障 %d 个，其中 %d 个还没连续失败满 %d 次，只写在日报里：%s' % (
        len(incidents), waiting, minimum, '，'.join(parts))
    if extra:
        content += '，以及另外 %d 个' % extra
    content += '。已单独告警的编号不会因为这份日报再响一次。待审 pending_review、延期和未付费干跑不列入。'
    content += ' https://github.com/%s/actions/workflows/update.yml' % _repo_slug()
    return _card('FreeToken 检查日报', content)


def notify_digest(store, incidents, send, *, now=None, streaks=None, workflow_deferred=False, minimum=None, enabled=None):
    """One summary card per UTC day while an actionable incident is open.

    Return 1 when that send fails. An empty day sends nothing.
    """
    if enabled is None:
        enabled = digest_enabled()
    if not enabled:
        print('INCIDENT_DIGEST off')
        return 0
    now = time.time() if now is None else now
    minimum = alert_min_streak() if minimum is None else minimum
    current = digest_incidents(incidents, workflow_deferred=workflow_deferred)
    day = _utc_day(now)
    if not current:
        def clear(state):
            book = state['history'].get(ALERT_KEY)
            digest = book.get('digest') if isinstance(book, dict) else None
            if isinstance(digest, dict) and not digest.get('accepted'):
                book.pop('digest', None)
            return None
        store.update(clear)
        print('INCIDENT_DIGEST idle')
        return 0
    owner = uuid.uuid4().hex

    def reserve(state):
        book = _alert_book(state)
        record = book.get('digest')
        if not isinstance(record, dict) or record.get('day') != day:
            record = {'day': day, 'accepted': False, 'attempts': 0, 'next': now, 'event': uuid.uuid4().hex}
            book['digest'] = record
        if record.get('accepted') or record.get('attempts', 0) >= _MAX_ATTEMPTS or record.get('next', 0) > now:
            return None
        record.update(owner=owner, attempts=record.get('attempts', 0) + 1, next=now + _RETRY_SECONDS)
        return dict(record)

    claimed = store.update(reserve)
    if not claimed:
        print('INCIDENT_DIGEST idle')
        return 0
    try:
        accepted = bool(send(_digest_card(current, streaks, minimum)))
    except Exception:
        accepted = False

    def finish(state):
        book = state['history'].get(ALERT_KEY)
        record = book.get('digest') if isinstance(book, dict) else None
        if isinstance(record, dict) and record.get('owner') == owner and record.get('day') == day:
            record['accepted'] = accepted
        return None

    store.update(finish)
    print('INCIDENT_DIGEST sent' if accepted else 'INCIDENT_DIGEST retry')
    return 0 if accepted else 1


def run(store, is_healthy, send, *, now=None, exercise=False, detail=''):
    now = time.time() if now is None else now
    key = 'external_heartbeat_test' if exercise else 'external_heartbeat'
    owner = uuid.uuid4().hex
    def reserve(state):
        previous = state['history'].get(key)
        if previous is None and is_healthy:
            state['history'][key] = {'healthy': True, 'accepted': True, 'attempts': 0, 'next': now}
            return None
        if previous is None or previous['healthy'] != is_healthy:
            previous = {'healthy': is_healthy, 'accepted': False, 'attempts': 0, 'next': now, 'event': uuid.uuid4().hex}
            state['history'][key] = previous
        if previous['accepted'] or previous['attempts'] >= 4 or previous['next'] > now:
            return None
        previous.update(owner=owner, attempts=previous['attempts'] + 1, next=now + 900)
        return dict(previous)
    record = store.update(reserve)
    if record:
        title = 'FreeToken 外部心跳' + ('联调' if exercise else '') + ('恢复' if is_healthy else '异常')
        content = '检查主监控可达性、心跳新鲜度和通知健康。事件：' + record['event']
        if detail:
            content += '\n' + detail.replace('\n', ' ')[:400]
        payload = {'msg_type': 'interactive', 'card': {'header': {'title': {'tag': 'plain_text', 'content': title}},
                   'elements': [{'tag': 'div', 'text': {'tag': 'plain_text', 'content': content}}]}}
        try:
            accepted = bool(send(payload))
        except Exception:
            accepted = False
        def finish(state):
            current = state['history'][key]
            if current.get('owner') == owner:
                current['accepted'] = accepted
        store.update(finish)
        if not accepted:
            return 1
    return 0 if is_healthy or exercise else 1


def execute(state, *, exercise, refresh, send, now=None):
    detail = ''
    incidents = []
    context = {}
    if exercise == 'none':
        result = refresh()
        ok, detail, incidents = result[0], result[1], result[2]
        if len(result) > 3 and isinstance(result[3], dict):
            context = result[3]
        print(detail)
    else:
        ok = exercise == 'recovery'
    code = run(state, ok, send, now=now, exercise=exercise != 'none', detail=detail)
    if exercise == 'none':
        streaks = context.get('streaks')
        deferred = bool(context.get('workflow_deferred'))
        if notify_incidents(state, incidents, send, now=now, streaks=streaks, workflow_deferred=deferred):
            code = 1
        if notify_digest(state, incidents, send, now=now, streaks=streaks, workflow_deferred=deferred):
            code = 1
    return code


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--exercise', choices=['none', 'failure', 'recovery'], default='none')
    args = parser.parse_args(argv)
    state = GitState(Path(__file__).resolve().parents[1])
    return execute(state, exercise=args.exercise, refresh=lambda: refresh_public_status(state.repo), send=send_feishu_card)


if __name__ == '__main__':
    raise SystemExit(main())
