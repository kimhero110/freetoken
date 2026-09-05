#!/usr/bin/env python3
import os
from pathlib import Path

try:
    from probe_config import load_probe_config
except ImportError:
    from scripts.probe_config import load_probe_config


def main():
    providers = load_probe_config()["providers"]
    configured = [slug for slug, item in providers.items() if os.environ.get(item["api_key_env"], "")]
    missing = [slug for slug in providers if slug not in configured]
    lines = [
        "## Capability probe credential coverage",
        "",
        f"Configured: **{len(configured)}/{len(providers)}**",
        f"Configured providers: {', '.join(configured) if configured else 'none'}",
        f"Skipped providers: {', '.join(missing) if missing else 'none'}",
    ]
    report = "\n".join(lines)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(report + "\n")
    print(f"[COVERAGE] configured={len(configured)}/{len(providers)}; skipped={len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
