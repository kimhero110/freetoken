import time
import unittest

from daemon.state import Ticket, TicketStore


def make_store(**kwargs):
    return TicketStore(**kwargs)


class ConfirmCodeTests(unittest.TestCase):
    def test_issue_and_confirm_ok(self):
        store = make_store()
        ticket = store.new_ticket("approve", "probe-x")
        code = store.issue_confirm(ticket)
        ok, why = store.check_confirm(ticket, code, now=time.time() + 1)
        self.assertTrue(ok)
        self.assertEqual(why, "OK")
        self.assertEqual(ticket.confirm_code, "")

    def test_wrong_code_three_times_locks(self):
        store = make_store(confirm_max_attempts=3, lock_ttl=100)
        ticket = store.new_ticket("approve", "probe-x")
        code = store.issue_confirm(ticket)
        now = time.time()
        self.assertEqual(store.check_confirm(ticket, "000000", now=now)[1], "WRONG")
        self.assertEqual(store.check_confirm(ticket, "000000", now=now)[1], "WRONG")
        self.assertEqual(store.check_confirm(ticket, "000000", now=now)[1], "LOCKED")
        ok, why = store.check_confirm(ticket, code, now=now + 1)
        self.assertFalse(ok)
        self.assertEqual(why, "LOCKED")

    def test_expired_code_rejected(self):
        store = make_store(confirm_ttl=60)
        ticket = store.new_ticket("approve", "probe-x")
        code = store.issue_confirm(ticket)
        ok, why = store.check_confirm(ticket, code, now=time.time() + 61)
        self.assertFalse(ok)
        self.assertEqual(why, "EXPIRED")


class TicketStoreTests(unittest.TestCase):
    def test_event_roundtrip_rebuilds_state(self):
        store = make_store()
        ticket = store.new_ticket("platform", "https://a.io")
        ticket.phase = "dispatched"
        ticket.run_ids = [123]
        ticket.card_message_id = "om-1"
        event = ticket.to_event()
        fresh = make_store()
        fresh.prime([event])
        restored = fresh.tickets[ticket.ticket_id]
        self.assertEqual(restored.phase, "dispatched")
        self.assertEqual(restored.run_ids, [123])
        self.assertEqual(restored.card_message_id, "om-1")

    def test_active_approval_lock(self):
        store = make_store(lock_ttl=100)
        ticket = store.new_ticket("approve", "cand-1")
        ticket.locked_until = time.time() + 50
        self.assertIs(store.active_approval_for("cand-1"), ticket)
        ticket.locked_until = time.time() - 1
        self.assertIsNone(store.active_approval_for("cand-1"))

    def test_short_id_deterministic(self):
        candidates = ["tip-b-222", "tip-a-111", "probe-c-333"]
        ordered = sorted(candidates)
        self.assertEqual(ordered, ["probe-c-333", "tip-a-111", "tip-b-222"])
        self.assertEqual(TicketStore.short_id_for(ordered, "tip-a-111"), "#p002")
        self.assertEqual(TicketStore.resolve_short_id(ordered, 3), "tip-b-222")
        self.assertIsNone(TicketStore.short_id_for(ordered, "missing"))
        self.assertIsNone(TicketStore.resolve_short_id(ordered, 9))

    def test_candidate_freshness_window(self):
        store = make_store(fresh_hours=48)
        from datetime import datetime, timezone, timedelta
        recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
        self.assertTrue(store.is_candidate_fresh(recent))
        self.assertFalse(store.is_candidate_fresh(old))
        self.assertFalse(store.is_candidate_fresh("not-a-date"))

    def test_latest_own_submission(self):
        store = make_store()
        first = store.new_ticket("platform", "https://a.io", owner="ou_1")
        time.sleep(0.01)
        store.new_ticket("platform", "https://b.io", owner="ou_2")
        time.sleep(0.01)
        second = store.new_ticket("article", "https://c.io", owner="ou_1")
        self.assertIs(store.latest_own_submission("ou_1"), second)
        self.assertIsNot(store.latest_own_submission("ou_1"), first)
        self.assertIsNone(store.latest_own_submission("ou_3"))


if __name__ == "__main__":
    unittest.main()
