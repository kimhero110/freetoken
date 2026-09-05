#!/usr/bin/env python3
"""抓取各平台来源页面，基于内容哈希做变更检测。

- 读取 data/platforms/*.yaml 中的 source_urls
- 请求每个 URL（带 UA、超时、失败容忍）
- 对比 .cache/hashes.json 中已成功处理的正文 SHA256 哈希
- 仅哈希发生变化的来源会被记录到 .cache/changed.json，供 extract.py 增量处理并在成功后推进哈希
"""

import hashlib
import json
import sys
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
    CACHE_DIR.mkdir(exist_ok=True)
    hashes = load_hashes()
    changed: list[dict] = []
    attempted = 0
    succeeded = 0

    yaml_files = sorted(PLATFORMS_DIR.glob("*.yaml"))
    print(f"共发现 {len(yaml_files)} 个平台条目")

    for yf in yaml_files:
        entry = yaml.safe_load(yf.read_text(encoding="utf-8"))
        name = entry.get("name", yf.stem)
        for url in entry.get("source_urls", []):
            attempted += 1
            text = fetch_text(url)
            if text is None:
                continue  # 抓取失败时保留旧哈希，下一轮重试
            succeeded += 1
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if hashes.get(url) != digest:
                hashes[url] = digest
                changed.append({"platform": yf.stem, "url": url, "hash": digest})
                print(f"  [变更] {name} - {url}")
            else:
                print(f"  [未变] {name} - {url}")

    # hashes.json 只记录已经成功提取的来源版本。不要在此提前推进哈希，
    # 否则后续 API 或数据校验失败时，下一轮会把该来源误判为“未变”。
    CHANGED_FILE.write_text(
        json.dumps(changed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n本轮来源覆盖率：{succeeded}/{attempted} 成功；{len(changed)} 个来源变更，已写入 {CHANGED_FILE}")
    if attempted and succeeded == 0:
        print("全部来源抓取失败，拒绝将监控失效报告为无变化")
        return 1
    if coverage_degraded(attempted, succeeded):
        print(f"来源成功率低于 50%（{succeeded}/{attempted}），监控已降级，拒绝静默报告成功")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
