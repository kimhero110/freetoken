# -*- coding: utf-8 -*-
"""Sender whitelist. BOOTSTRAP=1 answers 谁我 to anyone so the owner can discover their open_id."""


def is_authorized(sender_open_id: str, owner_open_id: str, bootstrap: bool = False) -> bool:
    return bool(sender_open_id) and sender_open_id == owner_open_id


def should_answer_whoami(sender_open_id: str, owner_open_id: str, bootstrap: bool = False) -> bool:
    """谁我 is answered for the owner always, and for anyone in bootstrap mode."""
    if sender_open_id == owner_open_id:
        return True
    return bootstrap and bool(sender_open_id)


def redact_open_id(open_id: str) -> str:
    """Audit-safe identity annotation: keep head 8 chars only."""
    return (open_id or "")[:8]
