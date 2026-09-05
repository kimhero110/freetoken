import re

from ..registry import register


def run(ctx):
    c = ctx["client"]
    r = c.chat(messages=[{"role": "user", "content":
                          "请写一篇题为《城市夜晚》的散文，要求：至少 20 个自然段，每段以“第N段”开头（N 为 1 到 20 的数字），每段至少两句话。直接开始正文。"}],
               max_tokens=3000, temperature=0.5, timeout=180)
    if not r["ok"]:
        return {"light": "fail", "summary_zh": "长输出请求失败：" + r["error"][:100],
                "metrics": {}, "evidence": {"error": r["error"][:200]}}

    content = r.get("content") or ""
    completion = (r["usage"] or {}).get("completion_tokens") or (len(content) // 2)
    finish = r.get("finish_reason") or ""
    found = re.findall(r"第(\d+)段", content)
    nums = [int(x) for x in found if 1 <= int(x) <= 25]
    monotonic_score = 0
    if nums:
        expected = list(range(1, min(21, max(nums) + 1)))
        hit = sum(1 for e in expected[:20] if e in set(nums))
        monotonic_score = hit

    complete_enough = completion >= 1500 or monotonic_score >= 20
    truncated_mid = finish == "length" and not complete_enough

    if truncated_mid:
        light, msg = "fail", "输出被截断（finish_reason=length，仅 %s tokens / %d/20 段）" % (completion, monotonic_score)
    elif complete_enough and monotonic_score >= 18:
        light, msg = "pass", "长输出完整：%s tokens，%d/20 段编号齐全" % (completion, monotonic_score)
    elif monotonic_score >= 10 or completion >= 800:
        light, msg = "warn", "长输出基本完成但编号不全（%s tokens，%d/20 段，finish=%s）" % (completion, monotonic_score, finish or "-")
    else:
        light, msg = "fail", "长输出能力不足（仅 %s tokens，%d/20 段）" % (completion, monotonic_score)

    return {
        "light": light,
        "summary_zh": msg,
        "metrics": {"completion_tokens": completion, "segments_found": monotonic_score,
                    "finish_reason": finish},
        "evidence": {"head": content[:150], "tail": content[-150:]},
    }


register("longgen", "长输出完整性", "capability",
         "要求生成 20 段结构化长文，检验 completion 长度、编号连续性与是否静默截断。",
         "≥18/20 段且未截断=通过；≥10 段或 ≥800 tokens=可疑；更少或截断=未通过。",
         90, False, run)
