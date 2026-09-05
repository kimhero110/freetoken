"""Test runner: paced sequential execution with progress callback and error containment."""

import time

from . import guard
from .client import Client, redact
from .registry import TESTS, ORDER


def run_benchmark(base_url, api_key, model, test_ids, progress=None):
    """progress(event_dict) called for start/progress/test/done. Returns run dict."""
    guard.ssrf_guard(base_url)

    valid = [t for t in test_ids if t in TESTS]
    if not valid:
        raise ValueError("no valid tests selected")
    client = Client(base_url, api_key, model)

    from . import baselines as B
    ctx = {
        "client": client,
        "model": model,
        "family": B.guess_family(model),
        "tier": B.guess_tier(model),
    }

    started = time.time()
    if progress:
        progress({"type": "start", "tests": valid, "model": model})

    results = {}
    for tid in ORDER:
        if tid not in valid:
            continue
        meta = TESTS[tid]
        if progress:
            progress({"type": "progress", "test": tid, "status": "running",
                      "name_zh": meta["name_zh"]})
        t0 = time.time()
        try:
            res = meta["run"](ctx)
            res.setdefault("light", "info")
        except Exception as e:
            res = {"light": "fail", "summary_zh": "测试执行异常：" + redact(str(e), api_key),
                   "metrics": {}, "evidence": {"error": redact(str(e), api_key)}}
        res["dim"] = meta["dim"]
        res["name_zh"] = meta["name_zh"]
        res["elapsed_s"] = round(time.time() - t0, 1)
        for k in ("metrics", "evidence"):
            res.setdefault(k, {})
        _redact_deep(res, api_key)
        results[tid] = res
        if progress:
            progress({"type": "test", "test": tid, "result": res})
        time.sleep(0.15)

    from .scoring import score_run
    composite = score_run(results)
    run = {
        "model": model,
        "host": _host_of(base_url),
        "family": ctx["family"],
        "tier": ctx["tier"],
        "baseline_version": B.BASELINE_VERSION,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_s": round(time.time() - started, 1),
        "usage": client.snapshot_usage(),
        "composite": composite,
        "tests": results,
    }
    if progress:
        progress({"type": "done", "run": _slim(run)})
    return run


def _host_of(base_url):
    from urllib.parse import urlparse
    return urlparse(base_url).hostname or base_url


def _slim(run):
    """Payload for final progress event (full run stored separately)."""
    return {
        "model": run["model"], "host": run["host"], "created": run["created"],
        "elapsed_s": run["elapsed_s"], "usage": run["usage"],
        "composite": run["composite"],
        "tests": {tid: {k: r.get(k) for k in ("name_zh", "dim", "light", "score", "summary_zh", "metrics", "elapsed_s")}
                  for tid, r in run["tests"].items()},
    }


def _redact_deep(obj, key):
    if not key or len(key) < 6:
        return
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            v = obj[k]
            if isinstance(v, str):
                obj[k] = redact(v, key)
            else:
                _redact_deep(v, key)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                obj[i] = redact(v, key)
            else:
                _redact_deep(v, key)
