import uuid

from ..registry import register


def build_haystack(target_chars=26000):
    codes = [uuid.uuid4().hex[:8].upper() for _ in range(3)]
    needles = [
        "【机密备忘A】秘密口令A是%s，请牢记。" % codes[0],
        "【机密备忘B】秘密口令B是%s，请牢记。" % codes[1],
        "【机密备忘C】秘密口令C是%s，请牢记。" % codes[2],
    ]
    parts = []
    total = 0
    i = 0
    inserted = [False, False, False]
    while total < target_chars:
        i += 1
        seg = "第%d条运维日志：机房巡检完成，各项指标正常，未发现异常告警。" % i
        parts.append(seg)
        total += len(seg)
        for idx, frac in enumerate((0.15, 0.5, 0.85)):
            if not inserted[idx] and total >= target_chars * frac:
                parts.append(needles[idx])
                total += len(needles[idx])
                inserted[idx] = True
    return "\n".join(parts), codes


def run(ctx):
    c = ctx["client"]
    haystack, codes = build_haystack()
    prompt = ("以下是一段很长的运维日志。请在阅读后回答：文中出现的三条秘密口令分别是什么？"
              "按 A、B、C 顺序每行输出一个，只输出口令本身。\n\n") + haystack
    r = c.chat(messages=[{"role": "user", "content": prompt}],
               max_tokens=200, temperature=0, timeout=120)
    if not r["ok"]:
        return {"light": "fail", "summary_zh": "长上下文请求失败：" + r["error"][:100],
                "metrics": {}, "evidence": {"error": r["error"][:200]}}

    content = r["content"].upper()
    hits = [code for code in codes if code in content]
    n = len(hits)
    light = "pass" if n == 3 else ("warn" if n == 2 else "fail")
    approx_tokens = r["usage"].get("prompt_tokens") if r["usage"] else len(prompt) // 2
    return {
        "light": light,
        "summary_zh": "长上下文召回 %d/3（prompt 实测 %s tokens）" % (
            n, ("{:,}".format(approx_tokens) if isinstance(approx_tokens, int) else "约1.5万")),
        "metrics": {"needles_found": n, "prompt_tokens": approx_tokens},
        "evidence": {"answer_head": r["content"][:200]},
    }


register("needle", "针海长上下文召回", "capability",
         "约 2.6 万字符（1.5~2 万 token 级）中文长文中 15%/50%/85% 三个深度位置各埋入随机口令，检验截断与遗忘。",
         "3/3 通过；2/3 可疑；≤1 未通过。",
         60, False, run)
