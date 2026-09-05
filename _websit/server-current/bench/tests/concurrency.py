import threading

from ..registry import register
from ..baselines import CONCURRENCY_WORKERS, CONCURRENCY_P95_GOOD_S, CONCURRENCY_P95_WARN_S, CONCURRENCY_ERR_WARN, CONCURRENCY_ERR_FAIL


def _one(client, results, idx):
    r = client.chat(messages=[{"role": "user", "content": "只回复数字 1，不要其他内容。"}],
                    max_tokens=5, temperature=0, timeout=90)
    results[idx] = r


def _pct(sorted_vals, p):
    if not sorted_vals:
        return None
    k = max(0, min(len(sorted_vals) - 1, int(round(p / 100.0 * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def run(ctx):
    c = ctx["client"]
    n = CONCURRENCY_WORKERS
    results = [None] * n
    threads = [threading.Thread(target=_one, args=(c, results, i)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)

    ok = [r for r in results if r and r.get("ok")]
    failed = n - len(ok)
    err_rate = failed / n
    lat = sorted([r["elapsed_ms"] for r in ok]) if ok else []
    p50 = _pct(lat, 50)
    p95 = _pct(lat, 95)

    if err_rate >= CONCURRENCY_ERR_FAIL or not lat or (p95 and p95 > CONCURRENCY_P95_WARN_S * 1000):
        light = "fail"
    elif err_rate >= CONCURRENCY_ERR_WARN or (p95 and p95 > CONCURRENCY_P95_GOOD_S * 1000):
        light = "warn"
    else:
        light = "pass"

    metrics = {"workers": n, "ok": len(ok), "failed": failed,
               "err_rate_pct": round(err_rate * 100, 1),
               "p50_ms": p50, "p95_ms": p95}
    if not lat:
        return {"light": "fail", "summary_zh": "%d 路并发全部失败" % n, "metrics": metrics,
                "evidence": {"first_error": (results and results[0] or {}).get("error", "")[:150]}}
    return {
        "light": light,
        "summary_zh": "%d 路并发：成功 %d，p50 %.1fs / p95 %.1fs" % (n, len(ok), p50 / 1000, p95 / 1000),
        "metrics": metrics,
        "evidence": {},
    }


register("concurrency", "并发压力测试", "stability",
         "8 路并行小请求，测 p50/p95 延迟与错误率，反映高峰期排队与后端池容量。",
         "错误率≥20% 或 p95>15s=未通过；错误率≥10% 或 p95>8s=可疑；否则通过。",
         45, False, run)
