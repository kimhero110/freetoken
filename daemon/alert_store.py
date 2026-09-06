"""Transactional incidents and outbox. A send acknowledgement is not a read receipt."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class AlertStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('ALERT_DATABASE_INVALID')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS incidents (
                  id TEXT PRIMARY KEY, active INTEGER NOT NULL, revision INTEGER NOT NULL,
                  code TEXT NOT NULL, changed REAL NOT NULL, notified REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS outbox (
                  id TEXT PRIMARY KEY, incident TEXT NOT NULL, payload TEXT NOT NULL,
                  status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                  next REAL NOT NULL, message_id TEXT);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def transition(self, incident, active, code, now):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT active,revision,code,notified FROM incidents WHERE id=?', (incident,)).fetchone()
            if old and old[0] == int(active) and old[2] == code and (not active or now - old[3] < 86400):
                return
            if old is None and not active:
                return
            revision = old[1] + 1 if old else 1
            event = hashlib.sha256(f'{incident}:{revision}'.encode()).hexdigest()[:32]
            payload = json.dumps({'event': event, 'incident': incident, 'active': bool(active), 'code': code})
            db.execute('INSERT OR REPLACE INTO incidents VALUES (?,?,?,?,?,?)',
                       (incident, int(active), revision, code, now, now))
            db.execute("UPDATE outbox SET status='superseded' WHERE incident=? AND status!='api_accepted'", (incident,))
            db.execute('INSERT INTO outbox(id,incident,payload,status,next) VALUES (?,?,?,?,?)',
                       (event, incident, payload, 'pending', now))

    def claim(self, now):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # A worker may die after sending. Its durable sending state expires into
            # a bounded retry, never an assertion that nothing was sent.
            db.execute("UPDATE outbox SET status='delivery_unknown' WHERE status='sending' AND next<=?", (now,))
            db.execute("UPDATE outbox SET status='exhausted' WHERE attempts>=4 AND status='delivery_unknown'")
            row = db.execute("SELECT id,payload,attempts FROM outbox WHERE status IN ('pending','retry_wait','delivery_unknown') AND next<=? AND attempts<4 ORDER BY rowid LIMIT 1", (now,)).fetchone()
            if row:
                db.execute("UPDATE outbox SET status='sending',attempts=attempts+1,next=? WHERE id=?", (now + 300, row[0]))
            return (row[0], json.loads(row[1]), row[2] + 1) if row else None

    def finish(self, event, attempts, now, message_id='', unknown=False):
        status = 'api_accepted' if message_id else ('exhausted' if attempts >= 4 else ('delivery_unknown' if unknown else 'retry_wait'))
        delay = (60, 300, 900, 86400)[min(attempts - 1, 3)]
        with self.connect() as db:
            db.execute("UPDATE outbox SET status=?,next=?,message_id=? WHERE id=? AND attempts=? AND status='sending'",
                       (status, now + delay, message_id, event, attempts))

    def health(self):
        with self.connect() as db:
            return {'active_incidents': db.execute('SELECT count(*) FROM incidents WHERE active=1').fetchone()[0],
                    'notification_failures': db.execute("SELECT count(*) FROM outbox WHERE status IN ('exhausted','delivery_unknown','retry_wait')").fetchone()[0]}
