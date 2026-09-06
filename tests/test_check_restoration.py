import copy
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from scripts.check_state import empty_state, StateError
from scripts.check_runner import paid_result, next_window
from scripts.check_external_monitor import run
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


if __name__ == '__main__':
    unittest.main()
