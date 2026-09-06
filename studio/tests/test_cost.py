import copy
import sys
import unittest
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cost_core import estimate,compare,observation_cost
from bench.observations import Collector
from concurrent.futures import ThreadPoolExecutor

def offer(model='demo',currency='USD',i='1',o='8',c='0.1'):
    return {'id':'demo','model':model,'currency':currency,'rates':{'input':i,'cached':c,'output':o}}

class CostTests(unittest.TestCase):
    def test_weighted_counterexample(self):
        w={'input':'1000000','cached':'0','output':'10000000'}
        result=compare(w,[offer(),offer(i='6',o='4')])[0]['results']
        self.assertEqual([Decimal(r['total']) for r in result],[Decimal(46),Decimal(81)])
    def test_missing_and_zero(self):
        q=offer(c=None)
        self.assertEqual(estimate({'input':'0','cached':'0','output':'0'},q)['total'],'0')
        self.assertIsNone(estimate({'input':'100','cached':'1','output':'2'},q)['total'])
        self.assertIsNone(estimate({'input':None,'cached':None,'output':None},q)['total'])
    def test_exact_decimal(self):
        r=estimate({'input':'3','cached':'0','output':'0'},offer(i='0.123456789123'))
        self.assertEqual(r['total'],'0.000000370370367369')
    def test_cache_and_credit(self):
        r=estimate({'input':'1000000','cached':'500000','output':'1000000'},offer(),credit='2')
        self.assertEqual(Decimal(r['gross']),Decimal('8.55'))
        self.assertEqual(Decimal(r['total']),Decimal('6.55'))
        self.assertEqual(estimate({'input':'0','cached':'0','output':'0'},offer(),credit='10')['total'],'0')
    def test_invalid_counts(self):
        for w in [{'input':'1','cached':'2','output':'0'},{'input':'-1','cached':'0','output':'0'},{'input':1.0,'cached':'0','output':'0'}]:
            with self.assertRaises(ValueError):estimate(w,offer())
    def test_different_models_and_currency_grouped(self):
        groups=compare({'input':'1','cached':'0','output':'1'},[offer(),offer(currency='CNY'),offer(model='other')])
        self.assertEqual(len(groups),3)
    def test_unknown_limits_not_eligible(self):
        self.assertEqual(estimate({'input':'1','cached':'0','output':'1'},offer())['eligibility_status'],'unknown')
        q=offer();q['limits']={'peak_rpm':5}
        self.assertEqual(estimate({'input':'1','cached':'0','output':'1','peak_rpm':'100'},q)['eligibility_status'],'ineligible')
    def test_fx_snapshot(self):
        r=estimate({'input':'1000000','cached':'0','output':'0'},offer(),fx={'rate':'7.1','to':'CNY','as_of':'2026-09-06'})
        self.assertEqual(r['converted_total'],'7.1')
        with self.assertRaises(ValueError):estimate({},offer(),fx={'rate':'0','to':'CNY','as_of':'2026-09-06'})
    def test_determinism_and_no_mutation(self):
        w={'input':'100','cached':'5','output':'30'};q=offer();saved=copy.deepcopy((w,q))
        self.assertEqual(estimate(w,q),estimate(w,q));self.assertEqual((w,q),saved)
    def test_unsupported_rule(self):
        q=offer();q['rule']='subscription'
        with self.assertRaises(ValueError):estimate({},q)
    def test_failed_call_is_not_free(self):
        calls=[{'call_id':'a','test_id':'x','operation':'chat','status':0,'usage':{'input':None,'cached':None,'output':None}}]
        self.assertIsNone(observation_cost(calls,offer())['total'])
    def test_concurrent_observations(self):
        c=Collector(max_calls=200)
        def one(_):
            r=c.reserve('chat');c.finish(r,{'status':200,'usage':{'prompt_tokens':10,'completion_tokens':3,'prompt_tokens_details':{'cached_tokens':0}}})
        with ThreadPoolExecutor(max_workers=8) as p:list(p.map(one,range(100)))
        self.assertEqual(len(c.snapshot()),100);self.assertEqual(len({r['call_id'] for r in c.snapshot()}),100)
    def test_absent_cache_is_unknown(self):
        c=Collector();r=c.reserve('chat');c.finish(r,{'usage':{'prompt_tokens':10,'completion_tokens':3}})
        self.assertIsNone(c.snapshot()[0]['usage']['cached'])
    def test_linear_additivity(self):
        q=offer();a=estimate({'input':'33','cached':'2','output':'12'},q);b=estimate({'input':'66','cached':'4','output':'24'},q)
        self.assertEqual(Decimal(a['gross'])*2,Decimal(b['gross']))

if __name__=='__main__':unittest.main()
