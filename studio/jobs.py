from concurrent.futures import ThreadPoolExecutor
import threading
import time
from bench import runner
from bench.observations import Collector
from cost_core import observation_cost,estimate
import repository

POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='studio')
LOCK=threading.Lock();CANCEL={};EVENTS={}

def submit(rid,base,key,model,tests,offer,workload):
    cancelled=threading.Event()
    with LOCK:CANCEL[rid]=cancelled;EVENTS[rid]=[]
    POOL.submit(execute,rid,base,key,model,tests,offer,workload,cancelled)

def execute(rid,base,key,model,tests,offer,workload,cancelled):
    repository.update(rid,'running')
    collector=Collector(cancelled)
    def progress(event):
        # No raw responses in polling progress; full report remains owner-only.
        item={k:event[k] for k in ('type','test','status','name_zh') if k in event}
        with LOCK:EVENTS[rid].append(item)
    try:
        result=runner.run_benchmark(base,key,model,tests,progress,collector)
        result['schema_version']=3
        if offer:
            try:
                result['benchmark_cost']=observation_cost(result['observations'],offer)
                if workload:result['workload_estimate']=estimate(workload,offer)
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
