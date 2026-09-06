import sys,unittest,json,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bench import probe
from bench.scoring import score_run
from bench.tests import identity,tokenizer
from cost_core import estimate
import plans

class AnswerClient:
    def __init__(self,cfg,bad=()):
        self.answers={c["prompt"]:c for c in probe.cases(cfg["seed"])};self.bad=bad;self.calls=0
    def chat(self,**kw):
        self.calls+=1;c=self.answers[kw["messages"][0]["content"]]
        return {"ok":True,"finish_reason":"stop","status":200,"content":json.dumps({"answer":"wrong" if c["id"] in self.bad else c["expected"]})}
class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.cfg=probe.config();self.base=probe.measure(AnswerClient(self.cfg),self.cfg)
    def test_no_tests_does_not_certify(self):
        r=score_run({});self.assertIsNone(r["composite"]);self.assertTrue(all(v[1]=="info" for v in r["verdict"]))
    def test_exact_grading_rejects_explanation_and_wrong_type(self):
        for text in ['7/9小于5/7，因此5/7更大。','{"answer":true}','{"answer":1,"other":2}','{"answer":"1"}']:
            self.assertFalse(probe.exact_answer(text,1))
        self.assertTrue(probe.exact_answer('{"answer":1}',1))
    def test_generated_reproducible_and_changes(self):
        self.assertEqual(probe.cases('a'),probe.cases('a'));self.assertNotEqual(probe.cases('a'),probe.cases('b'))
    def test_same_backend_no_deviation_and_36_calls(self):
        c=AnswerClient(self.cfg);current=probe.measure(c,self.cfg)
        self.assertEqual(c.calls,36);self.assertEqual(probe.compare(self.base,current)['status'],'no_significant_deviation')
    def test_known_replacement_detected(self):
        current=probe.measure(AnswerClient(self.cfg,{str(i) for i in range(18)}),self.cfg)
        r=probe.compare(self.base,current);self.assertEqual(r['status'],'capability_deviation');self.assertFalse(r['identity_verified'])
    def test_partial_replacement_detected(self):
        current=probe.measure(AnswerClient(self.cfg,{str(i) for i in range(9)}),self.cfg)
        self.assertEqual(probe.compare(self.base,current)['status'],'capability_deviation')
    def test_small_difference_not_certified(self):
        current=probe.measure(AnswerClient(self.cfg,{'1'}),self.cfg)
        self.assertEqual(probe.compare(self.base,current)['status'],'no_significant_deviation')
    def test_missing_or_truncated_not_wrong_answers(self):
        current=copy.deepcopy(self.base)
        for row in current['rows'][:3]:row['status']='unavailable';row['correct']=None
        self.assertEqual(probe.compare(self.base,current)['status'],'insufficient_evidence')
    def test_missing_stale_and_mismatched_baseline(self):
        self.assertEqual(probe.compare(None,self.base)['status'],'insufficient_evidence')
        other=copy.deepcopy(self.base);other['config']['params']['max_tokens']=20
        self.assertEqual(probe.compare(other,self.base)['status'],'insufficient_evidence')
        other=copy.deepcopy(self.base);other['observed_at']-=8*86400
        self.assertEqual(probe.compare(other,self.base)['status'],'insufficient_evidence')
    def test_weak_reference(self):
        weak=probe.measure(AnswerClient(self.cfg,{str(i) for i in range(9)}),self.cfg)
        self.assertEqual(probe.compare(weak,self.base)['status'],'insufficient_evidence')
    def test_identity_is_observation_only(self):
        class C:
            def chat(self,**kw):return {'ok':True,'content':'gateway OpenAI'}
        r=identity.run({'client':C()});self.assertEqual(r['light'],'info');self.assertFalse(r['metrics']['identity_verified'])
    def test_actual_tokenizer_length(self):
        class C:
            def chat(self,**kw):return {'ok':True,'usage':{'prompt_tokens':len(kw['messages'][0]['content'])}}
        r=tokenizer.run({'client':C()});self.assertEqual(r['metrics']['measurements'][0]['characters'],54);self.assertEqual(r['light'],'info')
    def test_prepaid_cash_conversion(self):
        offer={'model':'demo','currency':'CNY','rates':{'input':'1','cached':'0','output':'2'},'credit_pack':{'paid':'80','units':'100'}}
        r=estimate({'input':'1000000','cached':'0','output':'1000000'},offer)
        self.assertEqual(r['total'],'2.4')
        offer['credit_pack']['units']='0'
        with self.assertRaises(ValueError):estimate({'input':'0','cached':'0','output':'0'},offer)
    def test_subscription_not_quota_conversion(self):
        r=plans.compare({'plans':[{'name':'年付','currency':'CNY','amount':'1200','months':'12'}]})
        self.assertEqual(r['plans'][0]['monthly_equivalent'],'100');self.assertEqual(r['plans'][0]['fit'],'unknown')
        with self.assertRaises(ValueError):plans.compare({'plans':[{'name':'bad','currency':'USD','amount':'10','months':'0'}]})

    def test_budget_stop_preserves_partial_observations(self):
        class StopClient(AnswerClient):
            def chat(self,**kw):
                if self.calls>=3:raise ValueError('limit')
                return super().chat(**kw)
        m=probe.measure(StopClient(self.cfg),self.cfg)
        self.assertEqual(len(m['rows']),3);self.assertTrue(m['halted'])
        self.assertEqual(probe.compare(self.base,m)['status'],'insufficient_evidence')
