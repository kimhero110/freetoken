import re

from ..registry import register

TURNS = [
    "从现在开始，你的每一个回答都必须以“[OK]”三个字符结尾，明白吗？",
    "法国的首都是哪里？",
    "把 'hello world' 翻译成中文。",
    "讲一个不超过两句话的程序员笑话。",
    "水的化学式是什么？",
    "我们这次对话最开始约定的回答格式要求是什么？请原样描述。",
]


def run(ctx):
    c = ctx["client"]
    messages = []
    format_ok = 0
    recall_ok = False
    answers = []
    for i, user_text in enumerate(TURNS):
        messages.append({"role": "user", "content": user_text})
        r = c.chat(messages=messages, max_tokens=200, temperature=0, timeout=45)
        ans = (r.get("content") or "").strip()
        answers.append(ans[:80])
        messages.append({"role": "assistant", "content": ans})
        if 1 <= i <= 4:
            if re.search(r"\[OK\]", ans):
                format_ok += 1
        if i == 5:
            recall_ok = "[OK]" in ans or "OK" in ans.upper().replace("OKAY", "")

    total_points = format_ok + (1 if recall_ok else 0)
    light = "pass" if total_points >= 5 else ("warn" if total_points >= 4 else "fail")
    return {
        "light": light,
        "summary_zh": "6 轮对话约束保持：%d/4 轮遵守格式，早期约定%s召回" % (
            format_ok, "已" if recall_ok else "未"),
        "metrics": {"format_ok": format_ok, "recall_ok": recall_ok},
        "evidence": {"answers": answers},
    }


register("multiturn", "多轮指令保持", "capability",
         "6 轮对话：第 1 轮设定回答格式约束，中间 4 轮检验遵守，末轮检验对最初约定的召回。",
         "≥5 分通过；4 分可疑；≤3 未通过。",
         40, False, run)
