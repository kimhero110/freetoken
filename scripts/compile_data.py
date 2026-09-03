# -*- coding: utf-8 -*-
import json
import re
from pathlib import Path
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


def compile_articles():
    articles = []
    if CONTENT_DIR.exists():
        for af in sorted(CONTENT_DIR.glob("*.md")):
            content = af.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(content)
            slug = meta.get("slug", af.stem)
            title = meta.get("title", af.stem)
            date_str = str(meta.get("date", "2026-09-02"))
            reading_time = meta.get("reading_time") or estimate_reading_time(body)
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
                "content_md": body
            }
            articles.append(item)
            
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
        '  <url><loc>https://freetokens.info/articles/</loc><changefreq>daily</changefreq><priority>0.9</priority></url>',
        '  <url><loc>https://freetokens.info/en/articles/</loc><changefreq>daily</changefreq><priority>0.9</priority></url>',
        '  <url><loc>https://freetokens.info/guide/</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>',
        '  <url><loc>https://freetokens.info/en/guide/</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>',
        '  <url><loc>https://freetokens.info/about/</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>',
        '  <url><loc>https://freetokens.info/en/about/</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>',
    ]

    for a in articles:
        lines.append(f'  <url><loc>https://freetokens.info/article/{a["slug"]}/</loc><changefreq>weekly</changefreq><priority>0.85</priority></url>')

    for p in platforms:
        lines.append(f'  <url><loc>https://freetokens.info/platform/{p["slug"]}/</loc><changefreq>daily</changefreq><priority>0.8</priority></url>')
        lines.append(f'  <url><loc>https://freetokens.info/en/platform/{p["slug"]}/</loc><changefreq>daily</changefreq><priority>0.8</priority></url>')

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
