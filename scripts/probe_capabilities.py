#!/usr/bin/env python3
"""Create reviewable live capability observations from canonical platform data."""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

try:
    from platform_schema import validate_platform
    from safe_http import pinned_public_https_request
except ImportError:
    from scripts.platform_schema import validate_platform
    from scripts.safe_http import pinned_public_https_request


ROOT = Path(__file__).resolve().parent.parent
PLATFORMS_DIR = ROOT / "data" / "platforms"
CANDIDATES_DIR = ROOT / "data" / "candidates"
CANDIDATE_VERSION = 1
ALLOWED_PROVIDERS = (
    "deepseek",
    "siliconflow",
    "aliyun-bailian",
    "moonshot-kimi",
    "google-ai-studio",
    "groq",
    "volcengine",
    "zhipu-ai",
    "openrouter",
    "gmi-cloud-minimax",
)
PROVIDER_PROBES = {
    "deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com/chat/completions", "deepseek-v4-flash"),
    "siliconflow": ("SILICONFLOW_API_KEY", "https://api.siliconflow.cn/v1/chat/completions", "Qwen/Qwen2.5-7B-Instruct"),
    "aliyun-bailian": ("ALIYUN_BAILIAN_API_KEY", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", "qwen-turbo"),
    "moonshot-kimi": ("MOONSHOT_KIMI_API_KEY", "https://api.moonshot.cn/v1/chat/completions", "moonshot-v1-8k"),
    "google-ai-studio": ("GOOGLE_AI_STUDIO_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-2.5-flash"),
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile"),
    "volcengine": ("VOLCENGINE_API_KEY", "https://ark.cn-beijing.volces.com/api/v3/chat/completions", "doubao-pro-32k"),
    "zhipu-ai": ("ZHIPU_AI_API_KEY", "https://open.bigmodel.cn/api/paas/v4/chat/completions", "glm-4-flash"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions", "deepseek/deepseek-r1:free"),
    "gmi-cloud-minimax": ("GMI_CLOUD_MINIMAX_API_KEY", "https://api.gmicloud.ai/v1/chat/completions", "MiniMax-Text-01"),
}
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
    if operation["auth"]["type"] != "bearer":
        raise ValueError("operation does not use supported canonical bearer authentication")
    env_var, endpoint, model = PROVIDER_PROBES[platform_slug]
    if (
        operation["auth"]["env_var"] != env_var
        or operation["endpoint_url"] != endpoint
        or not operation["models"]
        or operation["models"][0] != model
    ):
        raise ValueError("operation does not match the fixed probe configuration")
    return platform, operation


def _protocol_valid(body):
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not (
        isinstance(choices, list)
        and choices
        and isinstance(choices[0], dict)
        and isinstance(choices[0].get("message"), dict)
    ):
        return False
    message = choices[0]["message"]
    return message.get("role") == "assistant" and isinstance(message.get("content"), str) and bool(message["content"].strip())


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
    operation_slug = candidate["operation_id"].replace("_", "-")
    destination = CANDIDATES_DIR / f"probe-{candidate['platform_slug']}-{operation_slug}-{stamp.lower()}.yaml"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=CANDIDATES_DIR, prefix=".probe-", suffix=".tmp", delete=False
    ) as handle:
        yaml.safe_dump(candidate, handle, allow_unicode=True, sort_keys=False)
        temporary = Path(handle.name)
    try:
        # A hard link publishes the completed file atomically and refuses to replace an observation.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def probe(platform_slug, operation_id):
    platform, operation = _load_operation(platform_slug, operation_id)
    env_var, endpoint, model = PROVIDER_PROBES[platform_slug]
    checked_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    status_code = None
    protocol_valid = False
    decision = "failed"

    api_key = os.environ.get(env_var, "")
    if api_key:
        payload = json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": FIXED_MESSAGE}],
                "max_tokens": 1,
                "stream": False,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            response = pinned_public_https_request(
                endpoint,
                method="POST",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                body=payload,
                connect_timeout=10,
                read_timeout=30,
                max_response_bytes=256 * 1024,
                allowed_content_types=JSON_CONTENT_TYPES,
                authenticated=True,
            )
            status_code = response.status
            protocol_valid = _protocol_valid(response.body)
            decision = "live" if 200 <= response.status < 300 and protocol_valid else "failed"
        except Exception:
            # Probe errors are deliberately opaque because provider errors may echo request data.
            decision = "failed"

    latency_ms = min(120000, max(0, round((time.monotonic() - started) * 1000)))
    candidate = {
        "candidate_type": "capability_probe",
        "candidate_version": CANDIDATE_VERSION,
        "platform_slug": platform_slug,
        "platform_hash": _canonical_hash(platform),
        "operation_id": operation_id,
        "endpoint_url": endpoint,
        "endpoint_hash": hashlib.sha256(endpoint.encode("utf-8")).hexdigest(),
        "model": model,
        "observed_status_code": status_code,
        "latency_ms": latency_ms,
        "protocol_valid": protocol_valid,
        "decision": decision,
        "checked_at": checked_at,
        "evidence_url": _run_evidence_url(),
    }
    path = _write_candidate(candidate)
    print(f"[PROBE] {platform_slug}/{operation_id}: {decision}; candidate={path.name}")
    return decision == "live", path


def probe_all_configured(operation_id):
    configured = [
        provider for provider in ALLOWED_PROVIDERS
        if os.environ.get(PROVIDER_PROBES[provider][0], "")
    ]
    if not configured:
        print("[PROBE] no allowlisted provider credentials are configured", file=sys.stderr)
        return 2

    all_succeeded = True
    for provider in configured:
        try:
            succeeded, _ = probe(provider, operation_id)
        except Exception:
            print(f"[PROBE] {provider}/{operation_id}: canonical configuration could not be loaded", file=sys.stderr)
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
    args = parser.parse_args()
    if args.all_configured:
        return probe_all_configured(args.operation)
    try:
        success, _ = probe(args.provider, args.operation)
    except Exception:
        print("[PROBE] canonical configuration could not be loaded", file=sys.stderr)
        return 2
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
