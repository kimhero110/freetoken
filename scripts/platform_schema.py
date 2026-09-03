import math
import re
from urllib.parse import urlparse


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STATUS_VALUES = {"active", "degraded", "expired", "unknown", "unverified"}
REQUIREMENT_VALUES = {"required", "not_required", "unknown"}
PROTOCOL_VALUES = {"openai", "anthropic", "google", "search", "rpc", "custom"}
MODEL_RE = re.compile(r"^[A-Za-z0-9@._:/+-]{1,160}$")
SAFE_URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~!&'()*+,;=:@%/?#{}-]*)?$")
QUOTA_KEYS = {"type", "amount", "unit", "reset_period", "details", "details_en", "conditions"}


def _https_url(value):
    if not isinstance(value, str) or not SAFE_URL_RE.fullmatch(value):
        return False
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and (port is None or 1 <= port <= 65535)
    )


def validate_quota(quota, prefix="free_quota"):
    errors = []
    if not isinstance(quota, dict):
        return [f"{prefix} must be an object"]
    unknown = set(quota) - QUOTA_KEYS
    if unknown:
        errors.append(f"{prefix} contains unsupported fields: {', '.join(sorted(unknown))}")
    amount = quota.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (str, int, float, type(None))):
        errors.append(f"{prefix}.amount must be text, a finite number, or null")
    elif isinstance(amount, float) and not math.isfinite(amount):
        errors.append(f"{prefix}.amount must be finite")
    elif isinstance(amount, (int, float)) and amount < 0:
        errors.append(f"{prefix}.amount must be non-negative")
    elif isinstance(amount, str) and (not amount.strip() or len(amount) > 100 or any(ord(c) < 32 for c in amount)):
        errors.append(f"{prefix}.amount contains invalid text")
    for field in ("type", "unit", "reset_period"):
        value = quota.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > 100 or any(ord(c) < 32 for c in value)):
            errors.append(f"{prefix}.{field} contains invalid text")
    for field in ("details", "details_en"):
        value = quota.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > 1000):
            errors.append(f"{prefix}.{field} contains invalid text")
    conditions = quota.get("conditions")
    if conditions is not None and (
        not isinstance(conditions, list)
        or len(conditions) > 10
        or any(not isinstance(item, str) or len(item) > 200 for item in conditions)
    ):
        errors.append(f"{prefix}.conditions must contain at most 10 short strings")
    return errors


def validate_platform(platform, expected_slug=None):
    errors = []
    if not isinstance(platform, dict):
        return ["entry must be an object"]

    slug = platform.get("slug")
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        errors.append("slug must contain only lowercase letters, numbers, and hyphens")
    if expected_slug and slug != expected_slug:
        errors.append(f"slug must match filename {expected_slug!r}")
    if not _https_url(platform.get("website")):
        errors.append("website must be an HTTPS URL")
    if platform.get("status") not in STATUS_VALUES:
        errors.append("status is invalid")
    if "doc_url" in platform and not _https_url(platform.get("doc_url")):
        errors.append("doc_url must be an HTTPS URL")
    if "api_base_url" in platform and not _https_url(platform.get("api_base_url")):
        errors.append("api_base_url must be an HTTPS URL")
    errors.extend(validate_quota(platform.get("free_quota")))

    registration = platform.get("registration")
    if not isinstance(registration, dict) or not _https_url(registration.get("url")):
        errors.append("registration.url must be an HTTPS URL")

    requirements = platform.get("requirements")
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object")
    else:
        for field in ("phone", "card", "region"):
            if requirements.get(field) not in REQUIREMENT_VALUES:
                errors.append(f"requirements.{field} is invalid")
        for field in ("rpm", "tpm"):
            value = requirements.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                errors.append(f"requirements.{field} must be null or a non-negative integer")

    capabilities = platform.get("capabilities")
    if not isinstance(capabilities, dict):
        errors.append("capabilities must be an object")
    else:
        protocol = capabilities.get("protocol")
        if protocol not in PROTOCOL_VALUES:
            errors.append("capabilities.protocol is invalid")
        chat_url = capabilities.get("chat_completions_url")
        if protocol == "openai" and not _https_url(chat_url):
            errors.append("OpenAI-compatible platforms require chat_completions_url")
        if protocol != "openai" and chat_url is not None:
            errors.append("non-OpenAI platforms cannot declare chat_completions_url")
        for field in ("supports_claude_code", "api_key_required"):
            if not isinstance(capabilities.get(field), bool):
                errors.append(f"capabilities.{field} must be boolean")
        if protocol == "openai":
            models = platform.get("free_models")
            if not isinstance(models, list) or not models or any(
                not isinstance(model, str) or not MODEL_RE.fullmatch(model) for model in models
            ):
                errors.append("OpenAI-compatible platforms require safe free_models identifiers")

    evidence = platform.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("evidence must contain at least one source")
    else:
        for index, item in enumerate(evidence):
            if not isinstance(item, dict) or not _https_url(item.get("url")):
                errors.append(f"evidence[{index}].url must be an HTTPS URL")

    return errors
