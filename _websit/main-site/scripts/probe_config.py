import hashlib
import json
from pathlib import Path


CONFIG_FILE = Path(__file__).with_name("capability_probe_config.json")


def load_probe_config():
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    if set(config) != {"providers", "tools"}:
        raise ValueError("probe configuration is invalid")
    return config


def probe_contract(platform_slug, operation, model):
    return {
        "platform_slug": platform_slug,
        "operation_id": operation["id"],
        "protocol": operation["protocol"],
        "endpoint_url": operation["endpoint_url"],
        "model": model,
        "auth": operation["auth"],
    }


def probe_config_hash(platform_slug, operation, model):
    encoded = json.dumps(
        probe_contract(platform_slug, operation, model),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
