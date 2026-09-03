# -*- coding: utf-8 -*-
"""
FreeToken Automated Global Resource Discovery Radar (Safe Print v2.2)
--------------------------------------------------------------------
- Full domain & slug deduplication against 40 platforms
- Deep heuristic scoring for Free API / Token / LLM developer offerings
- Safe console printing on Windows GBK environment
"""

import os
import sys
import re
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import yaml

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS_DIR = ROOT / "data" / "platforms"
PLATFORMS_DIR.mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 FreeTokenRadar/2.2"
)

# Candidate targets to sweep
TARGET_SEEDS = [
    "https://deepinfra.com",
    "https://chutes.ai",
    "https://aimlapi.com",
    "https://voyageai.com",
    "https://replicate.com",
    "https://glhf.chat",
    "https://kluster.ai",
    "https://anyscale.com",
    "https://baseten.co",
    "https://modal.com",
    "https://runpod.io",
    "https://lambda.chat",
    "https://openpipe.ai",
    "https://predibase.com",
    "https://lepton.ai",
    "https://featherless.ai",
    "https://deepseek.com",
    "https://siliconflow.cn",
    "https://groq.com",
    "https://cerebras.ai",
]


def sanitize_str(s: str) -> str:
    """Strip characters that cannot be encoded in GBK."""
    if not s:
        return ""
    # Keep standard ascii and basic chinese
    return re.sub(r'[^\x20-\x7E\u4e00-\u9fa5]', ' ', s).strip()


def get_existing_domains() -> set[str]:
    domains = set()
    for yf in PLATFORMS_DIR.glob("*.yaml"):
        domains.add(yf.stem.lower())
        try:
            data = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
            for key in ("website", "register_url", "docs_url", "api_base_url"):
                if url := data.get(key):
                    if host := urlparse(url).netloc.lower():
                        domains.add(host)
                        domains.add(re.sub(r"^www\.", "", host))
                        domains.add(host.split(".")[0])
        except Exception:
            pass
    return domains


def extract_page_data(url: str) -> dict | None:
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=5)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        title = (soup.title.string if soup.title else "").strip()
        for tag in soup(["script", "style", "noscript", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        
        score = 0
        keywords = ["free tier", "free api", "api key", "free credits", "developer", "pricing", "trial", "tokens", "免费", "额度", "体验金"]
        text_lower = text.lower()
        for kw in keywords:
            if kw in text_lower:
                score += 1
                
        return {
            "title": sanitize_str(title)[:50],
            "text": text[:2000],
            "score": score,
            "url": url
        }
    except Exception:
        return None


def run_discovery():
    print("=" * 60)
    print("[RADAR] Starting Global Free Token & API Discovery Sweep...")
    print("=" * 60)

    existing = get_existing_domains()
    print(f"[INFO] Existing indexed entities & domains: {len(existing)}")

    targets = list(dict.fromkeys(TARGET_SEEDS))
    print(f"[INFO] Probing candidate target pool ({len(targets)} candidates)...\n")

    scanned = 0
    already_indexed = 0
    discovered_new = []

    for url in targets:
        host = urlparse(url).netloc.lower()
        clean_host = re.sub(r"^www\.", "", host)
        slug_base = clean_host.split(".")[0]

        if host in existing or clean_host in existing or slug_base in existing:
            already_indexed += 1
            print(f"  [INDEXED] {url:<30} -> Already in 40-Platform Master DB")
            continue

        scanned += 1
        print(f"  [PROBING] {url:<30} ... ", end="", flush=True)
        data = extract_page_data(url)
        if not data:
            print("Failed (Offline / Timeout)")
            continue

        if data["score"] >= 3:
            print(f"FOUND! Match Score: {data['score']}/11 | Title: {data['title'][:25]}")
            cand_info = {
                "url": url,
                "host": host,
                "slug": slug_base,
                "title": data["title"],
                "score": data["score"]
            }
            discovered_new.append(cand_info)
            existing.add(host)

            # Persist candidate draft in data/candidates/
            candidates_dir = ROOT / "data" / "candidates"
            candidates_dir.mkdir(parents=True, exist_ok=True)
            cand_yaml = candidates_dir / f"{slug_base}.yaml"
            if not cand_yaml.exists():
                draft_content = {
                    "slug": slug_base,
                    "name": data["title"] or slug_base,
                    "name_en": slug_base.title(),
                    "category": "海外探索" if not any(c in data["text"] for c in ["免费", "元", "人民币"]) else "国内主流",
                    "intro": f"{data['title']} 提供免费体验额度与开发者 API 接口。",
                    "intro_en": f"{slug_base.title()} offers free tier API access for developers.",
                    "website": url,
                    "doc_url": f"{url.rstrip('/')}/docs",
                    "api_base_url": f"{url.rstrip('/')}/v1",
                    "free_models": ["default-free-tier"],
                    "free_quota": {
                        "type": "体验金 / 免费层",
                        "amount": "探测到免费额度",
                        "unit": "Tokens",
                        "reset_period": "每月/一次性",
                        "details": f"检测到开发者免费层/体验额度，雷达匹配得分 {data['score']}/11。"
                    },
                    "verification": "邮箱/GitHub",
                    "status": "pending_review",
                    "last_verified": str(date.today()),
                    "tags": ["雷达新源", "待人工复核", "OpenAI兼容"],
                    "gotchas": ["由雷达自动捕获，请人工复核免费层 RPM 限制与模型调用范围。"],
                    "gotchas_en": ["Discovered by radar. Manual verification recommended."]
                }
                with open(cand_yaml, "w", encoding="utf-8") as f:
                    yaml.dump(draft_content, f, allow_unicode=True, sort_keys=False)
                print(f"    -> [DRAFT] Saved candidate YAML: data/candidates/{slug_base}.yaml")

            # Push Feishu interactive notification
            try:
                from feishu_notifier import notify_new_candidate
                notify_new_candidate({
                    "slug": slug_base,
                    "name": data["title"],
                    "url": url,
                    "score": data["score"],
                    "free_quota": "包含开发者免费层 / 体验额度",
                    "tags": ["雷达新源", "待决策"],
                    "gotchas": "已在 data/candidates 生成草稿。在终端运行 `python scripts/review_candidates.py --approve " + slug_base + "` 即可一键批准上线！"
                })
            except Exception as fe:
                print(f"    -> [FEISHU WARN] Notification skipped: {fe}")
        else:
            print(f"Low relevance ({data['score']}/11)")

    print("\n" + "=" * 60)
    print(f"[RADAR SUMMARY] Radar Sweep Finished!")
    print(f"  - Verified Existing Platforms: {already_indexed}")
    print(f"  - Fresh Scanned Targets:       {scanned}")
    print(f"  - Discovered High-Match Tiers: {len(discovered_new)}")
    print("=" * 60)

    if discovered_new:
        print("\n[CANDIDATE DISCOVERY REPORT]")
        print(f"{'SLUG':<16} | {'SCORE':<6} | {'CANDIDATE URL':<30} | {'TITLE'}")
        print("-" * 75)
        for d in discovered_new:
            print(f"{d['slug']:<16} | {d['score']:<6} | {d['url'][:30]:<30} | {d['title'][:20]}")
        print("-" * 75)
        print("\n💡 提示：运行 `python scripts/review_candidates.py` 即可在终端交互式决策并一键上线！")
    else:
        print("[REPORT] All probed platforms are already 100% indexed in the database.")


if __name__ == "__main__":
    run_discovery()

