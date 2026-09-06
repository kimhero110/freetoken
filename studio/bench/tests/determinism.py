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

    if len(valid) >= 3 and not math_consistent:
        light, msg = "fail", "temperature=0 下数学答案不一致（%s）——疑似多模型混池" % " / ".join(
            ("%.2f" % n) for n in sorted(set(valid))[:4])
    elif avg_sim >= 0.7:
        light, msg = "pass", "temperature=0 下 5 轮回答高度一致（相似度 %.2f）——单一后端特征" % avg_sim
    elif avg_sim >= 0.45:
        light, msg = "warn", "数学答案一致但文风漂移（相似度 %.2f）——可能存在多后端" % avg_sim
    else:
        light, msg = "fail", "temperature=0 下文风显著漂移（相似度 %.2f）——疑似多模型混池" % avg_sim

    return {
        "light": light,
        "summary_zh": msg,
        "metrics": {"math_consistent": math_consistent, "style_similarity": round(avg_sim, 3)},
        "evidence": {"math_answers": math_answers, "style_first": style_answers[0][:100] if style_answers else ""},
    }


register("determinism", "确定性与混池检测", "authenticity",
         "temperature=0 下同一问题重复 5 轮：数学答案应完全一致、文风应高度相似；漂移大=后端混池。",
         "数学一致且文风相似度≥0.7=通过；≥0.45=可疑；明显漂移或数学不一致=未通过。",
         45, True, run)
