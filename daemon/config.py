# -*- coding: utf-8 -*-
"""Environment-driven configuration. No defaults for secrets: fail loudly."""

import os
from pathlib import Path

REQUIRED = (
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "OWNER_OPEN_ID",
    "GITHUB_PAT",
    "GITHUB_REPO",
)


class ConfigError(RuntimeError):
    pass


def load_config(env=None) -> dict:
    env = dict(os.environ if env is None else env)
    missing = [key for key in REQUIRED if not env.get(key, "").strip()]
    if missing:
        raise ConfigError("missing required env: " + ", ".join(missing))
    return {
        "app_id": env["FEISHU_APP_ID"].strip(),
        "app_secret": env["FEISHU_APP_SECRET"].strip(),
        "owner_open_id": env["OWNER_OPEN_ID"].strip(),
        "github_pat": env["GITHUB_PAT"].strip(),
        "github_repo": env["GITHUB_REPO"].strip(),
        "bootstrap": env.get("BOOTSTRAP", "").strip() == "1",
        "journal_path": Path(env.get("JOURNAL_PATH", "/data/journal.jsonl")),
        "watchdog_minutes": int(env.get("WATCHDOG_MINUTES", "30") or 30),
        "confirm_ttl_seconds": int(env.get("CONFIRM_TTL_SECONDS", "300") or 300),
        "confirm_max_attempts": int(env.get("CONFIRM_MAX_ATTEMPTS", "3") or 3),
        "lock_ttl_seconds": int(env.get("LOCK_TTL_SECONDS", "1800") or 1800),
        "candidate_fresh_hours": int(env.get("CANDIDATE_FRESH_HOURS", "48") or 48),
        "check_monitor_enabled": env.get("CHECK_MONITOR_ENABLED") == "true",
        "check_monitor_since": env.get("CHECK_MONITOR_SINCE", ""),
        "check_alert_db": Path(env.get("CHECK_ALERT_DB", "/data/check-alerts.sqlite3")),
        "check_status_path": Path(env.get("CHECK_STATUS_PATH", "/data/check-public/status.json")),
        "commit_sha": env.get("GIT_COMMIT", "dev").strip() or "dev",
    }
