from ..registry import register


def run(ctx):
    c = ctx["client"]
    r = c.chat(messages=[{"role": "user", "content": "回复：OK"}], max_tokens=10, temperature=0, timeout=45)
    h = r.get("resp_headers") or {}
    if not r["ok"]:
        return {"light": "fail", "summary_zh": "请求失败，无法分析响应头", "metrics": {},
                "evidence": {"error": r["error"][:200]}}

    interesting = {}
    for k in ("server", "x-request-id", "openai-version", "openai-processing-ms",
              "x-ratelimit-limit-requests", "x-ratelimit-remaining-requests",
              "x-ratelimit-limit-tokens", "x-ratelimit-remaining-tokens",
              "cf-ray", "x-served-by", "via", "x-powered-by"):
        if k in h:
            interesting[k] = h[k][:80]

    ratelimit_present = any(k.startswith("x-ratelimit") for k in h)
    openai_version = "openai-version" in h
    server_hdr = h.get("server", "")

    notes = []
    if ratelimit_present:
        notes.append("返回限流头（规范）")
    else:
        notes.append("缺少限流头（常见于中转/反代剥离）")
    if openai_version:
        notes.append("携带 openai-version 头")
    if server_hdr:
        notes.append("server: " + server_hdr)

    light = "info"
    if not ratelimit_present and not openai_version:
        light = "warn"
    summary = "；".join(notes) if notes else "响应头信息有限"
    return {
        "light": light,
        "summary_zh": summary + "（参考信号，不单独定罪）",
        "metrics": {"ratelimit_headers": ratelimit_present, "openai_version": openai_version,
                    "server": server_hdr},
        "evidence": {"headers": interesting},
    }


register("headers", "协议与响应头指纹", "authenticity",
         "检查响应头特征：限流头/openai版本头是否被中转剥离，server 指纹等。",
         "参考信号：缺失限流头与版本头提示可能存在反代中转，仅与其他证据合并判断。",
         8, False, run)
