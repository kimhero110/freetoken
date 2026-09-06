"""Rule-based scoring: test verdict -> dimension score -> composite + plain-language report."""

from . import baselines as B
from .registry import light_score


def score_run(tests_results):
    """tests_results: {tid: result dict with light, score?, summary_zh, ...}"""
    dims = {}
    for key, zh, weight in B.DIMENSIONS:
        entries = [(tid, r) for tid, r in tests_results.items() if r.get("dim") == key]
        vals = [light_score(r.get("light")) for _, r in entries]
        vals = [v for v in vals if v is not None]
        lights = [r.get("light") for _, r in entries]
        score = round(sum(vals) / len(vals)) if vals else None
        if lights and "fail" in lights:
            dlight = "fail"
        elif lights and "warn" in lights:
            dlight = "warn"
        elif lights:
            dlight = "pass"
        else:
            dlight = "info"
        dims[key] = {"name_zh": zh, "weight": weight, "score": score, "light": dlight,
                     "tests": [tid for tid, _ in entries]}

    scored = [(d["score"], d["weight"]) for d in dims.values() if d["score"] is not None]
    if scored:
        wsum = sum(w for _, w in scored)
        composite = round(sum(s * w for s, w in scored) / wsum)
    else:
        composite = 0
    grade = ("优秀" if composite >= 90 else "良好" if composite >= 75 else
             "合格" if composite >= 60 else "风险")

    verdict = _verdict_lines(tests_results, dims)
    return {"composite": composite, "grade": grade, "dims": dims, "verdict": verdict}


def _fmt_ms(ms):
    return ("%.1fs" % (ms / 1000)) if ms is not None and ms >= 1000 else ("%sms" % ms)


def _verdict_lines(tests, dims):
    lines = []

    def T(tid):
        return tests.get(tid, {})

    def first_fail(dim):
        for tid, r in tests.items():
            if r.get("dim") == dim and r.get("light") == "fail":
                return tid, r
        return None, None

    tid, r = first_fail("authenticity")
    if tid:
        lines.append(("authenticity", "fail", "真实性存疑：" + r.get("summary_zh", "存在异常信号")))
    elif dims.get("authenticity", {}).get("light") == "warn":
        lines.append(("authenticity", "warn", "真实性存在可疑信号：" + _dim_warn(tests, "authenticity")))
    else:
        lines.append(("authenticity", "pass", "通道真实性未见异常"))

    tk, idn, det = T("tokenizer"), T("identity"), T("determinism")
    cap_bad = [t.get("summary_zh") for t in (T("downgrade"), T("needle"), T("funcall")) if t.get("light") == "fail"]
    if cap_bad:
        lines.append(("capability", "fail", "能力表现明显低于预期：" + cap_bad[0]))
    elif dims.get("capability", {}).get("score") is not None and dims["capability"]["score"] < 75:
        lines.append(("capability", "warn", "能力一般，部分项目未达参考线"))
    else:
        lines.append(("capability", "pass", "能力达到该档位应有水平"))

    tt = T("ttft")
    th = T("throttling")
    if tt:
        p50 = tt.get("metrics", {}).get("ttft_p50_ms")
        if p50 is not None:
            speed = ("速度良好，首字中位 " + _fmt_ms(p50)) if tt.get("light") != "fail" else ("速度偏慢，首字中位 " + _fmt_ms(p50))
            if th and th.get("light") == "fail":
                speed += "，且存在后半程降速"
            elif th and th.get("metrics", {}).get("pseudo_stream"):
                speed += "，疑似伪流式（先缓冲后吐出）"
            lines.append(("performance", tt.get("light", "info"), speed))
    co = T("concurrency")
    if co:
        m = co.get("metrics", {})
        if co.get("light") == "fail":
            lines.append(("stability", "fail", "并发不稳：错误率 %s%%，p95 %s" % (
                m.get("err_rate_pct"), _fmt_s(m.get("p95_ms")))))
        elif co.get("light") == "warn":
            lines.append(("stability", "warn", "并发表现一般：p95 " + _fmt_s(m.get("p95_ms"))))
        else:
            lines.append(("stability", "pass", "并发稳定（%d 路并行无错误）" % (m.get("workers") or 8)))

    cp = T("compliance")
    if cp:
        rate = cp.get("metrics", {}).get("refusal_pct")
        if rate is not None:
            if cp.get("light") == "fail":
                lines.append(("compliance", "fail", "审查强度异常：%.0f%% 正常问题被拒答（疑似过度阉割）" % rate))
            elif cp.get("light") == "warn":
                lines.append(("compliance", "warn", "拒答率偏高（%.0f%%），与官方常见表现有差异" % rate))
            else:
                lines.append(("compliance", "pass", "审查强度与官方常见表现相当"))

    composite_fail = dims.get("authenticity", {}).get("light") == "fail"
    if composite_fail:
        lines.append(("conclusion", "fail", "综合结论：不建议用于重要业务——存在真实性硬伤"))
    elif dims.get("authenticity", {}).get("light") == "warn":
        lines.append(("conclusion", "warn", "综合结论：谨慎使用，建议复查真实性告警项"))
    else:
        lines.append(("conclusion", "pass", "综合结论：可用于日常业务，详见分项"))
    return lines


def _dim_warn(tests, dim):
    for tid, r in tests.items():
        if r.get("dim") == dim and r.get("light") == "warn":
            return r.get("summary_zh", "")
    return ""


def _fmt_s(ms):
    if ms is None:
        return "-"
    return "%.1fs" % (ms / 1000)
