from ..registry import register
from ..client import ngram_sim

MATH_Q = "计算 (37 * 23) + (456 / 3) 的值。只输出最终数字，不要任何其他文字。"
STYLE_Q = "用恰好两句话描述一场夏日的雷阵雨。不要任何前缀。"


def run(ctx):
    c = ctx["client"]
    math_answers = []
    style_answers = []
    for i in range(5):
        r = c.chat(messages=[{"role": "user", "content": MATH_Q}],
                   max_tokens=60, temperature=0, timeout=45)
        math_answers.append((r.get("content") or "").strip())
        r2 = c.chat(messages=[{"role": "user", "content": STYLE_Q}],
                    max_tokens=150, temperature=0, timeout=45)
        style_answers.append((r2.get("content") or "").strip())

    nums = []
    for a in math_answers:
        digits = "".join(ch for ch in a if ch.isdigit() or ch == ".")
        try:
            nums.append(round(float(digits), 2))
        except Exception:
            nums.append(None)
    valid = [n for n in nums if n is not None]
    math_consistent = len(set(valid)) <= 1 and len(valid) >= 4

    sims = []
    for i in range(len(style_answers)):
        for j in range(i + 1, len(style_answers)):
            sims.append(ngram_sim(style_answers[i], style_answers[j]))
    avg_sim = sum(sims) / len(sims) if sims else 0.0

    light = "info"
    msg = "重复回答观察：数学有效响应 %d/5，文风相似度 %.2f；没有对照，不推断混池或身份。" % (len(valid), avg_sim)

    return {
        "light": light,
        "summary_zh": msg,
        "metrics": {"math_consistent": math_consistent, "style_similarity": round(avg_sim, 3)},
        "evidence": {"math_answers": math_answers, "style_first": style_answers[0][:100] if style_answers else ""},
    }


register("determinism", "重复响应观察", "authenticity",
         "重复问题各5次，记录一致性；相似度不能证明单一或多个模型。",
         "仅作观察，不将漂移判定为混池。",45,False,run)
