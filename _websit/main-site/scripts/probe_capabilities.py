#!/usr/bin/env python3
"""Create single-tool, reviewable capability observations from canonical data."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

try:
    from platform_schema import validate_platform
    from probe_config import load_probe_config, probe_config_hash
    from safe_http import pinned_public_https_request
except ImportError:
    from scripts.platform_schema import validate_platform
    from scripts.probe_config import load_probe_config, probe_config_hash
    from scripts.safe_http import pinned_public_https_request


ROOT = Path(__file__).resolve().parent.parent
PLATFORMS_DIR = ROOT / "data" / "platforms"
CANDIDATES_DIR = ROOT / "data" / "candidates"
CANDIDATE_VERSION = 2
CONFIG = load_probe_config()
PROVIDER_PROBES = CONFIG["providers"]
TOOL_PROBES = CONFIG["tools"]
ALLOWED_PROVIDERS = tuple(PROVIDER_PROBES)
ALLOWED_TOOLS = tuple(TOOL_PROBES)
ALLOWED_OPERATIONS = ("chat_completions",)
JSON_CONTENT_TYPES = ("application/json", "application/problem+json")
FIXED_MESSAGE = "Reply with OK."


def _canonical_hash(platform):
    encoded = json.dumps(platform, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _load_operation(platform_slug, operation_id):
    path = PLATFORMS_DIR / f"{platform_slug}.yaml"
    platform = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    errors = validate_platform(platform, platform_slug)
    if errors:
        raise ValueError("canonical platform data is invalid")
    matches = [item for item in platform["capabilities"]["operations"] if item["id"] == operation_id]
    if len(matches) != 1:
        raise ValueError("canonical operation is missing")
    operation = matches[0]
    if operation["protocol"] != "openai" or operation_id != "chat_completions":
        raise ValueError("operation is not an allowlisted OpenAI chat capability")
    config = PROVIDER_PROBES[platform_slug]
    if (
        operation["auth"]["type"] != "bearer"
        or operation["auth"]["env_var"] != config["api_key_env"]
        or operation["endpoint_url"] != config["endpoint_url"]
        or not operation["models"]
        or operation["models"][0] != config["model"]
    ):
        raise ValueError("operation does not match the fixed probe configuration")
    return platform, operation


def _protocol_valid(payload):
    choices = payload.get("choices") if isinstance(payload, dict) else None
    return bool(
        isinstance(choices, list) and choices and isinstance(choices[0], dict)
        and isinstance(choices[0].get("message"), dict)
        and choices[0]["message"].get("role") == "assistant"
        and isinstance(choices[0]["message"].get("content"), str)
        and choices[0]["message"]["content"].strip()
    )


def _run_evidence_url():
    server = os.environ.get("GITHUB_SERVER_URL", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if server == "https://github.com" and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) and run_id.isdigit():
        return f"{server}/{repository}/actions/runs/{run_id}"
    return None


def _write_candidate(candidate):
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = candidate["checked_at"].replace("-", "").replace(":", "").replace(".", "").replace("+", "")
    destination = CANDIDATES_DIR / (
        f"probe-{candidate['platform_slug']}-{candidate['operation_id'].replace('_', '-')}-"
        f"{candidate['tool'].replace('_', '-')}-{stamp.lower()}.yaml"
    )
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=CANDIDATES_DIR, prefix=".probe-", suffix=".tmp", delete=False) as handle:
        yaml.safe_dump(candidate, handle, allow_unicode=True, sort_keys=False)
        temporary = Path(handle.name)
    try:
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _raw_http_probe(config, api_key):
    payload = json.dumps({
        "model": config["model"], "messages": [{"role": "user", "content": FIXED_MESSAGE}],
        "max_tokens": 16, "stream": False,
    }, separators=(",", ":")).encode("utf-8")
    response = pinned_public_https_request(
        config["endpoint_url"], method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        body=payload, connect_timeout=10, read_timeout=30, max_response_bytes=256 * 1024,
        allowed_content_types=JSON_CONTENT_TYPES, authenticated=True,
    )
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    valid = _protocol_valid(payload)
    return response.status, valid


def _python_sdk_probe(config, api_key):
    import httpx
    import openai

    suffix = "/chat/completions"
    if not config["endpoint_url"].endswith(suffix):
        raise ValueError("invalid OpenAI endpoint")
    status = None
    try:
        with httpx.Client(follow_redirects=False, trust_env=False) as http_client:
            client = openai.OpenAI(
                api_key=api_key, base_url=config["endpoint_url"][:-len(suffix)], timeout=30.0,
                max_retries=0, http_client=http_client,
            )
            response = client.chat.completions.create(
                model=config["model"], messages=[{"role": "user", "content": FIXED_MESSAGE}],
                max_tokens=16, stream=False,
            )
        status = 200
        payload = response.model_dump(mode="json")
        return status, _protocol_valid(payload)
    except openai.APIStatusError as error:
        status = error.status_code
        return status, False


def _node_sdk_probe(platform_slug):
    helper = ROOT / "scripts" / "node" / "probe_openai_node.mjs"
    completed = subprocess.run(
        ["node", str(helper), platform_slug], capture_output=True, text=True, timeout=40, check=False,
    )
    if completed.stderr or completed.returncode != 0 or len(completed.stdout) > 4096:
        raise RuntimeError("Node SDK probe failed")
    result = json.loads(completed.stdout)
    if set(result) != {"observed_status_code", "protocol_valid", "decision", "latency_ms"}:
        raise RuntimeError("Node SDK probe output is invalid")
    return result


def probe(platform_slug, operation_id, tool):
    platform, operation = _load_operation(platform_slug, operation_id)
    provider = PROVIDER_PROBES[platform_slug]
    tool_config = TOOL_PROBES[tool]
    checked_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    status_code = None
    protocol_valid = False
    decision = "failed"
    api_key = os.environ.get(provider["api_key_env"], "")

    if api_key:
        try:
            if tool == "raw_http":
                status_code, protocol_valid = _raw_http_probe(provider, api_key)
            elif tool == "openai_python":
                status_code, protocol_valid = _python_sdk_probe(provider, api_key)
            else:
                result = _node_sdk_probe(platform_slug)
                status_code, protocol_valid = result["observed_status_code"], result["protocol_valid"]
            decision = "live" if status_code is not None and 200 <= status_code < 300 and protocol_valid else "failed"
        except Exception:
            decision = "failed"

    candidate = {
        "candidate_type": "capability_probe", "candidate_version": CANDIDATE_VERSION,
        "platform_slug": platform_slug, "platform_hash": _canonical_hash(platform),
        "operation_id": operation_id, "tool": tool, "promotion_target": tool_config["promotion_target"],
        "client": tool_config["client"], "client_version": tool_config["client_version"],
        "probe_config_hash": probe_config_hash(platform_slug, operation, provider["model"]),
        "endpoint_url": provider["endpoint_url"],
        "endpoint_hash": hashlib.sha256(provider["endpoint_url"].encode("utf-8")).hexdigest(),
        "model": provider["model"], "observed_status_code": status_code,
        "latency_ms": min(120000, max(0, round((time.monotonic() - started) * 1000))),
        "protocol_valid": protocol_valid, "decision": decision, "checked_at": checked_at,
        "evidence_url": _run_evidence_url(),
    }
    path = _write_candidate(candidate)
    print(f"[PROBE] {platform_slug}/{operation_id}/{tool}: {decision}; candidate={path.name}")
    return decision == "live", path


def probe_all_configured(operation_id, tools):
    configured = [slug for slug in ALLOWED_PROVIDERS if os.environ.get(PROVIDER_PROBES[slug]["api_key_env"], "")]
    if not configured:
        print("[PROBE] no allowlisted provider credentials are configured", file=sys.stderr)
        return 2
    all_succeeded = True
    for provider in configured:
        for tool in tools:
            try:
                succeeded, _ = probe(provider, operation_id, tool)
            except Exception:
                print(f"[PROBE] {provider}/{operation_id}/{tool}: canonical configuration could not be loaded", file=sys.stderr)
                all_succeeded = False
            else:
                all_succeeded = succeeded and all_succeeded
    return 0 if all_succeeded else 1


def main():
    parser = argparse.ArgumentParser(description="Probe canonical API capabilities")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--provider", choices=ALLOWED_PROVIDERS)
    selection.add_argument("--all-configured", action="store_true")
    parser.add_argument("--operation", default="chat_completions", choices=ALLOWED_OPERATIONS)
    parser.add_argument("--tool", action="append", choices=ALLOWED_TOOLS)
    args = parser.parse_args()
    tools = tuple(dict.fromkeys(args.tool or ["raw_http"]))
    if args.all_configured:
        return probe_all_configured(args.operation, tools)
    try:
        outcomes = [probe(args.provider, args.operation, tool)[0] for tool in tools]
    except Exception:
        print("[PROBE] canonical configuration could not be loaded", file=sys.stderr)
        return 2
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
