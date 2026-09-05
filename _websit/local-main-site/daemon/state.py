# -*- coding: utf-8 -*-
"""Ticket state machine rebuilt from the journal: confirm codes, locks, short-id resolution.

Tickets are event-sourced (journal is source of truth). TTL logic is enforced
on read so a restarted daemon derives the same decisions from wall clock.
"""

import hashlib
import secrets
import time
from dataclasses import dataclass, field


@dataclass
class Ticket:
    ticket_id: str
    kind: str  # platform | article | approve | reject
    arg: str  # url or candidate_id
    phase: str = "created"  # created|dispatched|awaiting_confirm|awaiting_gate|merged|publishing|done|failed|cancelled
    note: str = ""
    run_ids: list = field(default_factory=list)
    card_message_id: str = ""
    confirm_code: str = ""
    confirm_expires_at: float = 0.0
    confirm_attempts: int = 0
    locked_until: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    owner: str = ""

    def to_event(self) -> dict:
        return {
            "type": "ticket_update",
            "ticket_id": self.ticket_id,
            "kind": self.kind,
            "arg": self.arg,
            "phase": self.phase,
            "note": self.note,
            "run_ids": list(self.run_ids),
            "card_message_id": self.card_message_id,
            "confirm_code": self.confirm_code,
            "confirm_expires_at": self.confirm_expires_at,
            "confirm_attempts": self.confirm_attempts,
            "locked_until": self.locked_until,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "owner": self.owner,
        }

    @classmethod
    def from_event(cls, event: dict) -> "Ticket":
        return cls(
            ticket_id=event["ticket_id"],
            kind=event.get("kind", ""),
            arg=event.get("arg", ""),
            phase=event.get("phase", "created"),
            note=event.get("note", ""),
            run_ids=list(event.get("run_ids", [])),
            card_message_id=event.get("card_message_id", ""),
            confirm_code=event.get("confirm_code", ""),
            confirm_expires_at=float(event.get("confirm_expires_at", 0) or 0),
            confirm_attempts=int(event.get("confirm_attempts", 0) or 0),
            locked_until=float(event.get("locked_until", 0) or 0),
            created_at=float(event.get("created_at", 0) or 0),
            updated_at=float(event.get("updated_at", 0) or 0),
            owner=event.get("owner", ""),
        )


class TicketStore:
    def __init__(self, confirm_ttl: float = 300.0, confirm_max_attempts: int = 3,
                 lock_ttl: float = 1800.0, fresh_hours: float = 48.0):
        self.tickets: dict[str, Ticket] = {}
        self.confirm_ttl = confirm_ttl
        self.confirm_max_attempts = confirm_max_attempts
        self.lock_ttl = lock_ttl
        self.fresh_hours = fresh_hours

    # -- state rebuild ------------------------------------------------------
    def apply(self, event: dict) -> None:
        if event.get("type") != "ticket_update":
            return
        existing = self.tickets.get(event["ticket_id"])
        incoming = Ticket.from_event(event)
        if existing is None or incoming.updated_at >= existing.updated_at:
            self.tickets[incoming.ticket_id] = incoming

    def prime(self, events) -> None:
        for event in events:
            self.apply(event)

    # -- lifecycle ----------------------------------------------------------
    def new_ticket(self, kind: str, arg: str, owner: str = "", note: str = "") -> Ticket:
        digest = hashlib.sha256(f"{time.time_ns()}-{kind}-{arg}".encode("utf-8")).hexdigest()[:10]
        ticket = Ticket(ticket_id=f"{kind[:2]}-{digest}", kind=kind, arg=arg, owner=owner, note=note)
        self.tickets[ticket.ticket_id] = ticket
        return ticket

    def active_approval_for(self, candidate_id: str) -> Ticket | None:
        now = time.time()
        for ticket in self.tickets.values():
            if ticket.kind in ("approve", "reject") and ticket.arg == candidate_id:
                if ticket.phase not in ("done", "failed", "cancelled") and ticket.locked_until > now:
                    return ticket
        return None

    # -- confirmation codes (fat-finger guard, not session-hijack defense) --
    def issue_confirm(self, ticket: Ticket) -> str:
        ticket.confirm_code = f"{secrets.randbelow(1000000):06d}"
        ticket.confirm_expires_at = time.time() + self.confirm_ttl
        ticket.confirm_attempts = 0
        ticket.updated_at = time.time()
        return ticket.confirm_code

    def check_confirm(self, ticket: Ticket, code: str, now: float | None = None) -> tuple[bool, str]:
        now = time.time() if now is None else now
        if ticket.locked_until > now:
            return False, "LOCKED"
        if now > ticket.confirm_expires_at:
            return False, "EXPIRED"
        if code != ticket.confirm_code:
            ticket.confirm_attempts += 1
            ticket.updated_at = time.time()
            if ticket.confirm_attempts >= self.confirm_max_attempts:
                ticket.locked_until = now + self.lock_ttl
                ticket.updated_at = time.time()
                return False, "LOCKED"
            return False, "WRONG"
        ticket.confirm_code = ""
        ticket.confirm_expires_at = 0.0
        ticket.updated_at = now
        return True, "OK"

    def is_candidate_fresh(self, candidate_created_iso: str, now_ts: float | None = None) -> bool:
        """The 48h freshness window applies to when the candidate was probed/extracted."""
        try:
            from datetime import datetime, timezone
            created = datetime.fromisoformat(candidate_created_iso)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            now = time.time() if now_ts is None else now_ts
            age = now - created.timestamp()
            return -300 <= age <= self.fresh_hours * 3600
        except (TypeError, ValueError):
            return False

    # -- short ids: deterministic from sorted candidate file listing ---------
    @staticmethod
    def short_id_for(candidate_files: list, candidate_id: str) -> str | None:
        ordered = sorted(candidate_files)
        try:
            index = ordered.index(candidate_id)
        except ValueError:
            return None
        return f"#p{index + 1:03d}"

    @staticmethod
    def resolve_short_id(candidate_files: list, number: int) -> str | None:
        ordered = sorted(candidate_files)
        if 1 <= number <= len(ordered):
            return ordered[number - 1]
        return None

    def latest_own_submission(self, owner: str) -> Ticket | None:
        mine = [t for t in self.tickets.values() if t.owner == owner and t.kind in ("platform", "article")]
        return max(mine, key=lambda t: t.created_at, default=None)


def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
