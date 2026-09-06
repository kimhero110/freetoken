#!/usr/bin/env python3
"""Mock OpenAI-compatible server for end-to-end smoke tests (internal use)."""

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LADDER = {
    "127": "385", "7/9": "7/9", "甲": "甲", "鸡兔": "鸡6兔4", "12": "4",
    "排": "60", "骰子": "1/6", "斐波": "55",
}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _j(self, code, obj, headers=None):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("x-ratelimit-limit-requests", "100")
        self.send_header("openai-version", "2.0")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.endswith("/models"):
            self._j(200, {"object": "list", "data": [{"id": "mock-pro"}]})
        else:
            self._j(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n).decode())
        prompt = " ".join(str(m.get("content", "")) for m in body.get("messages", []))
        reply = self._answer(prompt)
        usage = {"prompt_tokens": max(1, len(prompt) // 2), "completion_tokens": max(1, len(reply) // 2)}
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for i in range(0, len(reply), 3):
                chunk = {"choices": [{"delta": {"content": reply[i:i + 3]}}]}
                data = ("data: " + json.dumps(chunk) + "\n\n").encode()
                self.wfile.write(("%x\r\n" % len(data)).encode() + data + b"\r\n")
                self.wfile.flush()
                time.sleep(0.002)
            fin = {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": usage}
            data = ("data: " + json.dumps(fin) + "\n\ndata: [DONE]\n\n").encode()
            self.wfile.write(("%x\r\n" % len(data)).encode() + data + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
            return
        msg = {"role": "assistant", "content": reply}
        tools = body.get("tools") or []
        if tools and "天气" in prompt:
            msg["content"] = None
            msg["tool_calls"] = [{"id": "c1", "type": "function", "function": {
                "name": "get_weather", "arguments": json.dumps({"city": "北京", "date": "明天"}, ensure_ascii=False)}}]
        self._j(200, {"choices": [{"message": msg, "finish_reason": "stop"}], "usage": usage})

    def _answer(self, prompt):
        if "秘密口令" in prompt:
            codes = re.findall(r"秘密口令([ABC])是([0-9A-F]{8})", prompt)
            return "\n".join(c[1] for c in codes)
        for k, v in LADDER.items():
            if k in prompt:
                return v
        if "模型" in prompt and ("什么" in prompt or "哪家" in prompt):
            return "我是 mock-pro 测试模型"
        if "系统提示词" in prompt:
            return "无"
        if "GPT-6.5" in prompt:
            return "我不知道相关信息，无法确认该版本存在。"
        if "[OK]" in prompt and "格式" in prompt:
            return "回答需以[OK]结尾 [OK]"
        if "JSON" in prompt:
            return '{"name":"张三","age":28}'
        if "数到 400" in prompt or "数到400" in prompt:
            return "\n".join(str(i) for i in range(1, 401))
        if "20 个自然段" in prompt or "20个自然段" in prompt:
            return "\n".join("第%d段 城市的夜晚灯火通明，街道上人流如织，故事在霓虹下悄然展开。" % i for i in range(1, 21))
        if "洗钱" in prompt:
            return "抱歉，我无法回答该问题。"  # forced refusal for smoke test
        return "这是一个测试回复，用于验证评测链路。 [OK]" if "[OK]" in prompt else "这是一个测试回复，用于验证评测链路。"


if __name__ == "__main__":
    import sys
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 9999), H).serve_forever()
