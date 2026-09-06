"""Versioned, paired capability observations. No model identity classifier."""
import hashlib,json,math,random,secrets,time
VERSION="paired-capability-1"
PARAMS={"temperature":0,"max_tokens":512,"repeats":2}

def config(reference=None):
    return {"version":VERSION,"seed":reference["config"]["seed"] if reference else secrets.token_hex(16),"params":dict(PARAMS)}

def cases(seed):
    rng=random.Random(seed);out=[]
    for i in range(18):
        kind=i%3
        if kind==0:
            vals=[rng.randint(-80,120) for _ in range(18)]
            prompt="从数组中筛选能被3整除的数，去重后从大到小排列："+json.dumps(vals)
            answer=sorted({n for n in vals if n%3==0},reverse=True)
        elif kind==1:
            x=rng.randint(1,20);ops=[];answer=x
            for _ in range(10):
                a,b=rng.randint(2,7),rng.randint(1,19);ops.append([a,b]);answer=(answer*a+b)%97
            prompt="初始 x=%d。依次对每对[a,b]执行 x=(x*a+b) mod 97。给出最终整数 x：%s"%(x,json.dumps(ops))
        else:
            rows=[{"id":j,"group":rng.choice(["A","B","C"]),"value":rng.randint(1,99)} for j in range(12)]
            group=rng.choice(["A","B","C"])
            prompt="记录中 group=%s 的 value 之和是多少？不存在则为0：%s"%(group,json.dumps(rows))
            answer=sum(r["value"] for r in rows if r["group"]==group)
        prompt+='。只输出 JSON 对象 {"answer":结果}，不输出解释。'
        out.append({"id":str(i),"category":["filter_sort","state_tracking","aggregation"][kind],"prompt":prompt,"expected":answer})
    return out

def exact_answer(text,expected):
    try:
        s=text.strip()
        if s.startswith("```json") and s.endswith("```"):s=s[7:-3].strip()
        got=json.loads(s)
        return isinstance(got,dict) and set(got)=={"answer"} and type(got["answer"]) is type(expected) and json.dumps(got["answer"])==json.dumps(expected)
    except (ValueError,TypeError,AttributeError):return False

def measure(client,cfg):
    items=cases(cfg["seed"]);rows=[];halted=None
    for repeat in range(PARAMS["repeats"]):
        if halted:break
        order=list(items);random.Random(cfg["seed"]+str(repeat)).shuffle(order)
        for item in order:
            if getattr(getattr(client,"collector",None),"cancelled",None) is not None and client.collector.cancelled.is_set():break
            try:
                r=client.chat(messages=[{"role":"user","content":item["prompt"]}],max_tokens=512,temperature=0,timeout=45)
            except ValueError:
                halted="调用已停止；已完成样本保留";break
            valid=r.get("ok") and r.get("finish_reason")=="stop" and bool((r.get("content") or "").strip())
            rows.append({"id":item["id"],"repeat":repeat,"category":item["category"],
                         "status":"complete" if valid else "unavailable",
                         "correct":exact_answer(r.get("content"),item["expected"]) if valid else None,
                         "answer":(r.get("content") or "")[:2400],"finish_reason":r.get("finish_reason"),"http_status":r.get("status"),
                         "prompt_hash":hashlib.sha256(item["prompt"].encode()).hexdigest()})
    return {"config":cfg,"observed_at":time.time(),"rows":rows,"cases":items,"halted":halted}

def case_scores(m):
    scores={}
    for item in cases(m["config"]["seed"]):
        rs=[r for r in m["rows"] if r["id"]==item["id"]]
        if len(rs)==2 and {r["repeat"] for r in rs}=={0,1} and all(r["status"]=="complete" for r in rs):
            scores[item["id"]]=all(r["correct"] is True for r in rs)
    return scores

def compare(reference,current):
    result={"status":"insufficient_evidence","summary":"未提供可比较的参考报告，不能判断降级。",
            "identity_verified":False,"calibration":"实验性规则；未完成真实模型误报/漏报校准", "p_value":None}
    if not reference:return result
    if reference.get("config")!=current.get("config"):
        result["summary"]="题集或调用参数不一致，不能比较。";return result
    if abs(current["observed_at"]-reference["observed_at"])>7*86400:
        result["summary"]="参考报告已超过7天，请重新采样。";return result
    a,b=case_scores(reference),case_scores(current);ids=set(a)&set(b)
    result.update({"paired_cases":len(ids),"total_cases":18,"reference_source":"用户指定的私有报告，非官方认证"})
    if len(ids)<17:
        result["summary"]="有效配对样本不足17/18，失败或截断不能算模型答错。";return result
    base=sum(a[i] for i in ids)/len(ids);target=sum(b[i] for i in ids)/len(ids)
    result.update({"reference_success_rate":base,"target_success_rate":target})
    if base<0.8:
        result["summary"]="参考样本自身通过率低于80%，不适合作为本题集的降级对照。";return result
    losses=sum(a[i] and not b[i] for i in ids);gains=sum(b[i] and not a[i] for i in ids);n=losses+gains
    p=sum(math.comb(n,k) for k in range(losses,n+1))/(2**n) if n else 1.0
    result.update({"losses":losses,"gains":gains,"p_value":p,"success_rate_drop":base-target,
                   "test":"单侧配对符号检验，以题为单位；相关任务及多次比较会限制解释"})
    flagged=base-target>=0.2 and p<=0.01
    result.update({"status":"capability_deviation" if flagged else "no_significant_deviation",
                   "summary":"本题集表现显著低于指定参考；需独立复测，不能确定替换模型或服务商意图。" if flagged else "本题集未发现显著下降；不证明模型身份，也不排除间歇降级。"})
    return result
