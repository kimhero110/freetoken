import math
import re
from datetime import date
from urllib.parse import urlparse


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STATUS_VALUES = {"active", "degraded", "expired", "unknown", "unverified"}
REQUIREMENT_VALUES = {"required", "not_required", "unknown"}
OPERATION_IDS = {"chat_completions", "search", "text_extraction", "image_generation", "agent", "rpc"}
PROTOCOL_VALUES = {"openai", "anthropic", "google", "rest", "rpc", "custom"}
AUTH_TYPES = {"bearer", "api_key_header", "query", "none", "unknown"}
VERIFICATION_VALUES = {"claimed", "documented", "live", "failed", "unknown"}
TOOL_VALUES = VERIFICATION_VALUES | {"unsupported"}
TOOL_KEYS = {"curl", "openai_python", "openai_node", "cursor", "openclaw", "cherry_studio"}
CAPABILITY_KEYS = {"operations", "tools"}
OPERATION_KEYS = {"id", "protocol", "endpoint_url", "models", "auth", "verification"}
AUTH_KEYS = {"type", "header", "query_param", "env_var"}
VERIFICATION_KEYS = {"status", "checked_at", "evidence_url"}
MODEL_RE = re.compile(r"^[A-Za-z0-9@._:/+-]{1,160}$")
ENV_VAR_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
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


def _unknown_fields(value, allowed, prefix):
    unknown = set(value) - allowed
    return [f"{prefix} contains unsupported fields: {', '.join(sorted(unknown))}"] if unknown else []


def _missing_fields(value, required, prefix):
    missing = required - set(value)
    return [f"{prefix} is missing fields: {', '.join(sorted(missing))}"] if missing else []


def _validate_auth(auth, prefix):
    if not isinstance(auth, dict):
        return [f"{prefix} must be an object"]
    errors = _unknown_fields(auth, AUTH_KEYS, prefix)
    errors.extend(_missing_fields(auth, AUTH_KEYS, prefix))
    auth_type = auth.get("type")
    header = auth.get("header")
    query_param = auth.get("query_param")
    env_var = auth.get("env_var")
    if auth_type not in AUTH_TYPES:
        errors.append(f"{prefix}.type is invalid")
    for field, value in (("header", header), ("query_param", query_param)):
        if value is not None and (not isinstance(value, str) or not value or len(value) > 100 or any(ord(c) < 33 for c in value)):
            errors.append(f"{prefix}.{field} must be a safe string or null")
    env_var_valid = isinstance(env_var, str) and bool(ENV_VAR_RE.fullmatch(env_var))
    if env_var is not None and not env_var_valid:
        errors.append(f"{prefix}.env_var must be an uppercase safe identifier or null")

    if auth_type == "bearer" and (header != "Authorization" or not env_var_valid or query_param is not None):
        errors.append(f"{prefix} bearer auth requires Authorization header, env_var, and null query_param")
    elif auth_type == "api_key_header" and (not header or not env_var_valid or query_param is not None):
        errors.append(f"{prefix} api_key_header auth requires header, env_var, and null query_param")
    elif auth_type == "query" and (header is not None or not query_param or not env_var_valid):
        errors.append(f"{prefix} query auth requires query_param, env_var, and null header")
    elif auth_type in {"none", "unknown"} and any(value is not None for value in (header, query_param, env_var)):
        errors.append(f"{prefix} {auth_type} auth requires header, query_param, and env_var to be null")
    return errors


def _validate_verification(verification, prefix):
    if not isinstance(verification, dict):
        return [f"{prefix} must be an object"]
    errors = _unknown_fields(verification, VERIFICATION_KEYS, prefix)
    errors.extend(_missing_fields(verification, VERIFICATION_KEYS, prefix))
    if verification.get("status") not in VERIFICATION_VALUES:
        errors.append(f"{prefix}.status is invalid")
    checked_at = verification.get("checked_at")
    if checked_at is not None:
        if not isinstance(checked_at, str) or not DATE_RE.fullmatch(checked_at):
            errors.append(f"{prefix}.checked_at must be YYYY-MM-DD or null")
        else:
            try:
                date.fromisoformat(checked_at)
            except ValueError:
                errors.append(f"{prefix}.checked_at must be a valid date")
    evidence_url = verification.get("evidence_url")
    if evidence_url is not None and not _https_url(evidence_url):
        errors.append(f"{prefix}.evidence_url must be an HTTPS URL or null")
    status = verification.get("status")
    if status in {"documented", "live"} and (checked_at is None or evidence_url is None):
        errors.append(f"{prefix} documented/live status requires checked_at and evidence_url")
    elif status in {"claimed", "unknown"} and (checked_at is not None or evidence_url is not None):
        errors.append(f"{prefix} claimed/unknown status requires null checked_at and evidence_url")
    elif status == "failed" and checked_at is None:
        errors.append(f"{prefix} failed status requires checked_at")
    return errors


def _validate_capabilities(capabilities):
    if not isinstance(capabilities, dict):
        return ["capabilities must be an object"]
    errors = _unknown_fields(capabilities, CAPABILITY_KEYS, "capabilities")
    errors.extend(_missing_fields(capabilities, CAPABILITY_KEYS, "capabilities"))
    operations = capabilities.get("operations")
    if not isinstance(operations, list):
        errors.append("capabilities.operations must be a list")
    else:
        operation_ids = set()
        for index, operation in enumerate(operations):
            prefix = f"capabilities.operations[{index}]"
            if not isinstance(operation, dict):
                errors.append(f"{prefix} must be an object")
                continue
            errors.extend(_unknown_fields(operation, OPERATION_KEYS, prefix))
            errors.extend(_missing_fields(operation, OPERATION_KEYS, prefix))
            operation_id = operation.get("id")
            if operation_id not in OPERATION_IDS:
                errors.append(f"{prefix}.id is invalid")
            elif operation_id in operation_ids:
                errors.append(f"{prefix}.id is duplicated")
            operation_ids.add(operation_id)
            protocol = operation.get("protocol")
            if protocol not in PROTOCOL_VALUES:
                errors.append(f"{prefix}.protocol is invalid")
            endpoint_url = operation.get("endpoint_url")
            if endpoint_url is not None and not _https_url(endpoint_url):
                errors.append(f"{prefix}.endpoint_url must be an HTTPS URL or null")
            models = operation.get("models")
            if not isinstance(models, list) or any(
                not isinstance(model, str) or not MODEL_RE.fullmatch(model) for model in models
            ):
                errors.append(f"{prefix}.models must be a list of safe identifiers")
            if operation_id == "chat_completions":
                if not _https_url(endpoint_url):
                    errors.append(f"{prefix} chat_completions requires endpoint_url")
                if not isinstance(models, list) or not models:
                    errors.append(f"{prefix} chat_completions requires models")
                if protocol == "openai" and (not isinstance(endpoint_url, str) or not endpoint_url.endswith("/chat/completions")):
                    errors.append(f"{prefix} OpenAI endpoint must end with /chat/completions")
            errors.extend(_validate_auth(operation.get("auth"), f"{prefix}.auth"))
            errors.extend(_validate_verification(operation.get("verification"), f"{prefix}.verification"))

    tools = capabilities.get("tools")
    if not isinstance(tools, dict):
        errors.append("capabilities.tools must be an object")
    else:
        errors.extend(_unknown_fields(tools, TOOL_KEYS, "capabilities.tools"))
        errors.extend(_missing_fields(tools, TOOL_KEYS, "capabilities.tools"))
        for tool, status in tools.items():
            if tool in TOOL_KEYS and status not in TOOL_VALUES:
                errors.append(f"capabilities.tools.{tool} is invalid")
    return errors


def validate_platform(platform, expected_slug=None):
    errors = []
    if not isinstance(platform, dict):
        return ["entry must be an object"]

    if platform.get("schema_version") != 2 or isinstance(platform.get("schema_version"), bool):
        errors.append("schema_version must be 2")
    for field in ("slug", "name", "category", "intro", "website", "free_quota", "status", "registration", "requirements", "capabilities", "evidence"):
        if field not in platform:
            errors.append(f"{field} is required")
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

    errors.extend(_validate_capabilities(platform.get("capabilities")))

    evidence = platform.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("evidence must contain at least one source")
    else:
        for index, item in enumerate(evidence):
            if not isinstance(item, dict) or not _https_url(item.get("url")):
                errors.append(f"evidence[{index}].url must be an HTTPS URL")

    return errors
