from ..registry import register
from .. import baselines as B

ZH_SUFFIX = "今天天气很好我们去公园散步然后去图书馆看书傍晚回家做饭" * 2  # 40 chars
ASCII_SUFFIX = "The quick brown fox jumps over the lazy dog near ri"  # 50 chars


def _delta(client, base_msgs, suffix):
    r1 = client.chat(messages=base_msgs, max_tokens=5, temperature=0, timeout=45)
    r2 = client.chat(messages=[dict(base_msgs[0], content=base_msgs[0]["content"] + suffix)],
                     max_tokens=5, temperature=0, timeout=45)
    if not (r1["ok"] and r2["ok"]):
        return None, r1.get("error") or r2.get("error")
    u1 = (r1["usage"] or {}).get("prompt_tokens")
    u2 = (r2["usage"] or {}).get("prompt_tokens")
    if u1 is None or u2 is None:
        return None, "usage.prompt_tokens 未返回"
    return u2 - u1, None


def run(ctx):
    c = ctx["client"]
    family = ctx["family"]
    base = [{"role": "user", "content": "回复：OK"}]

    zh_delta, e1 = _delta(c, base, ZH_SUFFIX)
    if zh_delta is None:
        return {"light": "warn", "summary_zh": "无法测量分词（%s）——协议未返回 usage" % (e1 or "")[:80],
                "metrics": {"usage_available": False}, "evidence": {"error": (e1 or "")[:200]}}
    ascii_delta, _ = _delta(c, base, ASCII_SUFFIX)

    metrics = {"zh_delta_tokens": zh_delta, "ascii_delta_tokens": ascii_delta,
               "usage_available": True, "family": family}
    zh_range = B.TOKENIZER_ZH_PER_CHAR.get(family)
    if not zh_range:
        return {"light": "info",
                "summary_zh": "分词测量：中文 40 字 = %d tokens（该模型家族暂无基线，仅记录）" % zh_delta,
                "metrics": metrics, "evidence": {}}
    lo, hi = zh_range[0] * 40, zh_range[1] * 40
    ok = lo <= zh_delta <= hi
    slightly_off = lo * 0.75 <= zh_delta <= hi * 1.3
    if ok:
        light, msg = "pass", "分词特征与 %s 家族一致（中文 40 字 ≈ %d tokens，参考区间 %d~%d）" % (
            family, zh_delta, round(lo), round(hi))
    elif slightly_off:
        light, msg = "warn", "分词特征略偏离 %s 家族区间（测得 %d，参考 %d~%d）" % (
            family, zh_delta, round(lo), round(hi))
    else:
        light, msg = "fail", "分词特征与 %s 家族明显不符（测得 %d，参考 %d~%d），疑似换壳模型" % (
            family, zh_delta, round(lo), round(hi))
    return {"light": light, "summary_zh": msg, "metrics": metrics, "evidence": {}}


register("tokenizer", "分词器指纹", "authenticity",
         "对比追加固定文本前后的 usage.prompt_tokens 增量（模板开销互相抵消），与模型家族的公开分词特征比对。",
         "落在家族参考区间=通过；偏离30%内=可疑；明显偏离=未通过（强信号）。无 usage 返回=协议不规范。",
         15, True, run)
