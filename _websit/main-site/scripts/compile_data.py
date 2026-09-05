# -*- coding: utf-8 -*-
import json
import re
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

from platform_schema import validate_platform

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONTENT_DIR = ROOT / "content" / "articles"
SITE_DATA_DIR = ROOT / "site" / "src" / "data"
PUBLIC_DIR = ROOT / "site" / "public"

DATA_DIR.mkdir(parents=True, exist_ok=True)
SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

ARTICLE_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_frontmatter(content: str):
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    fm_raw = parts[1].strip()
    body = parts[2].strip()
    metadata = {}
    for line in fm_raw.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            elif val.startswith("[") and val.endswith("]"):
                items = [item.strip().strip('"').strip("'") for item in val[1:-1].split(",") if item.strip()]
                val = items
            elif val.lower() == "true":
                val = True
            elif val.lower() == "false":
                val = False
            metadata[key] = val
    return metadata, body


def estimate_reading_time(text: str) -> str:
    cn_chars = len(re.findall(r'[\u4e00-\u9fa5]', text))
    en_words = len(re.findall(r'\b[a-zA-Z]+\b', text))
    total_words = cn_chars + en_words
    mins = max(1, round(total_words / 350))
    return f"{mins} 分钟"


def compile_platforms():
    platforms_dir = DATA_DIR / "platforms"
    platforms = []
    seen_slugs = set()
    if platforms_dir.exists():
        for yf in sorted(platforms_dir.glob("*.yaml")):
            data = yaml.safe_load(yf.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema_version") != 2:
                raise ValueError(f"{yf.name}: schema_version must be 2")
            slug = data.get("slug")
            if slug in seen_slugs:
                raise ValueError(f"{yf.name}: duplicate slug {slug!r}")
            errors = validate_platform(data, yf.stem)
            if errors:
                raise ValueError(f"{yf.name}: {'; '.join(errors)}")
            seen_slugs.add(slug)
            platforms.append(data)
                
    p_json = json.dumps(platforms, ensure_ascii=False, indent=2) + "\n"
    (DATA_DIR / "platforms.json").write_text(p_json, encoding="utf-8")
    (SITE_DATA_DIR / "platforms.json").write_text(p_json, encoding="utf-8")
    print(f"[DATA] Platforms compiled: {len(platforms)} platforms -> platforms.json")
    return platforms


def validate_article_meta(slug: str, meta: dict, source: str) -> list[str]:
    """文章元数据严格校验：slug、日期、字段类型与长度。"""
    errors = []
    if not isinstance(slug, str) or not ARTICLE_SLUG_RE.fullmatch(slug) or not 1 <= len(slug) <= 100:
        errors.append(f"{source}: slug 只能包含小写字母、数字与连字符，且不超过 100 字符: {slug!r}")
    title = meta.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        errors.append(f"{source}: title 必须为非空字符串且不超过 200 字符")
    date_value = str(meta.get("date") or "2026-09-02")
    updated_value = str(meta.get("updated") or date_value)
    for key, value in (("date", date_value), ("updated", updated_value)):
        if not DATE_RE.fullmatch(value):
            errors.append(f"{source}: {key} 必须为 YYYY-MM-DD 格式: {value!r}")
        else:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                errors.append(f"{source}: {key} 不是有效日期: {value!r}")
    for key, limit in (
        ("title_en", 200), ("author", 100), ("category", 50),
        ("cover", 200), ("summary", 600), ("summary_en", 600),
        ("reading_time", 30),
    ):
        value = meta.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or len(value) > limit:
            errors.append(f"{source}: {key} 必须为字符串且不超过 {limit} 字符")
    source_url = meta.get("source_url")
    if source_url is not None and (
        not isinstance(source_url, str)
        or not re.fullmatch(r"https://\S{3,200}", source_url)
    ):
        errors.append(f"{source}: source_url 必须为 HTTPS 链接（<=200 字符）")
    tags = meta.get("tags")
    if tags is not None and (
        not isinstance(tags, list)
        or len(tags) > 12
        or any(not isinstance(tag, str) or not tag.strip() or len(tag) > 40 for tag in tags)
    ):
        errors.append(f"{source}: tags 必须为字符串列表，最多 12 项，每项不超过 40 字符")
    return errors


def compile_articles():
    articles = []
    errors = []
    seen_slugs = {}
    if CONTENT_DIR.exists():
        for af in sorted(CONTENT_DIR.glob("*.md")):
            content = af.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(content)
            slug = meta.get("slug", af.stem)
            title = meta.get("title", af.stem)
            date_str = str(meta.get("date", "2026-09-02"))
            reading_time = meta.get("reading_time") or estimate_reading_time(body)
            errors.extend(validate_article_meta(slug, meta, af.name))
            if isinstance(slug, str) and slug in seen_slugs:
                errors.append(f"{af.name}: slug 重复 {slug!r}（已见于 {seen_slugs[slug]}）")
            else:
                seen_slugs[slug] = af.name
            item = {
                "slug": slug,
                "title": title,
                "title_en": meta.get("title_en", title),
                "date": date_str,
                "updated": str(meta.get("updated", date_str)),
                "author": meta.get("author", "FreeToken Lab"),
                "category": meta.get("category", "实战指南"),
                "tags": meta.get("tags", ["AI算力"]),
                "cover": meta.get("cover", "/images/hero-mascot.webp"),
                "summary": meta.get("summary", ""),
                "summary_en": meta.get("summary_en", ""),
                "reading_time": reading_time,
                "featured": meta.get("featured", False),
                "source_url": meta.get("source_url"),
                "content_md": body
            }
            articles.append(item)

    if errors:
        raise ValueError("文章元数据校验失败:\n- " + "\n- ".join(errors))

    articles.sort(key=lambda x: x["date"], reverse=True)
    a_json = json.dumps(articles, ensure_ascii=False, indent=2)
    (DATA_DIR / "articles.json").write_text(a_json, encoding="utf-8")
    (SITE_DATA_DIR / "articles.json").write_text(a_json, encoding="utf-8")
    print(f"[DATA] Articles compiled: {len(articles)} articles -> articles.json")
    return articles


def generate_sitemap(platforms, articles):
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        '  <url><loc>https://freetokens.info/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>',
        '  <url><loc>https://freetokens.info/en/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>',
        '  <url><loc>https://freetokens.info/cost/</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>',
        '  <url><loc>https://freetokens.info/en/cost/</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>',
        '  <url><loc>https://freetokens.info/articles/</loc><changefreq>daily</changefreq><priority>0.9</priority></url>',
        '  <url><loc>https://freetokens.info/en/articles/</loc><changefreq>daily</changefreq><priority>0.9</priority></url>',
        '  <url><loc>https://freetokens.info/guide/</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>',
        '  <url><loc>https://freetokens.info/en/guide/</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>',
        '  <url><loc>https://freetokens.info/about/</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        '  <url><loc>https://freetokens.info/en/about/</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>',
    ]

    for a in articles:
        loc = escape(f"https://freetokens.info/article/{a['slug']}/")
        lines.append(f'  <url><loc>{loc}</loc><changefreq>weekly</changefreq><priority>0.85</priority></url>')

    for p in platforms:
        loc_cn = escape(f"https://freetokens.info/platform/{p['slug']}/")
        loc_en = escape(f"https://freetokens.info/en/platform/{p['slug']}/")
        lines.append(f'  <url><loc>{loc_cn}</loc><changefreq>daily</changefreq><priority>0.8</priority></url>')
        lines.append(f'  <url><loc>{loc_en}</loc><changefreq>daily</changefreq><priority>0.8</priority></url>')

    lines.append('</urlset>')
    xml_content = '\n'.join(lines) + '\n'
    (PUBLIC_DIR / "sitemap.xml").write_text(xml_content, encoding="utf-8")
    print(f"[DATA] Sitemap generated: {len(lines)-2} URLs indexed -> sitemap.xml")


def main():
    platforms = compile_platforms()
    articles = compile_articles()
    generate_sitemap(platforms, articles)
    print("[SUCCESS] All pure data compilation complete!")


if __name__ == "__main__":
    main()
