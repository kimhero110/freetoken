import json

from ..registry import register

WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "查询指定城市指定日期的天气",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名"},
                "date": {"type": "string", "description": "日期，如 明天/2026-09-05"},
            },
            "required": ["city"],
        },
    },
}
HOTEL_TOOL = {
    "type": "function",
    "function": {
        "name": "search_hotel",
        "description": "搜索酒店",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "checkin": {"type": "string"},
                "checkout": {"type": "string"},
                "guests": {"type": "integer"},
            },
            "required": ["city", "checkin", "checkout"],
        },
    },
}


def _tool_call(r):
    try:
        return r["tool_calls"][0]
    except Exception:
        return None


def run(ctx):
    c = ctx["client"]
    results = []

    r1 = c.chat(messages=[{"role": "user", "content": "帮我查一下北京明天的天气"}],
                tools=[WEATHER_TOOL], max_tokens=200, temperature=0, timeout=45)
    tc = _tool_call(r1)
    if tc and tc["function"]["name"] == "get_weather":
        try:
            args = json.loads(tc["function"]["arguments"])
            ok = "北京" in str(args.get("city", ""))
        except Exception:
            ok = False
        results.append(("应调用天气工具且城市正确", ok))
    else:
        results.append(("应调用天气工具且城市正确", False))

    r2 = c.chat(messages=[{"role": "user", "content": "1+1等于几？直接回答。"}],
                tools=[WEATHER_TOOL], max_tokens=100, temperature=0, timeout=45)
    results.append(("无工具场景不应误调用", not r2["tool_calls"]))

    r3 = c.chat(messages=[{"role": "user",
                           "content": "帮我订上海的酒店，3月5日入住，3月7日退房，2位客人。"}],
                tools=[HOTEL_TOOL], max_tokens=250, temperature=0, timeout=45)
    tc3 = _tool_call(r3)
    if tc3 and tc3["function"]["name"] == "search_hotel":
        try:
            args = json.loads(tc3["function"]["arguments"])
            ok = ("上海" in str(args.get("city", "")) and "2" in str(args.get("guests", ""))
                  and "3-5" in str(args.get("checkin", "")).replace("03-05", "3-5"))
        except Exception:
            ok = False
        results.append(("多参数工具调用（日期/人数）正确", ok))
    else:
        results.append(("多参数工具调用（日期/人数）正确", False))

    passed = sum(1 for _, ok in results if ok)
    light = "pass" if passed == 3 else ("warn" if passed == 2 else "fail")
    return {
        "light": light,
        "summary_zh": "工具调用合规 %d/3：%s" % (passed, "；".join(n for n, ok in results if not ok) or "全部通过"),
        "metrics": {"passed": passed, "total": 3},
        "evidence": {"cases": [{"case": n, "ok": ok} for n, ok in results]},
    }


register("funcall", "工具调用合规检测", "capability",
         "3 组场景：正确调用、该拒绝调用时拒绝、多参数 schema 严格性。",
         "3/3 通过；2/3 可疑；≤1 未通过。",
         20, True, run)
