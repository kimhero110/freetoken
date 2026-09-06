from concurrent.futures import ThreadPoolExecutor
import threading
import time
import os
from bench import runner
from bench.observations import Collector
from cost_core import observation_cost,estimate
import repository

POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='studio')
LOCK=threading.Lock();CANCEL={};EVENTS={}

def submit(rid,base,key,model,tests,offer,workload,credit="0",fx=None,probe_config=None):
    cancelled=threading.Event()
    with LOCK:CANCEL[rid]=cancelled;EVENTS[rid]=[]
    POOL.submit(execute,rid,base,key,model,tests,offer,workload,cancelled,credit,fx,probe_config)

def execute(rid,base,key,model,tests,offer,workload,cancelled,credit,fx,probe_config):
    repository.update(rid,'running')
    collector=Collector(cancelled)
    def progress(event):
        # No raw responses in polling progress; full report remains owner-only.
        item={k:event[k] for k in ('type','test','status','name_zh') if k in event}
        with LOCK:EVENTS[rid].append(item)
    try:
        result=runner.run_benchmark(base,key,model,tests,progress,collector,probe_config)
        result['schema_version']=4
        result['probe_summary']={k:v for k,v in result.get('tests',{}).get('downgrade',{}).get('metrics',{}).get('comparison',{}).items() if k in ('status','summary','identity_verified','calibration','paired_cases','total_cases','reference_success_rate','target_success_rate','p_value')}
        result['app_revision']=os.getenv('STUDIO_RELEASE','dev')
        if offer:
            try:
                result['benchmark_cost']=observation_cost(result['observations'],offer)
                if workload:result['workload_estimate']=estimate(workload,offer,credit,fx)
            except (ValueError,ArithmeticError):result['cost_error']='成本分析未完成，质量测试结果已保留。'
        else:result['cost_error']='未选择匹配报价；本次用量已记录，费用未知。'
        repository.update(rid,'cancelled' if cancelled.is_set() else 'done',result)
    except Exception:
        repository.update(rid,'cancelled' if cancelled.is_set() else 'failed',
                          {'observations':collector.snapshot()},'任务未完成；已发请求可能产生费用，未自动重试。')
    finally:
        key=None
        with LOCK:CANCEL.pop(rid,None);EVENTS.pop(rid,None)

def cancel(rid):
    with LOCK:
        event=CANCEL.get(rid)
        if event:event.set();return True
    return False

def events(rid):
    with LOCK:return list(EVENTS.get(rid,[]))
