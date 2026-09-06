"""Private jobs and versioned analyses alongside untouched legacy reports."""
import hashlib
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager

DB=Path(os.getenv('BENCH_DB',str(Path(__file__).parent/'data/reports.db')))

@contextmanager
def connect():
    DB.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS studio_runs(id TEXT PRIMARY KEY,owner TEXT,idem TEXT,created REAL,state TEXT,payload TEXT,result TEXT,error TEXT, UNIQUE(owner,idem));
    CREATE TABLE IF NOT EXISTS studio_shares(token_hash TEXT PRIMARY KEY,run_id TEXT,owner TEXT,expires REAL);
    CREATE TABLE IF NOT EXISTS studio_analyses(id TEXT PRIMARY KEY,run_id TEXT,created REAL,payload TEXT);
    ''')
    try:
        with c:
            yield c
    finally:
        c.close()

def recover():
    with connect() as c:
        c.execute("UPDATE studio_runs SET state='interrupted',error='服务重启，任务已中断；不会自动重新调用。' WHERE state IN ('queued','running','cancelling')")

def create(owner,idem,payload):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT id FROM studio_runs WHERE owner=? AND idem=?',(owner,idem)).fetchone()
        if old:return old['id'],False
        if c.execute("SELECT count(*) FROM studio_runs WHERE state IN ('queued','running','cancelling')").fetchone()[0]>=4:
            raise ValueError('当前任务已满，请稍后再试')
        if c.execute("SELECT count(*) FROM studio_runs WHERE owner=? AND state IN ('queued','running','cancelling')",(owner,)).fetchone()[0]:
            raise ValueError('当前会话已有运行中的任务')
        rid=secrets.token_urlsafe(18)
        c.execute('INSERT INTO studio_runs VALUES(?,?,?,?,?,?,?,?)',(rid,owner,idem,time.time(),'queued',json.dumps(payload,ensure_ascii=False),None,None))
        return rid,True

def update(rid,state,result=None,error=None):
    with connect() as c:
        c.execute('UPDATE studio_runs SET state=?,result=COALESCE(?,result),error=? WHERE id=?',
                  (state,json.dumps(result,ensure_ascii=False) if result is not None else None,error,rid))

def get(rid,owner):
    with connect() as c: row=c.execute('SELECT * FROM studio_runs WHERE id=? AND owner=?',(rid,owner)).fetchone()
    return decode(row)

def decode(row):
    if not row:return None
    d=dict(row);d.pop('owner',None);d.pop('idem',None)
    for k in ('payload','result'):d[k]=json.loads(d[k]) if d[k] else None
    return d

def history(owner):
    with connect() as c:
        return [dict(r) for r in c.execute('SELECT id,created,state,error FROM studio_runs WHERE owner=? ORDER BY created DESC LIMIT 50',(owner,))]

def share(rid,owner):
    if not get(rid,owner):raise ValueError('报告不存在')
    token=secrets.token_urlsafe(32)
    with connect() as c:c.execute('INSERT INTO studio_shares VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),rid,owner,time.time()+7*86400))
    return token

def shared(token):
    with connect() as c:
        row=c.execute('SELECT r.* FROM studio_shares s JOIN studio_runs r ON s.run_id=r.id WHERE s.token_hash=? AND s.expires>?',
                      (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
    data=decode(row)
    if data:
        # Explicit share contains conclusions, not original test evidence or business workload.
        result=data.get('result') or {}
        data={'state':data['state'],'created':data['created'],'result':{k:result.get(k) for k in ('model','composite','benchmark_cost','elapsed_s','cost_error','probe_summary')}}
    return data

def revoke(rid,owner):
    with connect() as c:c.execute('DELETE FROM studio_shares WHERE run_id=? AND owner=?',(rid,owner))

def save_analysis(rid,owner,analysis):
    if not get(rid,owner):raise ValueError('报告不存在')
    aid=secrets.token_urlsafe(16)
    with connect() as c:c.execute('INSERT INTO studio_analyses VALUES(?,?,?,?)',(aid,rid,time.time(),json.dumps(analysis,ensure_ascii=False)))
    return aid

def analyses(rid,owner):
    if not get(rid,owner):return []
    with connect() as c:
        return [{'id':r['id'],'created':r['created'],'analysis':json.loads(r['payload'])} for r in c.execute('SELECT * FROM studio_analyses WHERE run_id=? ORDER BY created DESC LIMIT 30',(rid,))]
