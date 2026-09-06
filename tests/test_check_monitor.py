import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from daemon.alert_store import AlertStore
from daemon.check_monitor import CheckMonitor, expected_slots, missing_slots, stamp


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
