from ..registry import register
from .. import baselines as B
from ..matching import check

# (问题, 语义等价判定 specs：文本同义词 / 数值 / 分数)
SPECS = [
    ([("text", ["阿根廷", "argentina"])], "2022年卡塔尔世界杯的冠军是哪支球队？"),
    ([("text", ["usb-c", "type-c", "usb type c", "usbc", "typec", "usb接口"]), ],
     "iPhone 15 系列改用了什么充电接口？"),
    ([("text", ["特朗普", "川普", "trump"])], "2024年美国总统大选的当选者是谁？"),
    ([("text", ["刘慈欣"])], "《三体》的作者是谁？"),
    ([("text", ["30万", "三十万"]), ("num", 300000, 600), ("num", 299792, 100), ("text", ["3*105", "3×105"])],
     "光在真空中的速度大约是多少公里每秒？"),
]


def run(ctx):
    c = ctx["client"]

    r_fake = c.chat(messages=[{"role": "user", "content":
                               "%s 有哪些新功能？请列举三项。" % B.KNOWLEDGE_FAKE_EVENT}],
                    max_tokens=200, temperature=0, timeout=45)
    fake_answer = (r_fake.get("content") or "").strip()
    fabricated = _claims_features(fake_answer)

    correct = 0
    details = []
    for specs, q in SPECS:
        r = c.chat(messages=[{"role": "user", "content": q + " 只用一句话回答。"}],
                   max_tokens=120, temperature=0, timeout=45)
        ok = check(r.get("content") or "", specs) if r.get("ok") else False
        correct += 1 if ok else 0
        details.append({"q": q, "ok": ok, "a": (r.get("content") or "")[:60]})

    if fabricated:
        light, msg = "fail", "对虚构事件（%s…）编造了具体功能——真实性硬伤" % B.KNOWLEDGE_FAKE_EVENT[:16]
    elif correct >= 4:
        light, msg = "pass", "常识题 %d/%d 正确，且未编造虚构事件" % (correct, len(B.KNOWLEDGE_DATED))
    elif correct >= 3:
        light, msg = "warn", "常识题 %d/%d 正确，未编造虚构事件" % (correct, len(B.KNOWLEDGE_DATED))
    else:
        light, msg = "fail", "常识题仅 %d/%d 正确——能力或真实性存疑" % (correct, len(B.KNOWLEDGE_DATED))

    return {
        "light": light,
        "summary_zh": msg,
        "metrics": {"dated_correct": correct, "dated_total": len(B.KNOWLEDGE_DATED),
                    "fabricated_fake_event": fabricated},
        "evidence": {"fake_event_answer": fake_answer[:200], "dated": details},
    }


def _claims_features(ans):
    if not ans:
        return False
    unsure = ["不知道", "无法确认", "没有", "未发布", "不了解", "虚构", "不存在", "无法核实",
              "i don't know", "not aware", "no information", "cannot confirm"]
    low = ans.lower()
    if any(k in low for k in unsure):
        return False
    enumerations = sum(1 for k in ("1.", "2.", "3.", "第一", "第二", "其一", "首先") if k in ans)
    return enumerations >= 2 or len(ans) > 120


register("knowledge", "知识与截止指纹", "authenticity",
         "5 道有确定答案的常识/时事题 + 1 个完全虚构的事件陷阱（真实模型应表示不知道）。",
         "编造虚构事件=未通过（硬伤）；常识≥4/5=通过；3/5=可疑；≤2=未通过。",
         35, False, run)
