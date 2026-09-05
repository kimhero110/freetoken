# -*- coding: utf-8 -*-
"""GitHub API client for the intake bot PAT (Actions-only fine-grained token).

Never grows Contents permissions: dispatch + poll + pending-deployment approval only.
Every approval is journaled by callers; codes bound to ticket-initiated runs.
"""

import time

import requests


class GhError(RuntimeError):
    def __init__(self, kind: str, message: str, status: int = 0):
        super().__init__(f"{kind}: {message}")
        self.kind = kind  # PAT_DEAD | CONTRACT | RATE | NOT_FOUND | NETWORK | OTHER
        self.status = status


class TokenBucket:
    def __init__(self, rate_per_minute: int = 10):
        self.capacity = rate_per_minute
        self.tokens = float(rate_per_minute)
        self.updated = time.monotonic()

    def wait(self) -> None:
        while True:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.capacity / 60.0)
            self.updated = now
            if self.tokens >= 1:
                self.tokens -= 1
                return
            time.sleep(max(0.05, (1 - self.tokens) * 60.0 / self.capacity))


def _kind_for_status(status: int) -> str:
    if status == 401:
        return "PAT_DEAD"
    if status == 403:
        return "RATE"
    if status == 404 or status == 422:
        return "CONTRACT"
    return "OTHER"


class GitHubClient:
    def __init__(self, token: str, repo: str, base: str = "https://api.github.com"):
        self.repo = repo
        self.base = base.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "freetoken-intake-bot",
            }
        )
        self.bucket = TokenBucket(10)

    def _request(self, method: str, path: str, payload=None, retries: int = 3):
        url = f"{self.base}{path}"
        backoff = 2.0
        for attempt in range(retries):
            self.bucket.wait()
            try:
                response = self.session.request(method, url, json=payload, timeout=20)
            except requests.RequestException as exc:
                if attempt + 1 == retries:
                    raise GhError("NETWORK", str(exc)) from exc
                time.sleep(backoff)
                backoff *= 2
                continue
            if response.status_code < 400:
                if response.status_code == 204 or not response.content:
                    return None
                return response.json()
            if response.status_code >= 500 and attempt + 1 < retries:
                time.sleep(backoff)
                backoff *= 2
                continue
            try:
                message = response.json().get("message", response.text[:200])
            except ValueError:
                message = response.text[:200]
            raise GhError(_kind_for_status(response.status_code), message, response.status_code)
        raise GhError("OTHER", "unreachable")

    # -- actions -------------------------------------------------------------
    def dispatch_workflow(self, workflow: str, ref: str = "main", inputs: dict | None = None) -> None:
        self._request("POST", f"/repos/{self.repo}/actions/workflows/{workflow}/dispatches",
                      {"ref": ref, "inputs": inputs or {}})

    def get_run(self, run_id: int) -> dict:
        return self._request("GET", f"/repos/{self.repo}/actions/runs/{run_id}")

    def list_runs(self, workflow: str | None = None, limit: int = 10) -> list:
        path = f"/repos/{self.repo}/actions/runs?per_page={limit}"
        if workflow:
            path = f"/repos/{self.repo}/actions/workflows/{workflow}/runs?per_page={limit}"
        return self._request("GET", path).get("workflow_runs", [])

    def pending_deployments(self, run_id: int) -> list:
        return self._request("GET", f"/repos/{self.repo}/actions/runs/{run_id}/pending_deployments") or []

    def approve_deployment(self, run_id: int, environment_id: int, comment: str) -> None:
        self._request(
            "POST",
            f"/repos/{self.repo}/actions/runs/{run_id}/pending_deployments",
            {"environment_ids": [environment_id], "state": "approved", "comment": comment[:200]},
        )

    def cancel_run(self, run_id: int) -> None:
        self._request("POST", f"/repos/{self.repo}/actions/runs/{run_id}/cancel")

    # -- contents (read-only is allowed for any token with repo access) ------
    def list_candidates(self) -> list:
        data = self._request("GET", f"/repos/{self.repo}/contents/data/candidates")
        return [item["name"].rsplit(".", 1)[0] for item in data if item["type"] == "file"]

    def run_url(self, run_id: int) -> str:
        return f"https://github.com/{self.repo}/actions/runs/{run_id}"
