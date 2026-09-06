#!/usr/bin/env python3
"""Fetch source snapshots into a temporary directory.

Approved .cache/hashes.json is read-only here; only human review advances it.
Successful snapshots survive partial fetch failure for downstream extraction.
"""

import argparse
import hashlib
import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

try:
    from .safe_http import get_public_text
except ImportError:
    from safe_http import get_public_text

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS_DIR = ROOT / "data" / "platforms"
CACHE_DIR = ROOT / ".cache"
HASHES_FILE = CACHE_DIR / "hashes.json"
CHANGED_FILE = CACHE_DIR / "changed.json"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 FreeTokenBot/1.0"
)
TIMEOUT = 20  # 秒


def load_hashes() -> dict:
    if HASHES_FILE.exists():
        return json.loads(HASHES_FILE.read_text(encoding="utf-8"))
    return {}


def fetch_text(url: str) -> str | None:
    """抓取 URL 并提取纯文本；失败返回 None。"""
    try:
        body = get_public_text(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    except (requests.RequestException, ValueError) as exc:
        print(f"  [失败] {url}: {exc}")
        return None
    soup = BeautifulSoup(body, "html.parser")
    # 去掉脚本与样式，减少噪音
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def coverage_degraded(attempted: int, succeeded: int) -> bool:
    """来源成功率不足一半时视为监控降级，运行应报告失败以便告警。"""
    return attempted > 0 and succeeded * 2 < attempted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=Path(os.environ.get('RUNNER_TEMP', ROOT / '.cache' / 'check-run')))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    hashes = load_hashes()
    changed: list[dict] = []
    attempted = 0
    succeeded = 0
    observations = []

    yaml_files = sorted(PLATFORMS_DIR.glob("*.yaml"))
    print(f"共发现 {len(yaml_files)} 个平台条目")

    for yf in yaml_files:
        entry = yaml.safe_load(yf.read_text(encoding="utf-8"))
        name = entry.get("name", yf.stem)
        for url in entry.get("source_urls", []):
            attempted += 1
            text = fetch_text(url)
            if text is None:
                observations.append({'source': hashlib.sha256((yf.stem + url).encode()).hexdigest(), 'status': 'fetch_failed'})
                continue  # 抓取失败时保留旧哈希，下一轮重试
            succeeded += 1
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            observations.append({'source': hashlib.sha256((yf.stem + url).encode()).hexdigest(), 'status': 'fetched'})
            if hashes.get(url) != digest:
                changed.append({"platform": yf.stem, "url": url, "hash": digest, "text": text})
                print(f"  [变更] {name} - {url}")
            else:
                print(f"  [未变] {name} - {url}")

    # hashes.json 只记录经过人工审核的来源版本。不要在此提前推进哈希，
    # 否则后续 API 或数据校验失败时，下一轮会把该来源误判为“未变”。
    output = args.output_dir / 'changed.json'
    output.write_text(
        json.dumps(changed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / 'fetch-summary.json').write_text(json.dumps({
        'checked_at': datetime.now(timezone.utc).isoformat(), 'attempted': attempted,
        'succeeded': succeeded, 'sources': observations,
    }), encoding='utf-8')
    print(f"\n本轮来源覆盖率：{succeeded}/{attempted} 成功；{len(changed)} 个来源变更")
    if attempted and succeeded == 0:
        print("全部来源抓取失败，拒绝将监控失效报告为无变化")
        return 1
    if succeeded < attempted:
        print('存在来源抓取失败，成功来源仍可继续处理')
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
