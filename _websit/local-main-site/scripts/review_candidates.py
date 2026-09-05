# -*- coding: utf-8 -*-
"""
FreeToken Candidate Platform Review & Decision Terminal
---------------------------------------------------------
- Review pending radar discoveries in data/candidates/
- One-click approve -> move to data/platforms -> recompile -> build
- Approval pushes to main; CI then triggers the verified production publish
  workflow, which announces the release after dual-node verification
- Rejections archive the candidate and record the reviewed source version
"""

import sys
import os
import argparse
import hashlib
import json
import re
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
import yaml
import subprocess
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_DIR = ROOT / "data" / "candidates"
PLATFORMS_DIR = ROOT / "data" / "platforms"
CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
PLATFORMS_DIR.mkdir(parents=True, exist_ok=True)
HASHES_FILE = ROOT / ".cache" / "hashes.json"
REVIEWS_DIR = ROOT / "data" / "reviews"
LOCK_FILE = ROOT / ".cache" / "candidate-review.lock"
GENERATED_FILES = (
    ROOT / "data" / "platforms.json",
    ROOT / "site" / "src" / "data" / "platforms.json",
    ROOT / "site" / "public" / "sitemap.xml",
)
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CAPABILITY_PROBE_KEYS = {
    "candidate_type", "candidate_version", "platform_slug", "platform_hash", "operation_id",
    "tool", "promotion_target", "client", "client_version", "probe_config_hash",
    "endpoint_url", "endpoint_hash", "model", "observed_status_code", "latency_ms",
    "protocol_valid", "decision", "checked_at", "evidence_url", "review",
}

sys.path.append(str(ROOT / "scripts"))
try:
    from platform_schema import validate_platform, validate_quota
    from probe_config import load_probe_config, probe_config_hash
    from safe_http import get_public_text
except ImportError:
    from scripts.platform_schema import validate_platform, validate_quota
    from scripts.probe_config import load_probe_config, probe_config_hash
    from scripts.safe_http import get_public_text


@contextmanager
def _approval_lock():
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+b") as lock:
        lock.seek(0)
        if lock.read(1) == b"":
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _source_hash(url: str) -> str:
    user_agent = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 FreeTokenBot/1.0"
    )
    body = get_public_text(url, headers={"User-Agent": user_agent}, timeout=20)
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _platform_hash(platform: dict) -> str:
    canonical = json.dumps(platform, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _archive_candidate(target_file: Path, decision: str) -> None:
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    destination = REVIEWS_DIR / f"{target_file.stem}-{decision}.yaml"
    if destination.exists():
        raise ValueError(f"审核记录已存在: {destination.name}")
    target_file.replace(destination)


def _mark_candidate_reviewed(target_file: Path, data: dict, decision: str) -> None:
    review = {
        "decision": decision,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": os.environ.get("GITHUB_ACTOR") or os.environ.get("USER") or os.environ.get("USERNAME") or "local-user",
    }
    # feishu 注解只是标注：权威身份永远是 github.actor（不可经 dispatch 输入伪造）
    approver_via = os.environ.get("FEISHU_APPROVER_VIA", "").strip()
    approver_id = os.environ.get("FEISHU_APPROVER_ID", "").strip()
    if approver_via and re.fullmatch(r"[\w-]{1,32}", approver_via):
        review["annotation_via"] = approver_via
        if approver_id and re.fullmatch(r"[\w-]{1,64}", approver_id):
            review["annotation_id"] = approver_id
    data["review"] = review
    temporary = target_file.with_suffix(target_file.suffix + ".tmp")
    temporary.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    temporary.replace(target_file)


def list_candidates():
    candidates = list(CANDIDATES_DIR.glob("*.yaml")) + list(CANDIDATES_DIR.glob("*.json"))
    if not candidates:
        print("[INFO] 目前没有待审候选源 (No pending candidates in data/candidates/).")
        return []

    print("\n" + "=" * 60)
    print(f"📋 【待审候选新源列表】 共 {len(candidates)} 个待决策平台")
    print("=" * 60)
    data_list = []
    for f in candidates:
        try:
            if f.suffix == ".yaml":
                d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            else:
                import json
                d = json.loads(f.read_text(encoding="utf-8"))
            proposed = d.get("proposed") if isinstance(d.get("proposed"), dict) else {}
            slug = d.get("platform_slug") or proposed.get("slug") or f.stem
            name = d.get("name") or proposed.get("name") or slug
            url = d.get("source_url") or proposed.get("website") or ""
            score = d.get("score", "-")
            print(f"  • [{slug:<15}] {name:<20} | 得分: {score} | 官网: {url}")
            data_list.append((f, d))
        except Exception as e:
            print(f"  • [ERROR] 无法读取 {f.name}: {e}")
    print("=" * 60 + "\n")
    return data_list


def _safe_slug(value: str) -> str:
    if not SLUG_RE.fullmatch(value or ""):
        raise ValueError(f"非法 slug: {value!r}")
    return value


def _candidate_file(candidate_id: str) -> Path | None:
    if len(candidate_id or "") > 200 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", candidate_id or ""):
        raise ValueError("候选 ID 只能包含小写字母、数字和连字符")
    for suffix in (".yaml", ".json"):
        path = (CANDIDATES_DIR / f"{candidate_id}{suffix}").resolve()
        if path.parent != CANDIDATES_DIR.resolve():
            raise ValueError("候选路径越界")
        if path.exists():
            return path
    return None


def _apply_update_candidate(data: dict) -> tuple[Path, str]:
    final_slug = _safe_slug(data.get("platform_slug", ""))
    source_url = data.get("source_url")
    source_hash = data.get("source_hash")
    platform_hash = data.get("platform_hash")
    proposed = data.get("proposed")
    if not isinstance(source_url, str) or not source_url.startswith("https://"):
        raise ValueError("更新候选必须包含 HTTPS 来源")
    if not isinstance(source_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", source_hash):
        raise ValueError("更新候选来源哈希无效")
    if not isinstance(platform_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", platform_hash):
        raise ValueError("更新候选平台哈希无效")
    if not isinstance(proposed, dict):
        raise ValueError("更新候选缺少 proposed 数据")

    dest_yaml = PLATFORMS_DIR / f"{final_slug}.yaml"
    if not dest_yaml.exists():
        raise ValueError(f"正式平台不存在: {final_slug}")
    platform = yaml.safe_load(dest_yaml.read_text(encoding="utf-8")) or {}
    if _platform_hash(platform) != platform_hash:
        raise ValueError("正式数据已在候选生成后变更，请重新提取候选")
    authorized_sources = set(platform.get("source_urls", [])) | {
        item.get("url") for item in platform.get("evidence", []) if isinstance(item, dict)
    }
    if source_url not in authorized_sources:
        raise ValueError("候选来源已不再被该平台授权")
    current = data.get("current")
    if not isinstance(current, dict) or any(platform.get(key) != value for key, value in current.items()):
        raise ValueError("正式数据已在候选生成后变更，请重新提取候选")
    if _source_hash(source_url) != source_hash:
        raise ValueError("来源页面已在候选生成后变更，请重新提取候选")
    quota = proposed.get("free_quota")
    quota_errors = validate_quota(quota, "proposed.free_quota")
    if quota_errors:
        raise ValueError("; ".join(quota_errors))
    if quota.get("amount") is not None:
        platform.setdefault("free_quota", {}).update(
            {key: value for key, value in quota.items() if value is not None}
        )
    if isinstance(proposed.get("intro"), str) and proposed["intro"].strip():
        platform["intro"] = proposed["intro"].strip()
    platform["last_checked"] = date.today().isoformat()
    platform["last_verified"] = date.today().isoformat()
    for evidence in platform.get("evidence", []):
        if evidence.get("url") == source_url:
            evidence.update({
                "checked_at": date.today().isoformat(),
                "source_hash": source_hash,
                "captured_at": data.get("captured_at"),
            })
    errors = validate_platform(platform, final_slug)
    if errors:
        raise ValueError("; ".join(errors))
    dest_yaml.write_text(
        yaml.safe_dump(platform, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    HASHES_FILE.parent.mkdir(exist_ok=True)
    hashes = json.loads(HASHES_FILE.read_text(encoding="utf-8")) if HASHES_FILE.exists() else {}
    hashes[source_url] = source_hash
    HASHES_FILE.write_text(
        json.dumps(hashes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return dest_yaml, final_slug


def _validate_capability_probe(data: dict) -> tuple[Path, dict, dict]:
    unknown = set(data) - CAPABILITY_PROBE_KEYS
    missing = CAPABILITY_PROBE_KEYS - {"review"} - set(data)
    if unknown or missing:
        raise ValueError("能力探测候选字段无效")
    if data.get("candidate_version") != 2 or isinstance(data.get("candidate_version"), bool):
        raise ValueError("能力探测候选版本无效")
    slug = _safe_slug(data.get("platform_slug", ""))
    if data.get("operation_id") != "chat_completions":
        raise ValueError("能力探测操作无效")
    config = load_probe_config()
    tool = data.get("tool")
    tool_config = config["tools"].get(tool)
    if not tool_config or data.get("promotion_target") != tool_config["promotion_target"]:
        raise ValueError("能力探测工具无效")
    if data.get("client") != tool_config["client"] or data.get("client_version") != tool_config["client_version"]:
        raise ValueError("能力探测客户端版本无效")
    for field in ("platform_hash", "endpoint_hash", "probe_config_hash"):
        if not isinstance(data.get(field), str) or not re.fullmatch(r"[a-f0-9]{64}", data[field]):
            raise ValueError("能力探测哈希无效")
    status_code = data.get("observed_status_code")
    if status_code is not None and (isinstance(status_code, bool) or not isinstance(status_code, int) or not 100 <= status_code <= 599):
        raise ValueError("能力探测状态码无效")
    latency = data.get("latency_ms")
    if isinstance(latency, bool) or not isinstance(latency, int) or not 0 <= latency <= 120000:
        raise ValueError("能力探测延迟无效")
    if not isinstance(data.get("protocol_valid"), bool) or data.get("decision") not in {"live", "failed"}:
        raise ValueError("能力探测结果无效")
    try:
        checked_at = datetime.fromisoformat(data.get("checked_at", ""))
    except (TypeError, ValueError) as exc:
        raise ValueError("能力探测时间无效") from exc
    if checked_at.tzinfo is None or checked_at.utcoffset().total_seconds() != 0:
        raise ValueError("能力探测时间必须为 UTC")
    age = datetime.now(timezone.utc) - checked_at
    if age.total_seconds() < -300 or age.days > 7:
        raise ValueError("能力探测已过期，请重新探测")
    evidence_url = data.get("evidence_url")
    if not isinstance(evidence_url, str) or not re.fullmatch(
        r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/runs/[0-9]+", evidence_url
    ):
        raise ValueError("能力探测证据 URL 无效")

    path = PLATFORMS_DIR / f"{slug}.yaml"
    if not path.exists():
        raise ValueError(f"正式平台不存在: {slug}")
    platform = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if _platform_hash(platform) != data["platform_hash"]:
        raise ValueError("正式数据已在能力探测后变更，请重新探测")
    operations = [item for item in platform.get("capabilities", {}).get("operations", []) if item.get("id") == data["operation_id"]]
    if len(operations) != 1:
        raise ValueError("正式操作已变更，请重新探测")
    operation = operations[0]
    endpoint = operation.get("endpoint_url")
    if endpoint != data.get("endpoint_url") or hashlib.sha256(endpoint.encode("utf-8")).hexdigest() != data["endpoint_hash"]:
        raise ValueError("正式端点已变更，请重新探测")
    if data.get("model") not in operation.get("models", []):
        raise ValueError("正式模型已变更，请重新探测")
    if operation.get("protocol") != "openai":
        raise ValueError("正式协议已变更，请重新探测")
    provider_config = config["providers"].get(slug)
    if not provider_config or (
        provider_config.get("endpoint_url") != endpoint
        or provider_config.get("model") != data["model"]
        or provider_config.get("api_key_env") != operation.get("auth", {}).get("env_var")
    ):
        raise ValueError("能力探测不在固定提供商配置中")
    if data["probe_config_hash"] != probe_config_hash(slug, operation, data["model"]):
        raise ValueError("能力探测配置已变更，请重新探测")
    return path, platform, operation


def _apply_capability_probe(data: dict) -> tuple[Path, str]:
    path, platform, operation = _validate_capability_probe(data)
    if data["decision"] != "live" or not data["protocol_valid"] or not 200 <= (data["observed_status_code"] or 0) < 300:
        raise ValueError("失败的能力探测只能拒绝并归档，不能应用到正式数据")
    operation["verification"] = {
        "status": "live",
        "checked_at": data["checked_at"][:10],
        "evidence_url": data["evidence_url"],
    }
    tools = platform["capabilities"]["tools"]
    tools[data["promotion_target"]] = "live"
    errors = validate_platform(platform, data["platform_slug"])
    if errors:
        raise ValueError("; ".join(errors))
    path.write_text(yaml.safe_dump(platform, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path, data["platform_slug"]


def approve_candidate(candidate_id: str):
    with _approval_lock():
        return _approve_candidate_locked(candidate_id)


def _approve_candidate_locked(candidate_id: str):
    target_file = _candidate_file(candidate_id)

    if not target_file:
        print(f"[ERROR] 未找到代号为 '{candidate_id}' 的待审候选源。请使用 --list 查看待审列表。")
        return False

    if target_file.suffix == ".yaml":
        data = yaml.safe_load(target_file.read_text(encoding="utf-8")) or {}
    else:
        data = json.loads(target_file.read_text(encoding="utf-8"))

    if data.get("candidate_type") in {"platform_update", "capability_probe"}:
        final_slug = _safe_slug(data.get("platform_slug", ""))
    else:
        proposed = data.get("proposed")
        if not isinstance(proposed, dict):
            raise ValueError("新平台候选缺少 proposed 数据")
        final_slug = _safe_slug(data.get("platform_slug", ""))
    dest_yaml = PLATFORMS_DIR / f"{final_slug}.yaml"
    dest_backup = dest_yaml.read_bytes() if dest_yaml.exists() else None
    hashes_backup = HASHES_FILE.read_bytes() if HASHES_FILE.exists() else None
    generated_backups = {path: path.read_bytes() if path.exists() else None for path in GENERATED_FILES}
    candidate_backup = target_file.read_bytes()

    try:
        _mark_candidate_reviewed(target_file, data, "approved")
        if data.get("candidate_type") == "platform_update":
            _apply_update_candidate(data)
        elif data.get("candidate_type") == "capability_probe":
            _apply_capability_probe(data)
        else:
            if dest_backup is not None:
                raise ValueError(f"正式平台已存在，拒绝覆盖: {final_slug}")
            errors = validate_platform(proposed, final_slug)
            if errors:
                raise ValueError("; ".join(errors))
            dest_yaml.write_text(yaml.safe_dump(proposed, allow_unicode=True, sort_keys=False), encoding="utf-8")

        print("[1/2] 重新生成聚合数据 (compile_data.py)...")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "compile_data.py")], check=True)

        print("[2/2] 构建静态网页 (npm run build)...")
        site_dir = ROOT / "site"
        npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
        subprocess.run([npm_cmd, "run", "build"], cwd=site_dir, check=True)
        _archive_candidate(target_file, "approved")
    except Exception:
        if dest_backup is None:
            dest_yaml.unlink(missing_ok=True)
        else:
            dest_yaml.write_bytes(dest_backup)
        if hashes_backup is None:
            HASHES_FILE.unlink(missing_ok=True)
        else:
            HASHES_FILE.write_bytes(hashes_backup)
        for path, backup in generated_backups.items():
            if backup is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(backup)
        if target_file.exists():
            target_file.write_bytes(candidate_backup)
        raise

    print(f"[OK] 审核通过并完成构建: data/platforms/{final_slug}.yaml")

    print(f"\n平台【{data.get('name', final_slug)}】已批准并通过本地构建，等待发布。\n")
    return True


def _record_reviewed_source_hash(data: dict) -> None:
    """记录已人工审核过的来源版本，避免同一来源反复进入候选队列。"""
    if data.get("candidate_type") != "platform_update":
        return
    source_url = data.get("source_url")
    source_hash = data.get("source_hash")
    if not isinstance(source_url, str) or not source_url.startswith("https://"):
        return
    if not isinstance(source_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", source_hash):
        return
    HASHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    hashes = json.loads(HASHES_FILE.read_text(encoding="utf-8")) if HASHES_FILE.exists() else {}
    hashes[source_url] = source_hash
    HASHES_FILE.write_text(
        json.dumps(hashes, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def reject_candidate(candidate_id: str):
    with _approval_lock():
        target_file = _candidate_file(candidate_id)
        if not target_file:
            print(f"[ERROR] 未找到候选源: {candidate_id}")
            return False
        if target_file.suffix == ".yaml":
            data = yaml.safe_load(target_file.read_text(encoding="utf-8")) or {}
        else:
            data = json.loads(target_file.read_text(encoding="utf-8"))
        _mark_candidate_reviewed(target_file, data, "rejected")
        _record_reviewed_source_hash(data)
        _archive_candidate(target_file, "rejected")
        print(f"[OK] 已拒绝并归档候选源: {target_file.name}")
        return True


def main():
    parser = argparse.ArgumentParser(description="FreeToken 候选平台审核与决策终端")
    parser.add_argument("--list", action="store_true", help="列出所有待审候选平台")
    parser.add_argument("--approve", type=str, help="批准候选文件 ID（不含扩展名）")
    parser.add_argument("--reject", type=str, help="拒绝并忽略指定平台 slug")
    args = parser.parse_args()

    if args.list:
        list_candidates()
        return 0
    elif args.approve:
        return 0 if approve_candidate(args.approve) else 1
    elif args.reject:
        return 0 if reject_candidate(args.reject) else 1
    else:
        candidates = list_candidates()
        if not candidates:
            return
        choice = input("请输入要批准的平台代号 (输入 q 退出): ").strip()
        if choice and choice.lower() != "q":
            return 0 if approve_candidate(choice) else 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
