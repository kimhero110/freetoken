#!/usr/bin/env python3
"""Studio v3: private asynchronous evaluation and deterministic cost analysis."""
import hashlib
import json
import os
import re
import secrets
import threading
import time
from collections import defaultdict,deque
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from bench import pages,store,probe
from bench.tests import *
from bench.registry import all_meta,TESTS
from bench.client import Client
from bench.guard import ssrf_guard
from cost_core import estimate,compare,VERSION
import jobs,pricing,repository,plans

ROOT=Path(__file__).parent
HOST=os.getenv('BENCH_HOST','100.64.0.17');PORT=int(os.getenv('BENCH_PORT','8500'))
COUNTERS=defaultdict(deque);RATE_LOCK=threading.Lock()

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass  # no report capability URLs or user input in access logs
    def session(self):
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except Exception:pass
        raw=cookie['studio_session'].value if 'studio_session' in cookie else ''
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}',raw):
            raw=secrets.token_urlsafe(32);self.new_cookie=raw
        return hashlib.sha256(raw.encode()).hexdigest()
    def send(self,status,body,ctype='application/json; charset=utf-8',extra=None):
        encoded=body if isinstance(body,bytes) else body.encode()
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(encoded)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY')
        if getattr(self,'new_cookie',None):
            secure='' if os.getenv('STUDIO_LOCAL_HTTP')=='1' else '; Secure'
            self.send_header('Set-Cookie',f'studio_session={self.new_cookie}; Path=/; HttpOnly; SameSite=Lax; Max-Age=7776000{secure}')
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers()
        try:self.wfile.write(encoded)
        except (BrokenPipeError,ConnectionResetError):pass
    def json(self,status,data):self.send(status,json.dumps(data,ensure_ascii=False,allow_nan=False))
    def do_GET(self):
        self.owner=self.session();p=urlsplit(self.path).path
        if p=='/healthz':return self.json(200,{'ok':True,'version':'4.0','probe':probe.VERSION,'engine':VERSION,'release':os.getenv('STUDIO_RELEASE','dev')})
        if p in ('/','/cost','/compare','/reports','/plans','/api-cost','/probe','/criteria','/select') or re.fullmatch(r'/(report|share)/[\w-]+',p):
            # Legacy URLs remain readable, never indexed in private history.
            if p.startswith('/report/'):
                rid=p.rsplit('/',1)[-1]
                if not repository.get(rid,self.owner):
                    legacy=store.get_run(rid)
                    if legacy:return self.send(200,pages.report_page(legacy),'text/html; charset=utf-8')
            return self.send(200,(ROOT/'static/index.html').read_bytes(),'text/html; charset=utf-8')
        if p=='/criteria':return self.send(200,pages.criteria_page(),'text/html; charset=utf-8')
        if p in ('/static/app.js','/static/style.css'):
            return self.send(200,(ROOT/p.lstrip('/')).read_bytes(),'application/javascript' if p.endswith('.js') else 'text/css')
        if p=='/api/pricebook':return self.json(200,pricing.pricebook())
        if p=='/api/meta':return self.json(200,{'tests':[{k:m[k] for k in ('tid','name_zh','dim','desc_zh','est_s','fast')} for m in all_meta()]})
        if p=='/api/history':return self.json(200,repository.history(self.owner))
        if p.startswith('/api/runs/'):
            rid=p.rsplit('/',1)[-1];run=repository.get(rid,self.owner)
            if not run:return self.json(404,{'error':'任务不存在或不属于当前会话'})
            run['events']=jobs.events(rid);run['analyses']=repository.analyses(rid,self.owner)
            return self.json(200,run)
        if p.startswith('/api/shares/'):
            report=repository.shared(p.rsplit('/',1)[-1])
            return self.json(200 if report else 404,report or {'error':'分享不存在、已撤销或已过期'})
        self.json(404,{'error':'页面不存在'})
    def limited(self,kind,limit,period):
        # Reverse proxy must overwrite X-Real-IP; direct access uses peer IP only.
        peer=self.client_address[0]
        trusted=set(os.getenv('STUDIO_TRUSTED_PROXIES','').split(','))
        identity=self.headers.get('X-Real-IP',peer) if peer in trusted else peer
        key=(identity,kind);now=time.monotonic()
        with RATE_LOCK:
            if len(COUNTERS)>10000:
                for k in list(COUNTERS):
                    if not COUNTERS[k] or now-COUNTERS[k][-1]>3600:COUNTERS.pop(k,None)
            q=COUNTERS[key]
            while q and now-q[0]>period:q.popleft()
            if len(q)>=limit:raise ValueError('请求过于频繁，请稍后再试')
            q.append(now)
    def do_POST(self):
        self.owner=self.session();p=urlsplit(self.path).path
        try:
            origin=self.headers.get('Origin')
            allowed={'https://studio.witkit.zone','https://test.witkit.zone'}
            if os.getenv('STUDIO_LOCAL_HTTP')=='1':allowed.add('http://'+self.headers.get('Host',''))
            if self.headers.get('X-Studio-Request')!='1' or (origin and origin not in allowed):
                return self.json(403,{'error':'请通过 Studio 页面操作'})
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=65536:raise ValueError('请求体大小不合法')
            self.connection.settimeout(20)
            data=json.loads(self.rfile.read(n));
            if not isinstance(data,dict):raise ValueError('请求必须是对象')
            self.limited('all',120,60)
            if p=='/api/plans/compare':return self.json(200,plans.compare(data))
            if p=='/api/cost/estimate':
                return self.json(200,estimate(data.get('workload',{}),pricing.select(data),data.get('credit','0'),data.get('fx')))
            if p=='/api/cost/compare':
                offers=data.get('offers',[])
                if not isinstance(offers,list) or len(offers)>20:raise ValueError('最多比较20个报价')
                return self.json(200,{'groups':compare(data.get('workload',{}),[pricing.select(o) for o in offers])})
            if p in ('/api/models','/api/runs','/api/benchmark'):
                self.limited('remote',10,3600)
                base=data.get('base_url','').strip();key=data.get('api_key','').strip();model=data.get('model','').strip()
                if not base or not 6<=len(key)<=4096:raise ValueError('请填写接入地址与本次使用的 Key')
                ssrf_guard(base)
                if p=='/api/models':
                    status,body,_=Client(base,key).models()
                    if status!=200 or not isinstance(body,dict):raise ValueError('模型列表获取失败，可手动填写模型；未自动重试')
                    return self.json(200,{'models':[str(m['id']) for m in body.get('data',[])[:500] if isinstance(m,dict) and 'id' in m]})
                tests=data.get('tests',[])
                if not model or len(model)>200 or not isinstance(tests,list) or not tests or any(t not in TESTS for t in tests):raise ValueError('请选择模型及有效测试项目')
                offer=pricing.select(data,model) if data.get('with_cost') else None
                workload=data.get('workload') if data.get('with_cost') else None
                credit=data.get('credit','0');fx=data.get('fx')
                if offer and workload:estimate(workload,offer,credit,fx)
                idem=data.get('idempotency_key','')
                if not re.fullmatch(r'[\w-]{16,80}',idem):raise ValueError('缺少有效的任务幂等标识')
                reference_id=data.get('reference_id','')
                reference=None
                if reference_id:
                    ref=repository.get(reference_id,self.owner)
                    if not ref or ref['state']!='done':raise ValueError('参考报告不存在、尚未完成或不属于当前会话')
                    reference=((ref.get('result') or {}).get('tests',{}).get('downgrade',{}).get('evidence',{}).get('measurement'))
                    if not reference or reference.get('config',{}).get('version')!=probe.VERSION:raise ValueError('参考报告没有当前版本探针数据')
                    if time.time()-reference['observed_at']>7*86400:raise ValueError('参考报告超过7天，请重新采样')
                    if 'downgrade' not in tests:raise ValueError('对照必须选择能力对照探针')
                probe_config={'config':probe.config(reference),'reference':reference,'reference_id':reference_id,'reference_source':{k:ref['result'].get(k) for k in ('host','model','created')} if reference else None}
                payload={'reference_id':reference_id,'model':model,'tests':tests,'offer':offer,'workload':workload,'credit':credit,'fx':fx}
                rid,created=repository.create(self.owner,idem,payload)
                if created:jobs.submit(rid,base,key,model,tests,offer,workload,credit,fx,probe_config)
                return self.json(202,{'id':rid,'created':created})
            match=re.fullmatch(r'/api/runs/([\w-]+)/(cancel|share|revoke|estimate)',p)
            if match:
                rid,action=match.groups();run=repository.get(rid,self.owner)
                if not run:return self.json(404,{'error':'任务不存在'})
                if action=='cancel':return self.json(200,{'cancel_requested':jobs.cancel(rid)})
                if action=='share':
                    if run['state'] not in ('done','cancelled','failed'):raise ValueError('任务结束后才能分享')
                    return self.json(200,{'path':'/share/'+repository.share(rid,self.owner),'expires_days':7})
                if action=='revoke':repository.revoke(rid,self.owner);return self.json(200,{'revoked':True})
                analysis=estimate(data.get('workload',{}),pricing.select(data),data.get('credit','0'),data.get('fx'))
                return self.json(200,{'id':repository.save_analysis(rid,self.owner,analysis),'analysis':analysis})
            return self.json(404,{'error':'接口不存在'})
        except (ValueError,TypeError,KeyError) as e:
            return self.json(400,{'error':str(e)[:180]})
        except Exception:
            return self.json(500,{'error':'处理失败；未自动重试模型调用，请检查任务状态'})

if __name__=='__main__':
    repository.recover()
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
