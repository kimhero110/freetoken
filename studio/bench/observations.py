import threading
import time
import uuid

class Collector:
    def __init__(self, cancelled=None, max_calls=90, max_seconds=1200):
        self.lock=threading.Lock();self.records=[];self.started=0
        self.test_id='';self.cancelled=cancelled or threading.Event()
        self.deadline=time.monotonic()+max_seconds;self.max_calls=max_calls
    def reserve(self, operation):
        with self.lock:
            if self.cancelled.is_set() or time.monotonic()>self.deadline:
                raise ValueError('任务已取消或超过时限')
            if self.started>=self.max_calls: raise ValueError('已达到任务调用次数上限')
            self.started+=1
            return {'call_id':uuid.uuid4().hex,'test_id':self.test_id,'operation':operation,'created_at':time.time()}
    def finish(self, record, result):
        raw=result.get('usage') or {}
        def count(value):
            return str(value) if type(value) is int and 0<=value<=10**15 else None
        i=count(raw.get('prompt_tokens',raw.get('input_tokens')))
        o=count(raw.get('completion_tokens',raw.get('output_tokens')))
        details=raw.get('prompt_tokens_details') or raw.get('input_tokens_details') or {}
        cached=count(raw.get('prompt_cache_hit_tokens',details.get('cached_tokens')))
        record.update(status=result.get('status',0),ok=result.get('ok',False),
                      usage={'input':i,'cached':cached,'output':o},usage_present=bool(raw),
                      elapsed_ms=result.get('elapsed_ms'),adapter_version='openai-usage-v1')
        with self.lock: self.records.append(record)
    def snapshot(self):
        with self.lock: return [dict(r) for r in self.records]
