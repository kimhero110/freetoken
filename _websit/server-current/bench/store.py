"""SQLite result store with share permalinks. Stdlib only."""

import json
import os
import sqlite3
import threading
import time
import secrets

_DB_PATH = os.environ.get("BENCH_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports.db"))
_lock = threading.Lock()


def _conn():
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    c = sqlite3.connect(_DB_PATH, timeout=15)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS runs(
        id TEXT PRIMARY KEY, created REAL, host TEXT, model TEXT,
        composite INTEGER, grade TEXT, full TEXT)""")
    return c


def save_run(run):
    rid = secrets.token_urlsafe(6)
    run["id"] = rid
    now = time.time()
    with _lock:
        c = _conn()
        try:
            c.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
                      (rid, now, run.get("host", ""), run.get("model", ""),
                       run.get("composite", {}).get("composite", 0),
                       run.get("composite", {}).get("grade", ""),
                       json.dumps(run, ensure_ascii=False)))
            c.execute("DELETE FROM runs WHERE id IN (SELECT id FROM runs ORDER BY created DESC LIMIT -1 OFFSET 500)")
            c.commit()
        finally:
            c.close()
    return rid


def get_run(rid):
    with _lock:
        c = _conn()
        try:
            row = c.execute("SELECT full FROM runs WHERE id=?", (rid,)).fetchone()
        finally:
            c.close()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def history(limit=30):
    with _lock:
        c = _conn()
        try:
            rows = c.execute(
                "SELECT id, created, host, model, composite, grade FROM runs ORDER BY created DESC LIMIT ?",
                (limit,)).fetchall()
        finally:
            c.close()
    out = []
    for rid, created, host, model, comp, grade in rows:
        out.append({"id": rid, "created": time.strftime("%Y-%m-%d %H:%M", time.localtime(created)),
                    "host": host, "model": model, "composite": comp, "grade": grade})
    return out
