"""Evidence coverage, never a model-identity certification."""
from .registry import TESTS
VERSION = "probe-report-2"
def score_run(results):
    observations = []
    for tid, r in results.items():
        observations.append({"test": tid, "state": r.get("light", "info"), "summary": r.get("summary_zh", "")})
    return {"version": VERSION, "composite": None, "grade": "证据报告，不评真假分",
            "dims": {}, "verdict": [("conclusion", "info", "模型身份与降级结论需可信对照；未执行和失败项目不视为通过。")],
            "coverage": {"selected": len(results), "registered": len(TESTS),
                         "unmeasured": [t for t in TESTS if t not in results]},
            "observations": observations}
