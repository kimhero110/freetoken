#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Feishu platform tip intake: safe fetch → LLM extract → dedupe → candidate.

Writes ONLY to data/candidates/. Canonical data changes remain gated by the
Review candidate workflow. Exits non-zero on failure (daemon reports via run state).
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT / "scripts"))
from extract import parse_json_safely, build_update_candidate  # noqa: E402
from platform_schema import validate_quota  # noqa: E402
from safe_http import get_public_text  # noqa: E402

PLATFORMS_DIR = ROOT / "data" / "platforms"
CANDIDATES_DIR = ROOT / "data" / "candidates"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

SYSTEM_PROMPT = """你是 FreeToken 平台数据提取器。从用户提供的网页文本中提取免费 Token 平台信息。
只输出一个 JSON 对象，不要输出任何其他文字。字段：
slug(小写连字符), name, name_en, category(国内主流|海外主流|新兴GPU云|开源生态 之一),
intro(一句话), intro_en, website, doc_url, api_base_url, free_quota{type,amount,unit,reset_period,details,details_en},
verification(注册方式), tags(3-6个), gotchas(注意事项数组), gotchas_en。
不确定的字段填 unknown 或空数组，绝不允许编造。金额/数字必须是有限数字。"""


def domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except ValueError:
        return ""


def load_platforms():
    platforms = []
    for path in sorted(PLATFORMS_DIR.glob("*.yaml")):
        try:
            platforms.append((path.stem, yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
        except yaml.YAMLError:
            continue
    return platforms


def find_match(url: str):
    domain = domain_of(url)
    for slug, platform in load_platforms():
        candidates = [platform.get("website", ""), platform.get("api_base_url", "")]
        candidates += platform.get("source_urls", []) or []
        candidates += [e.get("url", "") for e in platform.get("evidence", []) if isinstance(e, dict)]
        for known in candidates:
            if not isinstance(known, str) or not known:
                continue
            if domain and (domain_of(known) == domain or known.rstrip("/") == url.rstrip("/")):
                return slug, platform, known == url or domain_of(known) == domain
    return None


def call_deepseek(text: str, url: str) -> dict | None:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("[ERROR] DEEPSEEK_API_KEY missing")
        return None
    response = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"来源 URL: {url}\n\n网页文本（截断）：\n{text[:24000]}"},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 2000,
            "temperature": 0.1,
        },
        timeout=90,
    )
    if response.status_code != 200:
        print(f"[ERROR] deepseek {response.status_code}: {response.text[:200]}")
        return None
    content = response.json()["choices"][0]["message"]["content"]
    return parse_json_safely(content)


def build_platform(extracted: dict, url: str, note: str) -> dict:
    slug = str(extracted.get("slug", "")).strip().lower()
    slug = re.sub(r"[^a-z0-9-]", "-", slug).strip("-")
    if not SLUG_RE.fullmatch(slug or ""):
        slug = domain_of(url).split(".")[0] or "platform"
    return {
        "schema_version": 2,
        "slug": slug,
        "name": str(extracted.get("name") or slug)[:80],
        "name_en": str(extracted.get("name_en") or slug)[:80],
        "category": str(extracted.get("category") or "海外主流")[:20],
        "intro": str(extracted.get("intro") or "")[:300] or "待补充",
        "intro_en": str(extracted.get("name_en") or "")[:300],
        "website": str(extracted.get("website") or url)[:200],
        "doc_url": str(extracted.get("doc_url") or url)[:200],
        "api_base_url": str(extracted.get("api_base_url") or "")[:200],
        "free_quota": extracted.get("free_quota") or {"type": "未知", "amount": None, "unit": "unknown"},
        "verification": str(extracted.get("verification") or "unknown")[:40],
        "status": "active",
        "last_verified": date.today().isoformat(),
        "tags": [str(t)[:20] for t in (extracted.get("tags") or [])[:6]] or ["待核实"],
        "gotchas": [str(g)[:200] for g in (extracted.get("gotchas") or [])[:4]],
        "gotchas_en": [],
        "registration": {"url": str(extracted.get("website") or url)[:200]},
        "requirements": {"phone": "unknown", "card": "unknown", "region": "unknown", "regions": [], "rpm": None, "tpm": None},
        "capabilities": {
            "operations": [],
            "tools": {key: "unknown" for key in ("curl", "openai_python", "openai_node", "cursor", "openclaw", "cherry_studio")},
        },
        "source_urls": [url],
        "note": note[:200],
        "evidence": [{"url": url, "checked_at": date.today().isoformat()}],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--note", default="")
    parser.add_argument("--ticket-id", required=True)
    args = parser.parse_args()
    if not args.url.startswith("https://") or len(args.url) > 300:
        print("[ERROR] invalid url")
        return 2
    if not re.fullmatch(r"[a-z0-9-]{1,64}", args.ticket_id):
        print("[ERROR] invalid ticket id")
        return 2

    try:
        body = get_public_text(args.url, timeout=25)
    except Exception as exc:
        print(f"[ERROR] fetch failed: {exc}")
        return 3
    import bs4
    soup = bs4.BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    if len(text) < 120:
        print("[ERROR] page too short (paywall or empty?)")
        return 3

    match = find_match(args.url)
    if match:
        slug, platform, _ = match
        authorized = args.url in (platform.get("source_urls") or []) or any(
            isinstance(e, dict) and e.get("url") == args.url for e in platform.get("evidence", [])
        )
        candidate = {
            "candidate_type": "source_note",
            "platform_slug": slug,
            "ticket_id": args.ticket_id,
            "source_url": args.url,
            "note": args.note[:200],
            "captured_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
        if authorized:
            extracted = call_deepseek(text, args.url)
            if not isinstance(extracted, dict) or validate_quota(extracted.get("free_quota")):
                print("[ERROR] update extraction has invalid quota")
                return 4
            intro = extracted.get("intro")
            if not isinstance(intro, str) or not intro.strip() or len(intro) > 200:
                print("[ERROR] update extraction has invalid intro")
                return 4
            candidate = build_update_candidate(
                platform, slug, args.url, hashlib.sha256(text.encode("utf-8")).hexdigest(), text,
                {"free_quota": extracted["free_quota"], "intro": intro.strip()},
                {"provider": "deepseek", "model": "deepseek-chat"},
            )
            candidate.update({"ticket_id": args.ticket_id, "note": args.note[:200]})
        name = "note-" if not authorized else "update-"
        CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
        (CANDIDATES_DIR / f"{name}{slug}-{args.ticket_id}.yaml").write_text(
            yaml.safe_dump(candidate, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        print(f"[OK] platform exists: {slug} ({'authorized source' if authorized else 'unauthorized source, note-only candidate'})")
        return 0

    extracted = call_deepseek(text, args.url)
    if extracted is None:
        extracted = call_deepseek(text, args.url)  # single retry
    if extracted is None:
        print("[ERROR] extraction failed twice")
        return 4
    platform = build_platform(extracted, args.url, args.note)
    existing = {path.stem for path in PLATFORMS_DIR.glob("*.yaml")}
    base_slug = platform["slug"]
    counter = 2
    while platform["slug"] in existing:
        platform["slug"] = f"{base_slug}-{counter}"
        counter += 1
    candidate = {
        "candidate_type": "new_platform",
        "platform_slug": platform["slug"],
        "ticket_id": args.ticket_id,
        "source_url": args.url,
        "note": args.note[:200],
        "proposed": platform,
        "captured_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    (CANDIDATES_DIR / f"tip-{platform['slug']}-{args.ticket_id}.yaml").write_text(
        yaml.safe_dump(candidate, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(f"[OK] new platform candidate: {platform['slug']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
