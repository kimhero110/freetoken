# -*- coding: utf-8 -*-
"""Watchdog: cancel ticket-initiated runs stuck on the production gate > N minutes."""

import logging
import threading
import time

from . import cards

log = logging.getLogger("watchdog")


class Watchdog:
    def __init__(self, store, gh, feishu, config, journal, poll_seconds: int = 60):
        self.store = store
        self.gh = gh
        self.feishu = feishu
        self.config = config
        self.journal = journal
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="watchdog", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(self.poll_seconds):
            try:
                self._sweep()
            except Exception as exc:  # never die
                log.exception("watchdog sweep failed: %s", exc)

    def _sweep(self):
        limit = self.config["watchdog_minutes"] * 60
        now = time.time()
        for ticket in list(self.store.tickets.values()):
            if ticket.phase != "awaiting_gate" or not ticket.run_ids:
                continue
            if now - ticket.updated_at <= limit:
                continue
            run_id = ticket.run_ids[-1]
            try:
                self.gh.cancel_run(run_id)
                ticket.phase = "cancelled"
                ticket.updated_at = now
                self.journal.append(ticket.to_event())
                self.feishu.send_card(
                    self.config["owner_open_id"],
                    cards.watchdog_card(ticket.ticket_id, run_id, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ticket.updated_at))),
                    receive_id_type="open_id",
                )
                log.info("watchdog cancelled run %s for ticket %s", run_id, ticket.ticket_id)
            except Exception as exc:
                log.warning("watchdog cancel failed for %s: %s", run_id, exc)
