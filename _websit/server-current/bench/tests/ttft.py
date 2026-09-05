from ..registry import register


def run(ctx):
    c = ctx["client"]
    ttfts = []
    speeds = []
    err = ""
    for i in range(3):
        r = c.chat(messages=[{"role": "user", "content": "用一句话介绍量子计算的基本原理。"}],
                   stream=True, max_tokens=200, temperature=0.3, timeout=60)
        if not r["ok"]:
            err = r["error"]
            continue
        if r["ttft_ms"] is not None:
            ttfts.append(r["ttft_ms"])
        if r["elapsed_ms"] and r["elapsed_ms"] > (r.get("ttft_ms") or 0):
            body_ms = r["elapsed_ms"] - (r["ttft_ms"] or 0)
            comp = (r["usage"] or {}).get("completion_tokens")
            if comp and comp > 10:
                denom = max(body_ms, r["elapsed_ms"]) / 1000.0
                if denom > 0:
                    speeds.append(comp / denom)
    if not ttfts:
        return {"light": "fail", "summary_zh": "无法完成流式请求：" + err[:120],
                "metrics": {}, "evidence": {"error": err[:300]}}

    ttfts_sorted = sorted(ttfts)
    p50 = ttfts_sorted[len(ttfts_sorted) // 2]
    from ..baselines import TTFT_P50_GOOD_MS, TTFT_P50_WARN_MS
    if p50 < TTFT_P50_GOOD_MS:
        light = "pass"
    elif p50 < TTFT_P50_WARN_MS:
        light = "warn"
    else:
        light = "fail"
    avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else None
    summary = "3 轮流式测试：首字中位 %dms，生成速度 %s tok/s" % (
        p50, ("%.0f" % avg_speed) if avg_speed else "未知")
    return {
        "light": light,
        "summary_zh": summary,
        "metrics": {"ttft_p50_ms": p50, "ttft_min_ms": min(ttfts), "ttft_max_ms": max(ttfts),
                    "tok_per_s": avg_speed},
        "evidence": {"rounds": ttfts},
    }


register("ttft", "首字延迟与流式健康", "performance",
         "连续 3 轮真实流式对话，测量首字输出时间(TTFT)与持续生成速度。",
         "首字中位 <1.5s 通过；<4s 可疑；否则未通过。参考：官方直连通常 0.5~2s（受网络影响）。",
         25, True, run)
