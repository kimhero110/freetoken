import json
import re

from ..registry import register

CASES = [
    ("输出一个用户信息 JSON：name 字段为字符串“张三”，age 字段为数字 28，只输出 JSON。",
     lambda o: o.get("name") == "张三" and o.get("age") == 28),
    ("输出一个 JSON 数组，包含 3 个水果名称字符串，只输出 JSON。",
     lambda o: isinstance(o, list) and len(o) == 3 and all(isinstance(x, str) for x in o)),
    ("输出嵌套 JSON：{\"company\": {\"name\": 字符串, \"founded\": 数字年份}}，公司名任选，年份在1900-2026，只输出 JSON。",
     lambda o: isinstance(o.get("company"), dict) and "name" in o["company"] and isinstance(o["company"].get("founded"), int)),
    ("输出 JSON：{\"active\": true, \"score\": 99.5}，只输出 JSON。",
     lambda o: o.get("active") is True and abs(float(o.get("score", 0)) - 99.5) < 0.01),
    ("输出 JSON：{\"tags\": [\"a\", \"b\", \"c\"], \"count\": 3}，只输出 JSON。",
     lambda o: isinstance(o.get("tags"), list) and len(o["tags"]) == 3 and o.get("count") == 3),
]


def _parse(text):
    t = (text or "").strip()
    t = re.sub(r"^```(json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    m = re.search(r"[\{\[]", t)
    if not m:
        return None
    end = max(t.rfind("}"), t.rfind("]"))
    if end == -1:
        return None
    try:
        return json.loads(t[m.start():end + 1])
    except Exception:
        return None


def run(ctx):
    c = ctx["client"]
    passed = 0
    details = []
    for i, (prompt, check) in enumerate(CASES):
        r = c.chat(messages=[{"role": "user", "content": prompt}],
                   max_tokens=150, temperature=0, timeout=45)
        obj = _parse(r.get("content"))
        ok = False
        if obj is not None:
            try:
                ok = bool(check(obj))
            except Exception:
                ok = False
        passed += 1 if ok else 0
        details.append({"case": i + 1, "ok": ok, "raw": (r.get("content") or "")[:80]})

    light = "pass" if passed == 5 else ("warn" if passed == 4 else "fail")
    return {
        "light": light,
        "summary_zh": "严格 JSON 输出 %d/5 达标" % passed,
        "metrics": {"passed": passed, "total": 5},
        "evidence": {"cases": details},
    }


register("jsonmode", "严格 JSON 可靠性", "capability",
         "5 组不同结构的纯 JSON 输出任务（基础/数组/嵌套/布尔浮点/混合），解析+schema 双重校验。",
         "5/5 通过；4/5 可疑；≤3 未通过。",
         35, False, run)
