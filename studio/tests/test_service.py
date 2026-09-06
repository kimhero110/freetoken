import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import repository
import server_bench
from bench import store
from bench.transport import resolve

class MockModel(BaseHTTPRequestHandler):
    calls=0
    def log_message(self,*args):pass
    def do_POST(self):
        MockModel.calls+=1
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        data={'choices':[{'message':{'content':'OK'},'finish_reason':'stop'}],
              'usage':{'prompt_tokens':10,'completion_tokens':2,'prompt_tokens_details':{'cached_tokens':0}}}
        raw=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();repository.DB=Path(cls.temp.name)/'reports.db';store._DB_PATH=str(repository.DB)
        cls.env=patch.dict(os.environ,{'STUDIO_TEST_LOOPBACK':'1','STUDIO_LOCAL_HTTP':'1'});cls.env.start()
        cls.model=ThreadingHTTPServer(('127.0.0.1',0),MockModel);threading.Thread(target=cls.model.serve_forever,daemon=True).start()
        cls.web=ThreadingHTTPServer(('127.0.0.1',0),server_bench.Handler);threading.Thread(target=cls.web.serve_forever,daemon=True).start()
        cls.base=f'http://127.0.0.1:{cls.web.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.web.shutdown();cls.model.shutdown();cls.web.server_close();cls.model.server_close();cls.env.stop();cls.temp.cleanup()
    def request(self,path,data=None,cookie=None,csrf=True):
        headers={}
        if cookie:headers['Cookie']=cookie
        if data is not None:
            headers['Content-Type']='application/json'
            if csrf:headers['X-Studio-Request']='1'
        request=urllib.request.Request(self.base+path,data=None if data is None else json.dumps(data).encode(),headers=headers)
        try:r=urllib.request.urlopen(request)
        except urllib.error.HTTPError as e:r=e
        body=r.read();return r.status,json.loads(body),r.headers
    def test_full_lifecycle_private_share_revoke_and_no_extra_calls(self):
        status,_,headers=self.request('/api/history');cookie=headers['Set-Cookie'].split(';')[0]
        quote={'model':'demo','currency':'USD','rates':{'input':'1','cached':'0.1','output':'8'}}
        payload={'base_url':f'http://127.0.0.1:{self.model.server_port}/v1','api_key':'private-test-key',
                 'model':'demo','tests':['headers'],'with_cost':True,'offer':quote,'credit':'1',
                 'workload':{'input':'1000000','cached':'0','output':'10000000'},'idempotency_key':'test-idempotency-0001'}
        before=MockModel.calls
        status,created,_=self.request('/api/runs',payload,cookie);self.assertEqual(status,202,created);rid=created['id']
        _,duplicate,_=self.request('/api/runs',payload,cookie);self.assertEqual(duplicate['id'],rid)
        for _ in range(50):
            _,run,_=self.request('/api/runs/'+rid,cookie=cookie)
            if run['state']=='done':break
            time.sleep(.05)
        self.assertEqual(run['state'],'done',run);self.assertEqual(MockModel.calls-before,1)
        self.assertEqual(run['result']['benchmark_cost']['covered_calls'],1)
        self.assertEqual(run['result']['workload_estimate']['total'],'80')
        self.assertEqual(self.request('/api/runs/'+rid)[0],404)
        raw=repository.DB.read_bytes();self.assertNotIn(b'private-test-key',raw)
        _,share,_=self.request('/api/runs/'+rid+'/share',{},cookie)
        _,public,_=self.request('/api/shares/'+share['path'].rsplit('/',1)[1]);self.assertNotIn('workload_estimate',public['result']);self.assertNotIn('tests',public['result'])
        self.request('/api/runs/'+rid+'/revoke',{},cookie)
        self.assertEqual(self.request('/api/shares/'+share['path'].rsplit('/',1)[1])[0],404)
        self.request('/api/runs/'+rid+'/estimate',{'offer':quote,'workload':payload['workload']},cookie)
        self.assertEqual(MockModel.calls-before,1)
    def test_budget_no_key_or_model_call(self):
        before=MockModel.calls
        status,r,_=self.request('/api/cost/estimate',{'offer_id':'deepseek:deepseek-v4-flash:peak','workload':{'input':'1000000','cached':'0','output':'1000000'}})
        self.assertEqual(status,200);self.assertEqual(r['total'],'1.76');self.assertEqual(MockModel.calls,before)
    def test_csrf_and_bad_quote(self):
        self.assertEqual(self.request('/api/cost/estimate',{},csrf=False)[0],403)
        self.assertEqual(self.request('/api/cost/estimate',{'offer_id':'not-known'})[0],400)
    def test_restart_does_not_replay(self):
        rid,_=repository.create('owner','restart-test',{})
        repository.update(rid,'running');repository.recover()
        self.assertEqual(repository.get(rid,'owner')['state'],'interrupted')
    def test_private_dns_blocked_without_test_override(self):
        with patch.dict(os.environ,{'STUDIO_TEST_LOOPBACK':'0'}):
            with self.assertRaises(ValueError):resolve('https://127.0.0.1/v1')
            with self.assertRaises(ValueError):resolve('http://example.com/v1')
            with self.assertRaises(ValueError):resolve('https://user:password@example.com/v1')

if __name__=='__main__':unittest.main()
