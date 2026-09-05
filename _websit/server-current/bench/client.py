"""OpenAI-compatible API client used by all benchmark tests."""

import json
import time
import urllib.request
import urllib.error


class ApiError(Exception):
    pass


class Client:
    def __init__(self, base_url, api_key, model=""):
        self.base = base_url.rstrip("/")
        if not self.base.endswith("/v1"):
            self.base = self.base + "/v1"
        self.key = api_key
        self.model = model
        self.requests = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self._extra_headers = {}

    def _headers(self):
        h = {
            "Authorization": "Bearer " + self.key,
            "Content-Type": "application/json",
            "User-Agent": "WitKit-Studio-Bench/2.0",
        }
        h.update(self._extra_headers)
        return h

    def snapshot_usage(self):
        return {
            "requests": self.requests,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }

    def models(self, timeout=20):
        url = self.base + "/models"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        self.requests += 1
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8")), dict(resp.headers)
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {"error": str(e)}
            return e.code, body, dict(e.headers or {})
        except Exception as e:
            return 0, {"error": str(e)}, {}

    def chat(self, model=None, messages=None, stream=False, max_tokens=512,
             temperature=None, tools=None, tool_choice=None, response_format=None,
             timeout=60, extra_headers=None):
        """Returns a result dict. Never raises; check r['ok']."""
        model = model or self.model
        payload = {"model": model, "messages": messages, "stream": bool(stream)}
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if response_format is not None:
            payload["response_format"] = response_format
        data = json.dumps(payload).encode("utf-8")
        headers = self._headers()
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(self.base + "/chat/completions", data=data,
                                     headers=headers, method="POST")
        self.requests += 1
        r = {
            "ok": False, "status": 0, "error": "", "elapsed_ms": 0, "ttft_ms": None,
            "content": "", "tool_calls": [], "usage": None, "finish_reason": None,
            "chunk_times": [], "resp_headers": {},
        }
        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                r["resp_headers"] = {k.lower(): v for k, v in resp.headers.items()}
                if stream:
                    content_parts = []
                    first = True
                    t0 = time.time()
                    for raw_line in resp:
                        line = raw_line.decode("utf-8", "replace").strip()
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            obj = json.loads(data_str)
                        except Exception:
                            continue
                        now = time.time()
                        delta = ""
                        try:
                            ch = obj["choices"][0]
                            delta = (ch.get("delta") or {}).get("content") or ""
                            if ch.get("finish_reason"):
                                r["finish_reason"] = ch["finish_reason"]
                        except Exception:
                            ch = None
                        if obj.get("usage"):
                            r["usage"] = obj["usage"]
                        if delta:
                            if first:
                                r["ttft_ms"] = int((now - t0) * 1000)
                                first = False
                            content_parts.append(delta)
                            r["chunk_times"].append(round((now - t0) * 1000, 1))
                    r["content"] = "".join(content_parts)
                    r["elapsed_ms"] = int((time.time() - start) * 1000)
                    r["status"] = resp.status
                    r["ok"] = True
                else:
                    body = json.loads(resp.read().decode("utf-8"))
                    r["status"] = resp.status
                    r["elapsed_ms"] = int((time.time() - start) * 1000)
                    r["usage"] = body.get("usage")
                    try:
                        msg = body["choices"][0]["message"]
                        r["content"] = msg.get("content") or ""
                        r["tool_calls"] = msg.get("tool_calls") or []
                        r["finish_reason"] = body["choices"][0].get("finish_reason")
                    except Exception:
                        pass
                    r["ok"] = True
        except urllib.error.HTTPError as e:
            r["status"] = e.code
            r["elapsed_ms"] = int((time.time() - start) * 1000)
            try:
                r["error"] = json.dumps(json.loads(e.read().decode("utf-8")))[:500]
            except Exception:
                r["error"] = str(e)[:300]
        except Exception as e:
            r["elapsed_ms"] = int((time.time() - start) * 1000)
            r["error"] = str(e)[:300]
        if r["usage"]:
            self.prompt_tokens += r["usage"].get("prompt_tokens") or 0
            self.completion_tokens += r["usage"].get("completion_tokens") or 0
        return r


def ngram_sim(a: str, b: str, n=3) -> float:
    """Character n-gram Jaccard similarity, 0..1."""
    def grams(s):
        s = "".join(s.split())
        return set(s[i:i + n] for i in range(max(0, len(s) - n + 1)))
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 1.0 if not ga and not gb else 0.0
    return len(ga & gb) / len(ga | gb)


def redact(text: str, secret: str) -> str:
    if secret and len(secret) >= 6:
        text = text.replace(secret, "***REDACTED***")
    return text
