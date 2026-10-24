"""Independent heartbeat with durable, bounded notification attempts.

Monitor health and extract/check failures are separate alerts. The status
document stays healthy while active_incidents is non-zero; this module pages
the existing Feishu webhook once per new actionable incident id and remembers
that acceptance in the automation-state ledger.
"""
import argparse
import re
import time
import uuid
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


def actionable_incidents(incidents):
    """Ids that need a person. pending_review, deferred, and dry-run are absent.

    discover.yml problems remain on the status page and do not page here.
    """
    found = []
    for item in incidents or []:
        if isinstance(item, str) and _INCIDENT.fullmatch(item) and item not in found:
            found.append(item)
    return sorted(found)[:_MAX_INCIDENTS]


def _card(title, content):
    return {'msg_type': 'interactive', 'card': {'header': {'title': {'tag': 'plain_text', 'content': title}},
            'elements': [{'tag': 'div', 'text': {'tag': 'plain_text', 'content': content[:600]}}]}}


def _repo_slug():
    try:
        return default_repo()
    except Exception:
        return 'kimhero110/freetoken'


def notify_incidents(store, incidents, send, *, now=None):
    """Page once for incident ids not yet accepted. Return 1 when that send fails."""
    now = time.time() if now is None else now
    current = set(actionable_incidents(incidents))
    owner = uuid.uuid4().hex

    def reserve(state):
        book = state['history'].get(ALERT_KEY)
        if not isinstance(book, dict) or not isinstance(book.get('open'), dict):
            if not current:
                return None
            book = {'open': {}}
            state['history'][ALERT_KEY] = book
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
        print('INCIDENT_ALERT idle')
        return 0
    shown = claimed[:8]
    extra = len(claimed) - len(shown)
    content = '提取或检查出现需要人工处理的新故障（%d）：%s' % (len(claimed), ', '.join(shown))
    if extra:
        content += '，以及另外 %d 个' % extra
    content += '。同一编号在从状态消失前只告警一次。待审 pending_review、延期和未付费干跑不会告警。'
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
    if exercise == 'none':
        ok, detail, incidents = refresh()
        print(detail)
    else:
        ok = exercise == 'recovery'
    code = run(state, ok, send, now=now, exercise=exercise != 'none', detail=detail)
    if exercise == 'none' and notify_incidents(state, incidents, send, now=now):
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
