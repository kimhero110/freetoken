import copy
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from scripts.check_state import empty_state, StateError
from scripts.check_runner import paid_result, next_window
from scripts.check_external_monitor import ALERT_KEY, actionable_incidents, execute, notify_incidents, run
from scripts.extract import is_beijing_off_peak


class Store:
    def __init__(self):
        self.state = empty_state()

    def update(self, fn):
        state = copy.deepcopy(self.state)
        result = fn(state)
        self.state = state
        return result


class RestorationTests(unittest.TestCase):
    def test_current_pricing_weekends_and_weekday_boundaries(self):
        def date(day, hour):
            return datetime(2026, 9, day, hour, tzinfo=timezone.utc)
        self.assertTrue(is_beijing_off_peak(date(6, 8)))
        self.assertFalse(is_beijing_off_peak(date(7, 1)))
        self.assertTrue(is_beijing_off_peak(date(7, 4)))
        self.assertFalse(is_beijing_off_peak(date(7, 6)))
        self.assertTrue(is_beijing_off_peak(date(7, 10)))
        self.assertEqual(next_window(date(7, 2)), date(7, 4).isoformat())

    def test_legacy_refresh_grant_consumed_with_intent_not_replayed(self):
        store = Store()
        legacy = 'f' * 64
        store.state['history'][legacy] = 'legacy_unconfirmed'
        store.state['history']['refresh_group:group'] = {
            'used': None, 'allowed_legacy': [legacy],
            'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}
        request = Mock(return_value={'intro': 'new'})
        params = dict(store=store, source='b' * 64, run='1', request=request,
                      validate=lambda x: x, limit=4, history_keys=(legacy,), source_group='group')
        paid_result(key='a' * 64, **params)
        paid_result(key='a' * 64, **params)
        with self.assertRaises(StateError):
            paid_result(key='c' * 64, **params)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(store.state['history'][legacy], 'legacy_unconfirmed')

    def test_ungranted_legacy_and_expired_grant_never_call(self):
        store = Store()
        store.state['history']['legacy'] = 'legacy_unconfirmed'
        request = Mock()
        params = dict(store=store, key='a' * 64, source='b' * 64, run='1', request=request,
                      validate=lambda x: x, limit=4, history_keys=('legacy',), source_group='group')
        with self.assertRaises(StateError):
            paid_result(**params)
        store.state['history']['refresh_group:group'] = {'used': None, 'allowed_legacy': ['legacy'],
             'expires_at': '2026-01-01T00:00:00+00:00'}
        with self.assertRaises(StateError):
            paid_result(**params)
        request.assert_not_called()

    def test_external_failure_and_recovery_are_deduplicated(self):
        store, send = Store(), Mock(return_value=True)
        self.assertEqual(run(store, False, send, now=0), 1)
        run(store, False, send, now=1000)
        run(store, True, send, now=1100)
        run(store, True, send, now=1200)
        self.assertEqual(send.call_count, 2)

    def test_external_failed_sends_have_finite_persistent_retries(self):
        store, send = Store(), Mock(return_value=False)
        for now in (0, 900, 1800, 2700, 3600):
            run(store, False, send, now=now)
        self.assertEqual(send.call_count, 4)
        events = [x.args[0]['card']['elements'][0]['text']['content'] for x in send.call_args_list]
        self.assertEqual(len(set(events)), 1)

    def test_external_test_does_not_overwrite_real_incident(self):
        store, send = Store(), Mock(return_value=True)
        run(store, False, send, now=0)
        run(store, True, send, now=1, exercise=True)
        self.assertFalse(store.state['history']['external_heartbeat']['healthy'])

    def test_actionable_incidents_skip_pending_review_dry_run_and_discover(self):
        incident = 'extract:' + ('ab' * 12)
        self.assertEqual(actionable_incidents([
            incident, 'checks:paused', 'pending_review', 'workflow:discover.yml:execution',
            'extract:' + ('g' * 24), 'workflow:update.yml:execution',
        ]), ['extract:' + ('ab' * 12), 'workflow:update.yml:execution'])

    def test_extract_incident_alerts_once_until_the_id_clears(self):
        store, send = Store(), Mock(return_value=True)
        incident = 'extract:' + ('ab' * 12)
        self.assertEqual(notify_incidents(
            store, [incident, 'checks:paused', 'pending_review'], send, now=0), 0)
        self.assertEqual(notify_incidents(store, [incident], send, now=1000), 0)
        self.assertEqual(send.call_count, 1)
        body = send.call_args.args[0]['card']['elements'][0]['text']['content']
        title = send.call_args.args[0]['card']['header']['title']['content']
        self.assertEqual(title, 'FreeToken 检查失败')
        self.assertIn(incident, body)
        self.assertNotIn('checks:paused', body)
        self.assertNotIn('workflow:discover', body)
        self.assertTrue(store.state['history'][ALERT_KEY]['open'][incident]['accepted'])
        self.assertNotIn('external_heartbeat', store.state['history'])
        notify_incidents(store, [], send, now=1001)
        notify_incidents(store, [incident], send, now=1002)
        self.assertEqual(send.call_count, 2)

    def test_extract_incident_send_retries_are_bounded(self):
        store, send = Store(), Mock(return_value=False)
        incident = 'fetch:' + ('cd' * 12)
        codes = [notify_incidents(store, [incident], send, now=now) for now in (0, 900, 1800, 2700, 3600)]
        self.assertEqual(send.call_count, 4)
        self.assertEqual(codes, [1, 1, 1, 1, 0])
        self.assertFalse(store.state['history'][ALERT_KEY]['open'][incident]['accepted'])

    def test_a_new_incident_alerts_while_an_accepted_one_stays_quiet(self):
        store, send = Store(), Mock(return_value=True)
        first = 'workflow:update.yml:execution'
        second = 'call:' + ('ef' * 12)
        notify_incidents(store, [first], send, now=0)
        notify_incidents(store, [first, second], send, now=1)
        self.assertEqual(send.call_count, 2)
        body = send.call_args.args[0]['card']['elements'][0]['text']['content']
        self.assertIn(second, body)
        self.assertNotIn(first, body)

    def test_healthy_monitor_pages_a_new_extract_failure_once(self):
        store, send = Store(), Mock(return_value=True)
        incident = 'extract:' + ('12' * 12)

        def refresh():
            return True, 'CHECK_MONITOR_OK active_incidents=1', [incident, 'checks:paused']

        self.assertEqual(execute(store, exercise='none', refresh=refresh, send=send, now=0), 0)
        self.assertEqual(execute(store, exercise='none', refresh=refresh, send=send, now=10), 0)
        self.assertEqual(send.call_count, 1)
        self.assertIn('FreeToken 检查失败', send.call_args.args[0]['card']['header']['title']['content'])
        self.assertTrue(store.state['history']['external_heartbeat']['healthy'])

    def test_exercise_does_not_page_extract_incidents(self):
        store, send = Store(), Mock(return_value=True)

        def refresh():
            raise AssertionError('exercise must not read incidents')

        code = execute(store, exercise='failure', refresh=refresh, send=send, now=0)
        self.assertEqual(code, 0)
        self.assertEqual(send.call_count, 1)
        self.assertIn('联调', send.call_args.args[0]['card']['header']['title']['content'])
        self.assertNotIn(ALERT_KEY, store.state['history'])


if __name__ == '__main__':
    unittest.main()
