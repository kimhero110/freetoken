#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Feishu article rewrite: safe fetch → LLM rewrite/outline → validated draft markdown.

Writes content/articles/<slug>.md only; the PR is NEVER auto-merged (human review gate).
source_url is forced to the original URL (never trusted from the LLM).
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT / "scripts"))
from safe_http import get_public_text  # noqa: E402

CONTENT_DIR = ROOT / "content" / "articles"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ALLOWED_FRONTMATTER = {
    "slug", "title", "title_en", "date", "updated", "author", "category",
    "tags", "cover", "summary", "summary_en", "reading_time", "featured",
    "source_url",
}

REWRITE_PROMPT = """你是 FreeToken（freetokens.info）的资深技术作者。把用户提供的外文/外部文章改写为一篇原创中文实战文章。
要求：
1. 站点语气：技术实战、直接、面向开发者，保留代码块并翻译注释。
2. 结构：导读 → 2-4 个编号章节（## 01 · 风格）→ 总结与建议。
3. 只输出一个 JSON 对象：{"title": str, "title_en": str, "category": str, "tags": [str],
   "summary": str, "summary_en": str, "body_md": str}
4. body_md 是完整 Markdown 正文（不要包含 frontmatter，不要再写标题行）。
5. 绝不逐句照抄原文；改写为本站原创表达。"""

OUTLINE_PROMPT = """你是 FreeToken（freetokens.info）的技术编辑。基于用户提供的外部文章，输出一份供人工撰写的详细提纲。
只输出一个 JSON 对象：{"title": str, "title_en": str, "category": str, "tags": [str],
"summary": str, "summary_en": str, "body_md": str}
body_md 为提纲正文 Markdown：每章节包含要点、应覆盖的数据/代码位、以及建议的本站观点。"""


def slugify(text: str, url: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", (text or "").lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not SLUG_RE.fullmatch(slug or ""):
        slug = re.sub(r"[^a-z0-9.-]", "-", url.split("//")[1].split("/")[0]).replace(".", "-").strip("-")
    return (slug or "article")[:60].strip("-")


def call_deepseek(prompt: str, text: str, url: str, max_tokens: int) -> tuple[dict | None, str]:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return None, "NO_KEY"
    response = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"原文 URL: {url}\n\n原文（截断）：\n{text[:24000]}"},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
            "temperature": 0.4,
        },
        timeout=120,
    )
    if response.status_code != 200:
        return None, f"HTTP_{response.status_code}"
    choice = response.json()["choices"][0]
    finish = choice.get("finish_reason", "")
    try:
        parsed = json.loads(choice["message"]["content"])
    except (ValueError, KeyError):
        return None, "BAD_JSON"
    return parsed, finish


def validate_output(parsed: dict, url: str, mode: str) -> tuple[str | None, list[str]]:
    errors = []
    title = str(parsed.get("title") or "").strip()
    if not title or len(title) > 200:
        errors.append("title invalid")
    body = parsed.get("body_md")
    if not isinstance(body, str) or len(body) < (300 if mode == "rewrite" else 150):
        errors.append("body too short")
    tags = parsed.get("tags")
    if not isinstance(tags, list) or not tags or len(tags) > 12 or any(not isinstance(t, str) or len(t) > 40 for t in tags):
        errors.append("tags invalid")
    return title, errors


def render_markdown(parsed: dict, slug: str, url: str, mode: str) -> str:
    today = date.today().isoformat()
    tags = ", ".join(f'"{str(t)[:40]}"' for t in parsed.get("tags", [])[:6])
    body = parsed["body_md"].strip()
    label = "（提纲草稿，待人工撰写）" if mode == "outline" else ""
    frontmatter = f"""---
slug: "{slug}"
title: "{str(parsed.get('title') or slug)[:200]}"
title_en: "{str(parsed.get('title_en') or parsed.get('title') or slug)[:200]}"
date: "{today}"
updated: "{today}"
author: "FreeToken Lab"
category: "{str(parsed.get('category') or '实战指南')[:50]}"
tags: [{tags}]
cover: "/images/hero-mascot.webp"
summary: "{str(parsed.get('summary') or '')[:600]}"
summary_en: "{str(parsed.get('summary_en') or '')[:600]}"
featured: false
source_url: "{url}"
---

# {str(parsed.get('title') or slug)[:200]} {label}

> **导读**：{str(parsed.get('summary') or '')[:200]}

"""
    return frontmatter + body + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--note", default="")
    parser.add_argument("--ticket-id", required=True)
    parser.add_argument("--mode", choices=["rewrite", "outline"], default="rewrite")
    args = parser.parse_args()
    if not args.url.startswith("https://") or len(args.url) > 300:
        return 2
    if not re.fullmatch(r"[a-z0-9-]{1,64}", args.ticket_id):
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
    if len(text) < 300:
        print("[ERROR] source too short (paywall?)")
        return 3

    prompt = OUTLINE_PROMPT if args.mode == "outline" else REWRITE_PROMPT
    parsed, finish = call_deepseek(prompt, text, args.url, max_tokens=4096)
    if parsed is None and args.mode == "rewrite":
        print(f"[WARN] rewrite failed ({finish}); falling back to outline")
        args.mode = "outline"
        parsed, finish = call_deepseek(OUTLINE_PROMPT, text, args.url, max_tokens=3000)
    if parsed is None:
        print(f"[ERROR] LLM failed: {finish}")
        return 4
    if finish == "length" and args.mode == "rewrite":
        print("[WARN] output truncated; falling back to outline")
        args.mode = "outline"
        parsed, finish = call_deepseek(OUTLINE_PROMPT, text, args.url, max_tokens=3000)
        if parsed is None:
            return 4

    unknown_keys = set(parsed) - {"title", "title_en", "category", "tags", "summary", "summary_en", "body_md"}
    if unknown_keys:
        print(f"[WARN] dropping unknown keys: {sorted(unknown_keys)}")
    title, errors = validate_output(parsed, args.url, args.mode)
    if errors:
        print(f"[ERROR] validation failed: {errors}")
        return 5

    slug = slugify(title, args.url)
    existing = {path.stem for path in CONTENT_DIR.glob("*.md")}
    base = slug
    counter = 2
    while slug in existing:
        slug = f"{base}-{counter}"
        counter += 1

    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    (CONTENT_DIR / f"{slug}.md").write_text(render_markdown(parsed, slug, args.url, args.mode), encoding="utf-8")
    print(f"[OK] article draft written: {slug} (mode={args.mode}, source_url forced)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
