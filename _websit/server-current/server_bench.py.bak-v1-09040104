#!/usr/bin/env python3
"""WitKit Studio Bench v2 — LLM Quality & Security Benchmark Arena.

Zero-dependency (Python 3 stdlib only) web service.
Routes:
  GET  /                 main console
  GET  /criteria         judging criteria & methodology
  GET  /report/{id}      shareable report page
  GET  /api/meta         test registry metadata
  GET  /api/history      recent runs
  POST /api/models       passthrough GET {base}/models (SSRF-guarded)
  POST /api/benchmark    run tests, NDJSON streaming progress
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from bench import store, ui, pages
from bench.guard import ssrf_guard
from bench.client import Client, redact
from bench.registry import all_meta
from bench import baselines as B
from bench.tests import *  # noqa: F401,F403  (registers all tests)
from bench import runner

HOST = os.environ.get("BENCH_HOST", "100.64.0.17")
PORT = int(os.environ.get("BENCH_PORT", "8500"))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj, extra=None):
        self._send(code, json.dumps(obj, ensure_ascii=False), extra=extra)

    def _read_json(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > 1024 * 64:
                return None
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return None

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/index.html"):
            self._send(200, ui.PAGE, ctype="text/html; charset=utf-8")
        elif p == "/criteria":
            self._send(200, pages.criteria_page(), ctype="text/html; charset=utf-8")
        elif p.startswith("/report/"):
            rid = p.split("/report/")[1].strip("/")
            run = store.get_run(rid) if rid else None
            if run:
                self._send(200, pages.report_page(run), ctype="text/html; charset=utf-8")
            else:
                self._send(404, "<h1>404 报告不存在</h1>", ctype="text/html; charset=utf-8")
        elif p == "/api/meta":
            tests = [{k: m[k] for k in ("tid", "name_zh", "dim", "desc_zh", "thresholds_zh", "est_s", "fast")}
                     for m in all_meta()]
            self._json(200, {"tests": tests,
                             "dims": [{"key": k, "name_zh": zh, "weight": w} for k, zh, w in B.DIMENSIONS],
                             "baseline_version": B.BASELINE_VERSION})
        elif p == "/api/history":
            self._json(200, store.history(30))
        elif p == "/healthz":
            self._json(200, {"ok": True, "version": "2.0"})
        else:
            self._send(404, '{"error":"not found"}')

    def do_POST(self):
        p = urlparse(self.path).path
        data = self._read_json()
        if data is None:
            self._json(400, {"success": False, "error": "invalid JSON body"})
            return

        if p == "/api/models":
            base_url = (data.get("base_url") or "").strip()
            api_key = (data.get("api_key") or "").strip()
            if not base_url or not api_key:
                self._json(400, {"success": False, "error": "Missing base_url or api_key"})
                return
            try:
                ssrf_guard(base_url)
            except ValueError as e:
                self._json(400, {"success": False, "error": str(e)})
                return
            client = Client(base_url, api_key)
            status, body, _ = client.models()
            if status == 200 and isinstance(body, dict):
                models = sorted(str(m.get("id")) for m in body.get("data", []) if isinstance(m, dict))
                self._json(200, {"success": True, "models": models})
            else:
                msg = json.dumps(body, ensure_ascii=False)[:200] if body else ("HTTP " + str(status))
                self._json(200, {"success": False, "error": redact(msg, api_key)})
            return

        if p == "/api/benchmark":
            base_url = (data.get("base_url") or "").strip()
            api_key = (data.get("api_key") or "").strip()
            model = (data.get("model") or "").strip()
            test_ids = data.get("tests") or []
            if not base_url or not api_key or not model:
                self._json(400, {"success": False, "error": "Missing base_url/api_key/model"})
                return
            try:
                ssrf_guard(base_url)
            except ValueError as e:
                self._json(400, {"success": False, "error": str(e)})
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            def progress(ev):
                line = json.dumps(ev, ensure_ascii=False) + "\n"
                payload = line.encode("utf-8")
                self.wfile.write(("%x\r\n" % len(payload)).encode() + payload + b"\r\n")
                self.wfile.flush()

            try:
                run = runner.run_benchmark(base_url, api_key, model, test_ids, progress)
                rid = store.save_run(run)
                slim = runner._slim(run)
                slim["report_id"] = rid
                progress({"type": "done", "run": slim})
            except ValueError as e:
                progress({"type": "error", "error": str(e)})
            except Exception as e:
                progress({"type": "error", "error": "internal error: " + str(e)[:200]})
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            return

        self._send(404, '{"error":"not found"}')


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("WitKit Bench v2 listening on %s:%d" % (HOST, PORT), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
