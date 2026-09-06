"""Versioned public check ledger. Git fast-forward pushes are the CAS boundary.

No code is checked out from the state branch. Missing/corrupt state fails closed.
Only the workflow's existing repository credential is used.
"""
import copy
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

BRANCH = "automation-state"
MAX_BYTES = 8_000_000


class StateError(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def empty_state():
    return {"version": 1, "calls": {}, "runs": {}, "history": {}}


def validate_state(state):
    if not isinstance(state, dict) or set(state) != {"version", "calls", "runs", "history"} or state["version"] != 1:
        raise StateError("STATE_SCHEMA")
    if any(not isinstance(state[k], dict) for k in ("calls", "runs", "history")):
        raise StateError("STATE_SCHEMA")
    for key, call in state["calls"].items():
        if not re.fullmatch(r"[a-f0-9]{64}", key) or not isinstance(call, dict):
            raise StateError("STATE_SCHEMA")
        allowed = {"owner", "run", "source", "status", "created_at", "saved_at", "result", "result_hash", "resolution"}
        if set(call) - allowed or call.get("status") not in {"intent", "uncertain", "rejected_result", "result_saved", "abandoned"}:
            raise StateError("STATE_SCHEMA")
        if not {"owner", "run", "source", "created_at"} <= set(call):
            raise StateError("STATE_SCHEMA")
        if call.get("status") == "result_saved" and digest(call.get("result")) != call.get("result_hash"):
            raise StateError("RESULT_INTEGRITY")
    if len(json.dumps(state).encode()) > MAX_BYTES:
        raise StateError("STATE_CAPACITY")
    return state


class GitState:
    def __init__(self, repo, remote="origin"):
        self.repo = Path(repo)
        self.remote = remote

    def git(self, *args, data=None, env=None, check=True):
        result = subprocess.run(["git", *args], cwd=self.repo, input=data, text=True,
                                encoding="utf-8", capture_output=True, timeout=60, env=env)
        if check and result.returncode:
            # Git stderr may contain an authenticated URL. Never publish it.
            raise StateError("GIT_OPERATION_FAILED")
        return result

    def read(self, allow_missing=False):
        refs = self.git("ls-remote", "--heads", self.remote, f"refs/heads/{BRANCH}").stdout.split()
        if not refs:
            if allow_missing:
                return None, empty_state()
            raise StateError("STATE_NOT_INITIALIZED")
        head = refs[0]
        self.git("fetch", "--no-tags", self.remote, head)
        size = int(self.git("cat-file", "-s", f"{head}:state.json").stdout)
        if size > MAX_BYTES:
            raise StateError("STATE_CAPACITY")
        try:
            state = json.loads(self.git("show", f"{head}:state.json").stdout)
            return head, validate_state(state)
        except (ValueError, TypeError, KeyError) as exc:
            raise StateError("STATE_INVALID") from exc

    def commit(self, head, state):
        validate_state(state)
        payload = json.dumps(state, ensure_ascii=False, sort_keys=True, allow_nan=False)
        with tempfile.TemporaryDirectory(prefix="check-index-") as temp:
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(temp) / "index"),
                       GIT_AUTHOR_NAME="freetoken-bot[bot]", GIT_COMMITTER_NAME="freetoken-bot[bot]",
                       GIT_AUTHOR_EMAIL="freetoken-bot[bot]@users.noreply.github.com",
                       GIT_COMMITTER_EMAIL="freetoken-bot[bot]@users.noreply.github.com")
            self.git("read-tree", "--empty", env=env)
            blob = self.git("hash-object", "-w", "--stdin", data=payload).stdout.strip()
            self.git("update-index", "--add", "--cacheinfo", f"100644,{blob},state.json", env=env)
            tree = self.git("write-tree", env=env).stdout.strip()
            parents = ["-p", head] if head else []
            commit = self.git("commit-tree", tree, *parents, data="Update check ledger\n", env=env).stdout.strip()
        try:
            self.git("push", self.remote, f"{commit}:refs/heads/{BRANCH}")
        except (StateError, subprocess.TimeoutExpired):
            # Resolve lost acknowledgement, including a concurrent descendant.
            remote_head, _ = self.read(allow_missing=True)
            if not remote_head or self.git("merge-base", "--is-ancestor", commit, remote_head, check=False).returncode:
                return False
        return True

    def update(self, mutate, *, initialize=False):
        for _ in range(3):
            head, state = self.read(allow_missing=initialize)
            updated = copy.deepcopy(state)
            result = mutate(updated)
            if head and updated == state:
                return result
            if self.commit(head, updated):
                return result
        raise StateError("STATE_CONTENTION")
