"""Independent heartbeat with durable, bounded notification attempts."""
import argparse
import time
import uuid
from pathlib import Path
from .check_state import GitState
from .check_status import refresh_public_status
from .feishu_notifier import send_feishu_card


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exercise', choices=['none', 'failure', 'recovery'], default='none')
    args = parser.parse_args()
    state = GitState(Path(__file__).resolve().parents[1])
    detail = ''
    if args.exercise == 'none':
        ok, detail = refresh_public_status(state.repo)
        print(detail)
    else:
        ok = args.exercise == 'recovery'
    return run(state, ok, send_feishu_card, exercise=args.exercise != 'none', detail=detail)


if __name__ == '__main__':
    raise SystemExit(main())
