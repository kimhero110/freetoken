import json
import tempfile
import unittest
from pathlib import Path

from daemon.journal import Journal, clear_spool, list_spool, write_spool


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "journal.jsonl"
        self.journal = Journal(self.path)

    def test_append_and_load_roundtrip(self):
        events = [
            {"type": "ticket_update", "ticket_id": "pl-1", "phase": "created"},
            {"type": "feishu_event", "event_id": "e-1", "ts": "2026-09-03T00:00:00Z"},
            {"type": "ticket_update", "ticket_id": "pl-1", "phase": "dispatched"},
        ]
        for event in events:
            self.journal.append(event)
        loaded = self.journal.load_events()
        self.assertEqual(loaded, events)

    def test_seen_event_dedup(self):
        self.assertFalse(self.journal.seen_event("e-9"))
        self.journal.append({"type": "feishu_event", "event_id": "e-9"})
        self.assertTrue(self.journal.seen_event("e-9"))

    def test_prime_seen_events_rebuilds_on_restart(self):
        self.journal.append({"type": "feishu_event", "event_id": "e-7"})
        fresh = Journal(self.path)
        self.assertFalse(fresh.seen_event("e-7"))
        fresh.prime_seen_events()
        self.assertTrue(fresh.seen_event("e-7"))

    def test_torn_tail_write_is_skipped(self):
        self.journal.append({"type": "ticket_update", "ticket_id": "ok"})
        self.path.write_text(self.path.read_text(encoding="utf-8") + '{"type": "tor', encoding="utf-8")
        loaded = Journal(self.path).load_events()
        self.assertEqual(len(loaded), 1)

    def test_spool_roundtrip(self):
        spool = Path(self.tmp.name) / "spool"
        write_spool(spool, {"event_id": "ev-1", "text": "平台 https://a.io"})
        items = list_spool(spool)
        self.assertEqual(items, [{"event_id": "ev-1", "text": "平台 https://a.io"}])
        clear_spool(spool, "ev-1")
        self.assertEqual(list_spool(spool), [])


if __name__ == "__main__":
    unittest.main()
