import re

from ..registry import register
from .. import baselines as B
from ..matching import check, norm_num

LADDER = [
    ("127 + 258 等于多少？只输出数字。", [("num", 385)]),
    ("7/9 和 5/7 哪个更大？只输出分数。", [("frac", 7, 9), ("text", ["7/9"])]),
    ("甲比乙高，乙比丙高，谁最高？只输出名字。", [("text", ["甲"])]),
    ("鸡兔同笼，头共10个，脚共28只，鸡和兔各几只？按'鸡X兔Y'格式输出。", [("jitui", 6, 4)]),
    ("牛顿第二定律 F=ma。若 F=12N、m=3kg，加速度是多少 m/s²？只输出数字。", [("num", 4)]),
    ("5 个人排成一排，甲必须站在乙的左边（不必相邻），共有多少种排法？只输出数字。", [("num", 60)]),
    ("同时掷两枚骰子，点数之和为 7 的概率是多少？输出分数。", [("frac", 1, 6), ("text", ["1/6"])]),
    ("斐波那契数列 a1=1, a2=1, an=a(n-1)+a(n-2)，a10 是多少？只输出数字。", [("num", 55)]),
]


def run(ctx):
    c = ctx["client"]
    tier = ctx["tier"]
    passed = 0
    details = []
    for i, (q, specs) in enumerate(LADDER):
        r = c.chat(messages=[{"role": "user", "content": q}],
                   max_tokens=200, temperature=0, timeout=60)
        ans = (r.get("content") or "")
        ok = check(ans, specs) if r["ok"] else False
        passed += 1 if ok else 0
        details.append({"rung": i + 1, "ok": ok, "answer": ans[:60]})

    line = B.TIER_LADDER_LINE.get(tier, B.TIER_LADDER_LINE["mid"])
    light = "pass" if passed >= line else ("warn" if passed >= line - 1 else "fail")
    return {
        "light": light,
        "summary_zh": "8 级难度阶梯答对 %d/8（%s）" % (passed, B.TIER_LADDER_DESC.get(tier, B.TIER_LADDER_DESC["unknown"])),
        "metrics": {"passed": passed, "total": 8, "tier": tier, "tier_line": line},
        "evidence": {"ladder": details},
    }


register("downgrade", "防降级与逻辑阶梯", "capability",
         "8 级递进难度的逻辑/数学题（结果可精确校验），对照模型档位参考线，识别小模型冒充。",
         "按档位参考线：旗舰≥7、中档≥5、轻量≥3 为通过；差 1 级可疑；更多未通过。",
         60, True, run)
