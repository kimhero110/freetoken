# -*- coding: utf-8 -*-
"""Unit tests for bench.matching (deterministic semantic matching)."""
import sys
sys.path.insert(0, '/opt/witkit-bench')
from bench.matching import check, norm_num, norm_text, has_standalone_number, match_fraction, match_jitui

CASES = [
    # (描述, 答案文本, specs, 期望)
    ("世界杯-标准", "冠军是阿根廷。", [("text", ["阿根廷", "argentina"])], True),
    ("世界杯-球队后缀", "阿根廷队通过点球大战夺冠。", [("text", ["阿根廷", "argentina"])], True),
    ("世界杯-英文", "Argentina won the cup.", [("text", ["阿根廷", "argentina"])], True),
    ("接口-USB-C", "改用了 USB-C 接口。", [("text", ["usb-c", "type-c", "usbc", "typec"])], True),
    ("接口-Type-C", "是 Type-C。", [("text", ["usb-c", "type-c", "usbc", "typec"])], True),
    ("接口-USB Type C", "USB Type C 充电口。", [("text", ["usb-c", "type-c", "usb type c", "usbc", "typec"])], True),
    ("接口-错误答案", "改用了 Lightning 接口。", [("text", ["usb-c", "type-c", "usbc", "typec"])], False),
    ("总统-川普", "当选的是川普。", [("text", ["特朗普", "川普", "trump"])], True),
    ("总统-Trump", "Donald Trump won.", [("text", ["特朗普", "川普", "trump"])], True),
    ("光速-30万", "大约每秒30万公里。", [("text", ["30万", "三十万"]), ("num", 300000, 600)], True),
    ("光速-三十万", "约为三十万公里每秒。", [("text", ["30万", "三十万"]), ("num", 300000, 600)], True),
    ("光速-精确值", "299792 公里/秒。", [("text", ["30万", "三十万"]), ("num", 300000, 600), ("num", 299792, 100)], True),
    ("光速-错误", "大约 15 万公里每秒。", [("text", ["30万", "三十万"]), ("num", 300000, 600)], False),
    ("分数-7/9标准", "7/9 更大。", [("frac", 7, 9)], True),
    ("分数-小数", "0.78 更大一些。", [("frac", 7, 9)], True),
    ("分数-中文", "七分之九更大。", [("frac", 7, 9)], True),
    ("分数-错误小数", "0.5 更大。", [("frac", 7, 9)], False),
    ("概率-分数", "概率是 1/6。", [("frac", 1, 6), ("text", ["1/6"])], True),
    ("概率-百分比", "概率约 16.7%。", [("frac", 1, 6), ("text", ["1/6"])], True),
    ("概率-小数", "约等于 0.167。", [("frac", 1, 6), ("text", ["1/6"])], True),
    ("概率-中文分数", "六分之一。", [("frac", 1, 6), ("text", ["1/6"])], True),
    ("数字-385", "127+258=385", [("num", 385)], True),
    ("数字-160不误判60", "共有 160 种排法。", [("num", 60)], False),
    ("数字-60正确", "共有 60 种排法。", [("num", 60)], True),
    ("数字-4不误判14", "是 14 m/s²。", [("num", 4)], False),
    ("数字-4.0等值", "是 4.0 m/s²。", [("num", 4)], True),
    ("数字-55", "a10 = 55", [("num", 55)], True),
    ("鸡兔-标准", "鸡6兔4", [("jitui", 6, 4)], True),
    ("鸡兔-带单位", "鸡：6只，兔：4只。", [("jitui", 6, 4)], True),
    ("鸡兔-数量在前", "有6只鸡和4只兔。", [("jitui", 6, 4)], True),
    ("鸡兔-鸡在前文", "鸡有 6 只，兔则有 4 只。", [("jitui", 6, 4)], True),
    ("鸡兔-错误", "鸡4兔6。", [("jitui", 6, 4)], False),
    ("鸡兔-错误2", "鸡5兔5。", [("jitui", 6, 4)], False),
]

failed = 0
for desc, text, specs, expect in CASES:
    got = check(text, specs)
    mark = "PASS" if got == expect else "FAIL"
    if got != expect:
        failed += 1
    print("%s  %-20s -> %s" % (mark, desc, got))

print()
if failed:
    print("FAILED: %d/%d" % (failed, len(CASES)))
    sys.exit(1)
print("ALL %d CASES PASSED" % len(CASES))
