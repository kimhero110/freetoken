"""At-most-one automatic paid attempt; publishing can resume independently."""
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from .check_state import StateError, digest


def utcnow():
    return datetime.now(timezone.utc)


def public_result(result):
    # Exact schema validation is additionally performed by extract.validate_extracted.
    import json
    text = json.dumps(result, ensure_ascii=False)
    if len(text) > 8000 or re.search(r"(?i)(bearer\s|sk-[a-z0-9]{12,}|-----BEGIN|api[_-]?key\s*[:=])", text):
        raise StateError("PUBLIC_RESULT_REJECTED")
    for name, value in os.environ.items():
        if any(word in name for word in ("SECRET", "TOKEN", "API_KEY", "PASSWORD")) and len(value) >= 8 and value in text:
            raise StateError("PUBLIC_RESULT_REJECTED")
    return result


def next_window(now):
    current = now.astimezone(timezone.utc)
    if current.weekday() < 5:
        if 1 <= current.hour < 4:
            return current.replace(hour=4, minute=0, second=0, microsecond=0).isoformat()
        if 6 <= current.hour < 10:
            return current.replace(hour=10, minute=0, second=0, microsecond=0).isoformat()
    return current.isoformat()


def paid_result(store, *, key, source, run, request, validate, limit, fresh_hours=48, history_keys=(), source_group=None):
    """Only a new, confirmed claim in this invocation may send the request.

    A crash leaves intent; its lease never authorizes another automatic request.
    """
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise StateError("BUDGET_NOT_CONFIGURED")
    owner = uuid.uuid4().hex
    def claim(state):
        previous = state["calls"].get(key)
        if previous:
            return previous
        blocked = [item for item in (source, *history_keys) if item in state['history']]
        grant = None
        if blocked:
            grant = state['history'].get('refresh_group:' + str(source_group))
            if (not isinstance(grant, dict) or grant.get('used') is not None
                    or datetime.fromisoformat(grant['expires_at']) <= utcnow()
                    or any(item not in grant['allowed_legacy'] for item in blocked)):
                raise StateError('HISTORICAL_CALL_REQUIRES_REVIEW')
        if sum(c["run"] == run for c in state["calls"].values()) >= limit:
            raise StateError("RUN_BUDGET_EXHAUSTED")
        # One automatic attempt per source version, even when recipe/provider changes.
        if any(c["source"] == source for c in state["calls"].values()):
            raise StateError("SOURCE_ALREADY_ATTEMPTED")
        record = {"owner": owner, "run": run, "source": source, "status": "intent",
                  "created_at": utcnow().isoformat()}
        if grant is not None:
            grant["used"] = key
        state["calls"][key] = record
        return record
    record = store.update(claim)
    if record["status"] == "result_saved":
        if utcnow() - datetime.fromisoformat(record["saved_at"]) > timedelta(hours=fresh_hours):
            raise StateError("RESULT_EXPIRED")
        result = validate(record["result"])
        if result is None:
            raise StateError("RESULT_INVALID")
        return public_result(result)
    if record["owner"] != owner:
        raise StateError("CALL_UNCERTAIN" if record["status"] == "intent" else record["status"].upper())
    try:
        raw = request()
        result = validate(raw)
        status = "result_saved" if result is not None else "rejected_result"
        if result is not None:
            public_result(result)
    except Exception:
        result, status = None, "uncertain"
    def save(state):
        current = state["calls"].get(key, {})
        if current.get("owner") != owner or current.get("status") != "intent":
            raise StateError("CALL_FENCED")
        current["status"] = status
        if result is not None:
            current.update(result=result, result_hash=digest(result), saved_at=utcnow().isoformat())
    store.update(save)
    if result is None:
        raise StateError(status.upper())
    return result
