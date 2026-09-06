"""Read-only workflow/ledger monitoring, separate from approval cancellation."""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .alert_store import AlertStore
from . import cards

log = logging.getLogger('check-monitor')


def stamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return parsed.timestamp()


def expected_slots(workflow, start, now):
    day = datetime.fromtimestamp(start, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    while day.timestamp() <= now:
        hours = (17, 20, 23) if workflow == 'update.yml' else ((18,) if day.day % 2 == 1 else ())
        for hour in hours:
            slot = day.replace(hour=hour, minute=30).timestamp()
            if start <= slot <= now:
                yield slot
        day += timedelta(days=1)


def missing_slots(workflow, runs, start, now):
    scheduled = [r for r in runs if r.get('event') == 'schedule' and r.get('head_branch') == 'main']
    return [slot for slot in expected_slots(workflow, start, now - 10800)
            if not any(slot <= stamp(r['created_at']) < slot + 10800 for r in scheduled)]


def public_ledger(repo):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('REPO_INVALID')
    # Use public API raw media; no credentials or raw-host dependency.
    url = f'https://api.github.com/repos/{repo}/contents/state.json?ref=automation-state'
    with requests.get(url, timeout=(5, 15), stream=True, allow_redirects=False,
                      headers={'Cache-Control': 'no-cache', 'Accept': 'application/vnd.github.raw+json',
                               'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'freetoken-check-monitor'}) as response:
        if response.status_code != 200:
            raise RuntimeError('LEDGER_UNAVAILABLE')
        content = bytearray()
        for chunk in response.iter_content(8192):
            content.extend(chunk)
            if len(content) > 8_000_000:
                raise ValueError('LEDGER_TOO_LARGE')
    data = json.loads(content)
    if not isinstance(data, dict) or data.get('version') != 1 or not all(isinstance(data.get(k), dict) for k in ('runs', 'calls', 'history')):
        raise ValueError('LEDGER_SCHEMA')
    return data


class CheckMonitor:
    def __init__(self, gh, feishu, config):
        self.gh, self.feishu, self.config = gh, feishu, config
        self.started = stamp(config['check_monitor_since'])
        self.status_file = Path(config['check_status_path'])
        self.store = AlertStore(config['check_alert_db'])
        self.stop = threading.Event()

    def start(self):
        threading.Thread(target=self.loop, name='check-monitor', daemon=True).start()

    def write_health(self, value):
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.status_file.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8') as file:
            json.dump(value, file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, self.status_file)

    def deliver(self, now):
        for _ in range(8):
            item = self.store.claim(now)
            if not item:
                break
            event, payload, attempts = item
            if payload.get('kind') == 'candidate':
                card = cards._card('待审核 · ' + payload['name'], 'orange',
                                   cards.lark_escape(payload['summary']),
                                   buttons=[cards.publish_button(payload['candidate_id']),
                                            cards._button('完整候选与来源', f"https://github.com/{self.config['github_repo']}/blob/main/data/candidates/{payload['candidate_id']}.yaml")])
            else:
                # Payload contains only fixed codes / locally constructed IDs, not API text.
                card = cards.error_card('定时检查异常' if payload['active'] else '定时检查恢复',
                                        f"{payload['incident']} · {payload['code']} · 事件 {event}",
                                        f"请核对 https://github.com/{self.config['github_repo']}/actions 。重复事件编号表示通知重试；未自动重发模型请求。")
            try:
                message_id = self.feishu.send_card(self.config['owner_open_id'], card, receive_id_type='open_id')
                self.store.finish(event, attempts, now, message_id=message_id)
            except Exception:
                self.store.finish(event, attempts, now, unknown=True)

    def queue_candidates(self, now):
        from .candidate_notifications import newest_candidates, source_is_current
        candidates = [(name, data) for name, data in newest_candidates(self.gh, self.config['github_repo'], now)
                      if source_is_current(data, getattr(self, 'source_observations', []), now)]
        self.store.supersede_candidates({candidate_id for candidate_id, _ in candidates})
        for candidate_id, data in candidates:
            summary = ('自动抓取已完成；请核对以下变更后点击直接发布。旧版本批准不继承。\n'
                       + json.dumps({'当前': data.get('current'), '建议': data.get('proposed'),
                                     '来源': data.get('source_url'), '采集时间': data.get('captured_at')}, ensure_ascii=False))
            self.store.enqueue_candidate(candidate_id, str(data.get('name', candidate_id)), summary, now)

    def sweep(self, now):
        # Bounded history: a gap longer than the API page must be visible, never silently skipped.
        for workflow in ('update.yml', 'discover.yml'):
            runs = self.gh.list_runs(workflow=workflow, limit=100)
            start = max(self.started, now - 7 * 86400)
            if len(runs) == 100 and min(stamp(r['created_at']) for r in runs) > start:
                raise RuntimeError('RUN_HISTORY_TRUNCATED')
            trusted = [r for r in runs if r.get('head_branch') == 'main' and r.get('path') == f'.github/workflows/{workflow}'
                       and r.get('repository', {}).get('full_name') == self.config['github_repo']]
            completed = [r for r in trusted if stamp(r['created_at']) >= self.started and r.get('status') == 'completed']
            latest_run = max(completed, key=lambda r: (stamp(r['created_at']), r.get('run_attempt', 1)), default=None)
            if latest_run:
                failed = latest_run.get('conclusion') != 'success'
                self.store.transition(f'workflow:{workflow}:execution', failed, 'RUN_FAILED' if failed else 'EXECUTION_RESUMED', now)
            overdue = any(stamp(r['created_at']) >= self.started and r.get('status') == 'in_progress'
                          and now - stamp(r.get('run_started_at', r['created_at'])) > 2400 for r in trusted)
            self.store.transition(f'workflow:{workflow}:running', overdue, 'RUN_TIMEOUT' if overdue else 'RUN_FINISHED', now)
            missing = missing_slots(workflow, trusted, start, now)
            last_scheduled = max((stamp(r['created_at']) for r in trusted if r.get('event') == 'schedule'), default=0)
            stopped = bool(missing and max(missing) > last_scheduled)
            self.store.transition(f'workflow:{workflow}:schedule', stopped, 'SCHEDULE_NOT_OBSERVED' if stopped else 'SCHEDULE_RESUMED', now)
        # Ledger outages must not suppress workflow failure notifications above.
        ledger = public_ledger(self.config['github_repo'])
        for key, call in ledger['calls'].items():
            if not re.fullmatch('[a-f0-9]{64}', key):
                raise ValueError('CALL_ID_INVALID')
            status = call.get('status')
            unresolved = status in {'uncertain', 'rejected_result'} or (status == 'intent' and now - stamp(call['created_at']) > 1800)
            if unresolved or status in {'result_saved', 'abandoned'}:
                self.store.transition('call:' + key[:24], unresolved,
                                      'CALL_REQUIRES_REVIEW' if unresolved else 'CALL_RESULT_SAVED', now)
        summaries = [r for r in ledger['runs'].values() if r.get('completed_at') and r.get('workflow_file') == 'update.yml']
        observations = {}
        for summary in sorted(summaries, key=lambda r: stamp(r['completed_at'])):
            for stage in ('fetch', 'extract'):
                for item in summary.get(stage, {}).get('sources', []):
                    if not re.fullmatch('[a-f0-9]{64}', item.get('source', '')):
                        raise ValueError('SOURCE_ID_INVALID')
                    observations[(stage, item['source'])] = item
        for (stage, source), item in observations.items():
            status = item.get('status')
            bad = status in {'failed', 'fetch_failed', 'deferred'}
            good = status in {'fetched', 'candidate_ready', 'pending_review', 'reviewed_version', 'verified_unchanged', 'reviewed_rejected', 'changed', 'baseline_mismatch'}
            if bad or good:
                self.store.transition(f'{stage}:{source[:24]}', bad, 'SOURCE_BLOCKED' if bad else 'SOURCE_STAGE_RESUMED', now)
        latest = max(summaries, key=lambda r: stamp(r['completed_at']), default={})
        paused = latest.get('status') == 'dry_run'
        if latest:
            self.store.transition('checks:paused', paused, 'PAID_CHECKS_PAUSED' if paused else 'CHECKS_RESUMED', now)
        fetch = latest.get('fetch', {})
        self.source_observations = fetch.get('sources', [])
        return {'last_check_at': fetch.get('checked_at'),
                'attempted': fetch.get('attempted'), 'succeeded': fetch.get('succeeded'),
                'check_status': latest.get('status', 'unknown'),
                'sources': [{k: item.get(k) for k in ('platform', 'checked_at', 'status', 'scope')}
                            for item in fetch.get('sources', []) if isinstance(item, dict) and item.get('platform')]}

    def loop(self):
        while not self.stop.is_set():
            now = time.time()
            health = {'version': 1, 'updated_at': datetime.fromtimestamp(now, timezone.utc).isoformat(), 'monitoring': 'unknown'}
            try:
                health.update(self.sweep(now))
                if self.config.get('candidate_notifications_enabled'):
                    self.queue_candidates(now)
                self.store.transition('monitor:query', False, 'MONITOR_QUERY_RESTORED', now)
                health['monitoring'] = 'ok'
            except Exception:
                log.error('CHECK_MONITOR_QUERY_FAILED')
                try:
                    self.store.transition('monitor:query', True, 'MONITOR_QUERY_FAILED', now)
                except Exception:
                    log.error('CHECK_MONITOR_DATABASE_FAILED')
            try:
                self.deliver(now)
                health.update(self.store.health())
            except Exception:
                health['monitoring'] = 'unknown'
                log.error('CHECK_MONITOR_OUTBOX_FAILED')
            try:
                self.write_health(health)
            except Exception:
                log.error('CHECK_MONITOR_HEARTBEAT_FAILED')
            self.stop.wait(300)
