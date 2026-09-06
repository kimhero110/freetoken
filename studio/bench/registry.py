"""Test registry. Each test module calls register() at import time.

meta fields:
  tid            unique id
  name_zh        display name
  dim            dimension key (authenticity/capability/performance/stability/compliance)
  desc_zh        what it measures, plain language
  thresholds_zh  judging rules shown on /criteria (objectivity)
  est_s          estimated seconds
  fast           included in quick mode
"""

TESTS = {}
ORDER = []


def register(tid, name_zh, dim, desc_zh, thresholds_zh, est_s, fast, fn):
    if tid in TESTS:
        raise ValueError("duplicate test id: " + tid)
    TESTS[tid] = {
        "tid": tid, "name_zh": name_zh, "dim": dim, "desc_zh": desc_zh,
        "thresholds_zh": thresholds_zh, "est_s": est_s, "fast": fast, "run": fn,
    }
    ORDER.append(tid)


def get(tid):
    return TESTS[tid]


def all_meta():
    return [TESTS[t] for t in ORDER]


def light_score(light):
    return {"pass": 100, "warn": 60, "fail": 10, "info": None}.get(light)
