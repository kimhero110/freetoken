import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from daemon.alert_store import AlertStore
from daemon.check_monitor import CheckMonitor, expected_slots, missing_slots, stamp, public_ledger


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'alerts.db'
        self.store = AlertStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_restart_preserves_pending_event_and_deduplicates(self):
        self.store.transition('source:a', True, 'FAILED', 100)
        other = AlertStore(self.path)
        other.transition('source:a', True, 'FAILED', 200)
        event = other.claim(200)
        self.assertIsNotNone(event)
        other.finish(event[0], event[2], 200, message_id='accepted')
        self.assertIsNone(other.claim(1000))

    def test_unknown_send_has_bounded_retries(self):
        self.store.transition('source:a', True, 'FAILED', 0)
        ids = []
        for now in (0, 60, 360, 1260):
            event = self.store.claim(now)
            ids.append(event[0])
            self.store.finish(event[0], event[2], now, unknown=True)
        self.assertEqual(len(set(ids)), 1)
        self.assertIsNone(self.store.claim(100000))
        self.assertEqual(self.store.health()['notification_failures'], 1)

    def test_worker_crash_after_send_is_unknown_not_unsent(self):
        self.store.transition('source:a', True, 'FAILED', 0)
        first = self.store.claim(0)
        self.assertIsNone(self.store.claim(299))
        second = AlertStore(self.path).claim(300)
        self.assertEqual(first[0], second[0])
        self.assertEqual(second[2], 2)

    def test_one_source_recovery_does_not_clear_others(self):
        self.store.transition('source:a', True, 'FAILED', 0)
        self.store.transition('source:b', True, 'FAILED', 0)
        self.store.transition('source:a', False, 'RECOVERED', 10)
        self.assertEqual(self.store.health()['active_incidents'], 1)

    def test_recovery_supersedes_stale_failure_retries(self):
        self.store.transition('source:a', True, 'FAILED', 0)
        first = self.store.claim(0)
        self.store.finish(first[0], first[2], 0, unknown=True)
        self.store.transition('source:a', False, 'RECOVERED', 10)
        event = self.store.claim(60)
        self.assertFalse(event[1]['active'])
        self.store.finish(event[0], event[2], 60, message_id='recovery')
        self.assertIsNone(self.store.claim(9999))
        self.assertEqual(self.store.health()['notification_failures'], 0)

    def test_business_rejection_does_not_mark_accepted(self):
        config = {'check_monitor_since': '2026-09-06T00:00:00Z', 'check_status_path': str(Path(self.temp.name) / 'health.json'),
                  'check_alert_db': self.path, 'owner_open_id': 'test', 'github_repo': 'example/repo'}
        feishu = Mock()
        feishu.send_card.return_value = ''
        monitor = CheckMonitor(Mock(), feishu, config)
        self.store.transition('source:a', True, 'FAILED', 0)
        monitor.deliver(0)
        self.assertEqual(self.store.health()['notification_failures'], 1)


class ScheduleTests(unittest.TestCase):
    def test_long_daytime_gap_does_not_imply_missing_run(self):
        start = stamp('2026-09-06T00:00:00Z')
        now = stamp('2026-09-06T16:00:00Z')
        self.assertEqual(missing_slots('update.yml', [], start, now), [])

    def test_manual_run_cannot_cover_missing_schedule(self):
        start = stamp('2026-09-06T17:00:00Z')
        now = stamp('2026-09-06T21:00:00Z')
        run = {'event': 'workflow_dispatch', 'head_branch': 'main', 'created_at': '2026-09-06T18:00:00Z'}
        self.assertEqual(len(missing_slots('update.yml', [run], start, now)), 1)
        run['event'] = 'schedule'
        self.assertEqual(missing_slots('update.yml', [run], start, now), [])

    def test_discovery_uses_odd_utc_dates_not_rolling_48_hours(self):
        start = stamp('2026-09-01T00:00:00Z')
        now = stamp('2026-09-04T00:00:00Z')
        slots = list(expected_slots('discover.yml', start, now))
        self.assertEqual(len(slots), 2)


if __name__ == '__main__':
    unittest.main()


class StaleSourceTests(unittest.TestCase):
    """抓取来源的 id 是当天那一版页面的哈希，页面一变它就再也不会出现。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'alerts.sqlite'

    def monitor(self):
        config = {'check_monitor_since': '2026-09-06T00:00:00Z',
                  'check_status_path': str(Path(self.temp.name) / 'health.json'),
                  'check_alert_db': str(self.path), 'owner_open_id': 'test',
                  'github_repo': 'example/repo'}
        gh = Mock()
        gh.list_runs.return_value = []
        return CheckMonitor(gh, Mock(), config)

    def ledger(self, completed, status, error=None):
        source = 'a' * 64
        return {'calls': {}, 'runs': {'1': {
            'completed_at': completed, 'workflow_file': 'update.yml', 'status': 'completed',
            'fetch': {'sources': []},
            'extract': {'sources': [{'source': source, 'status': status, 'error': error}]}}}}

    def states(self, ledger, now):
        monitor = self.monitor()
        with patch('daemon.check_monitor.public_ledger', return_value=ledger):
            monitor.sweep(now)
        with monitor.store.connect() as db:
            return {r[0]: (r[1], r[2]) for r in db.execute('SELECT id,active,code FROM incidents')
                    if r[0].startswith('extract:')}

    def test_a_failure_from_last_week_is_not_todays_problem(self):
        # 09-08 到 09-21 那 59 个 MODEL_NOT_AVAILABLE，在原因修好之后
        # 还在每天早上被报一遍，因为它们的 id 永远不会再出现一次健康状态。
        ledger = self.ledger('2026-09-10T01:12:00Z', 'failed', 'MODEL_NOT_AVAILABLE')
        states = self.states(ledger, stamp('2026-09-23T01:00:00Z'))
        self.assertEqual(states, {})

    def test_a_failure_from_this_morning_still_is(self):
        ledger = self.ledger('2026-09-23T01:12:00Z', 'failed', 'MODEL_NOT_AVAILABLE')
        states = self.states(ledger, stamp('2026-09-23T09:00:00Z'))
        self.assertEqual(states['extract:' + 'a' * 24], (1, 'SOURCE_BLOCKED'))

    def test_waiting_for_the_cheap_window_is_not_a_blocked_source(self):
        # deferred 是费用策略在起作用，不是来源读不到。
        ledger = self.ledger('2026-09-23T01:12:00Z', 'deferred')
        self.assertEqual(self.states(ledger, stamp('2026-09-23T09:00:00Z')), {})


class PublicLedgerTests(unittest.TestCase):
    def response(self, chunks, status=200):
        response = Mock(status_code=status)
        response.iter_content.return_value = chunks
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        return context

    @patch('daemon.check_monitor.requests.get')
    def test_public_api_raw_without_credentials(self, get):
        get.return_value = self.response([b'{"version":1,"runs":{},"calls":{},"history":{}}'])
        self.assertEqual(public_ledger('example/repo')['version'], 1)
        args, kwargs = get.call_args
        self.assertEqual(args[0], 'https://api.github.com/repos/example/repo/contents/state.json?ref=automation-state')
        self.assertEqual(kwargs['headers']['Accept'], 'application/vnd.github.raw+json')
        self.assertNotIn('Authorization', kwargs['headers'])
        self.assertFalse(kwargs['allow_redirects'])

    @patch('daemon.check_monitor.requests.get')
    def test_fail_closed(self, get):
        for chunks, status in [([], 403), ([b'x' * 8_000_001], 200), ([b'[]'], 200), ([b'{"content":"encoded"}'], 200)]:
            get.return_value = self.response(chunks, status)
            with self.assertRaises((ValueError, RuntimeError)):
                public_ledger('example/repo')
