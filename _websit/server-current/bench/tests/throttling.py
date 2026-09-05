from ..registry import register
from ..baselines import THROTTLE_RATIO_GOOD, THROTTLE_RATIO_WARN


def run(ctx):
    c = ctx["client"]
    r = c.chat(messages=[{"role": "user", "content":
                          "从 1 数到 400，每行一个数字，只输出数字，不要跳过，不要解释。"}],
               stream=True, max_tokens=1500, temperature=0, timeout=180)
    if not r["ok"]:
        return {"light": "fail", "summary_zh": "长流式请求失败：" + r["error"][:100],
                "metrics": {}, "evidence": {"error": r["error"][:200]}}

    ct = r["chunk_times"]
    total_ms = r["elapsed_ms"]
    ttft = r.get("ttft_ms") or 0
    body_ms = max(1, total_ms - ttft)
    completion = (r["usage"] or {}).get("completion_tokens") or (len(r["content"]) // 2)

    pseudo_stream = False
    if ttft and total_ms and (ttft / total_ms > 0.9) and completion > 50:
        pseudo_stream = True

    seg1 = _rate(ct, 0, 100)
    seg2 = _rate(ct, 100, 400)
    seg3 = _rate(ct, 400, 10 ** 9)
    ratio = round(seg3 / seg1, 2) if seg1 and seg3 else None

    if pseudo_stream:
        light = "warn"
        msg = "疑似伪流式：首字时间占全程 %.0f%%，内容一次性吐出（后端缓冲假流式）" % (ttft / total_ms * 100)
    elif ratio is None:
        light, msg = "info", "生成长度不足，未测出降速曲线（completion≈%s）" % completion
    elif ratio >= THROTTLE_RATIO_GOOD:
        light, msg = "pass", "全程生成速度平稳（后段/前段速率比 %.2f）" % ratio
    elif ratio >= THROTTLE_RATIO_WARN:
        light, msg = "warn", "后段轻微降速（速率比 %.2f）" % ratio
    else:
        light, msg = "fail", "明显前快后慢（速率比 %.2f）——超出初始速度的 %.0f%%，疑似限速/降级" % (
            ratio, ratio * 100)

    return {
        "light": light,
        "summary_zh": msg,
        "metrics": {"rate_first100_tok_s": seg1, "rate_mid_tok_s": seg2, "rate_tail_tok_s": seg3,
                    "tail_over_head_ratio": ratio, "completion_tokens": completion,
                    "pseudo_stream": pseudo_stream},
        "evidence": {"ttft_ms": ttft, "total_ms": total_ms, "chunks": len(ct)},
    }


def _rate(chunk_times, from_chunk, to_chunk):
    seg = chunk_times[from_chunk:to_chunk]
    if len(seg) < 5:
        return None
    span_ms = seg[-1] - seg[0]
    if span_ms <= 0:
        return None
    return round(len(seg) / (span_ms / 1000.0), 1)


register("throttling", "限流降速曲线", "performance",
         "一次 400 数字长流式生成，分段统计 tokens/s：识别'前 200 token 快、后面偷偷降速'与伪流式缓冲。",
         "后段/前段速率比≥0.5=通过；≥0.3=可疑；更低=未通过。首字时间占全程>90% 且一次性吐出=伪流式（可疑）。",
         90, False, run)
