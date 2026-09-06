from ..registry import register
ZH_SUFFIX="今天天气很好我们去公园散步然后去图书馆看书傍晚回家做饭"*2
ASCII_SUFFIX="The quick brown fox jumps over the lazy dog near ri"
def run(ctx):
    rows=[]
    for suffix in [ZH_SUFFIX,ASCII_SUFFIX]:
        values=[]
        for text in ["回复：OK","回复：OK"+suffix]:
            r=ctx["client"].chat(messages=[{"role":"user","content":text}],max_tokens=5,temperature=0,timeout=45)
            values.append((r.get("usage") or {}).get("prompt_tokens") if r.get("ok") else None)
        valid=all(type(v) is int and v>=0 for v in values)
        rows.append({"characters":len(suffix),"reported_delta":values[1]-values[0] if valid else None})
    return {"light":"info","summary_zh":"记录服务商报告的分词增量；没有独立计量及版本基线，不判定换模。",
            "metrics":{"measurements":rows,"source":"provider_reported"},"evidence":{}}
register("tokenizer","分词计量观察","authenticity","记录追加文本的 Token 增量与真实字符数。","usage 可被代理改写，仅作弱信号。",15,False,run)
