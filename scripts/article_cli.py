# -*- coding: utf-8 -*-
"""
FreeToken Article Management & Automated Publishing CLI
-------------------------------------------------------
Usage:
  python scripts/article_cli.py new --slug <slug> --title <title> [--category <cat>]
  python scripts/article_cli.py build
  python scripts/article_cli.py publish --slug <slug> [--message <msg>]
  python scripts/article_cli.py list
"""

import sys
import os
import argparse
import datetime
import json
import re
import subprocess
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "articles"
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"
SITE_DATA_DIR = SITE_DIR / "src" / "data"

CONTENT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)


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


def cmd_new(args):
    slug = args.slug.strip().lower()
    slug = re.sub(r'[^a-z0-9\-]', '-', slug).strip('-')
    if not slug:
        print("[ERROR] Invalid slug.")
        sys.exit(1)
        
    article_path = CONTENT_DIR / f"{slug}.md"
    if article_path.exists() and not args.force:
        print(f"[ERROR] Article already exists at {article_path}. Use --force to overwrite.")
        sys.exit(1)
        
    today = datetime.date.today().strftime("%Y-%m-%d")
    title = args.title or "新文章标题"
    category = args.category or "实战指南"
    
    template = f"""---
slug: {slug}
title: "{title}"
title_en: "{slug.replace('-', ' ').title()}"
date: "{today}"
updated: "{today}"
author: "FreeToken Lab"
category: "{category}"
tags: ["{category}", "AI算力", "实战教程"]
cover: "/images/hero-mascot.webp"
summary: "这是关于 {title} 的核心摘要与导读，简明扼要介绍本篇解决的关键痛点。"
summary_en: "Core summary and key takeaways for {title}."
reading_time: "5 分钟"
featured: true
---

# {title}

> **导读**：在这里写下本篇长文的核心亮点与适用读者对象。

---

## 01 · 为什么关注这个主题？

详细阐述背景与当前开发者的痛点。

```python
# 示例代码
import openai

client = openai.OpenAI(
    base_url="https://api.openai.com/v1",
    api_key="YOUR_API_KEY"
)
```

---

## 02 · 核心解决方案与架构设计

列出关键步骤与配置清单：

1. **第一步**：注册并获取 API 凭证；
2. **第二步**：配置轻量网关或本地环境变量；
3. **第三步**：在 OpenClaw / Cursor 中接入测试。

---

## 03 · 总结与长期建议

总结全文，并附上参考资源链接。
"""
    article_path.write_text(template, encoding="utf-8")
    print(f"[SUCCESS] 新文章草稿已成功创建: {article_path}")
    print(f"[INFO] 接下来请编辑该 Markdown 文件，编辑完成后运行: python scripts/article_cli.py build")


def cmd_build(args=None):
    print("[BUILD] 正在扫描并编译 content/articles/*.md ...")
    articles = []
    for f in sorted(CONTENT_DIR.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)
        slug = meta.get("slug", f.stem)
        title = meta.get("title", f.stem)
        date_str = str(meta.get("date", "2026-09-02"))
        reading_time = meta.get("reading_time") or estimate_reading_time(body)
        article_item = {
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
        articles.append(article_item)
        
    articles.sort(key=lambda x: x["date"], reverse=True)
    articles_json = json.dumps(articles, ensure_ascii=False, indent=2)
    (DATA_DIR / "articles.json").write_text(articles_json, encoding="utf-8")
    (SITE_DATA_DIR / "articles.json").write_text(articles_json, encoding="utf-8")
    print(f"[SUCCESS] 成功编译 {len(articles)} 篇文章至 data/articles.json 与 site/src/data/articles.json！")
    return articles


def cmd_list(args):
    articles_file = DATA_DIR / "articles.json"
    if not articles_file.exists():
        cmd_build()
    articles = json.loads(articles_file.read_text(encoding="utf-8"))
    print(f"\n[ARTICLES] 当前已录入文章总数: {len(articles)}")
    print("-" * 80)
    print(f"{'SLUG':<35} | {'分类':<10} | {'发布日期':<12} | {'标题'}")
    print("-" * 80)
    for a in articles:
        print(f"{a['slug']:<35} | {a['category']:<10} | {a['date']:<12} | {a['title'][:25]}")
    print("-" * 80 + "\n")


def cmd_publish(args):
    print("[PUBLISH] 启动全网发布流水线 (Build -> Commit -> Push -> Deploy -> Cloudflare & Tencent Sync)...")
    articles = cmd_build()
    
    print("[BUILD] 执行 Astro 静态编译: cd site && npm run build ...")
    build_res = subprocess.run(["npm", "run", "build"], cwd=str(SITE_DIR), shell=True, capture_output=True, text=True)
    if build_res.returncode != 0:
        print("[ERROR] Astro 构建失败:\n", build_res.stderr)
        sys.exit(1)
        
    dist_dir = ROOT / "dist"
    site_dist_dir = SITE_DIR / "dist"
    shutil.rmtree(dist_dir, ignore_errors=True)
    shutil.copytree(site_dist_dir, dist_dir)
    print("[DIST] 根目录 dist 静态产物已同步刷新！")
    
    msg = args.message or f"feat(article): 发布/更新文章 {args.slug or ''} 及其全网静态路由"
    print(f"[GIT] 提交主分支代码: git commit -m '{msg}' ...")
    subprocess.run(["git", "add", "-A"], cwd=str(ROOT), shell=True)
    subprocess.run(["git", "commit", "-m", msg], cwd=str(ROOT), shell=True)
    push_res = subprocess.run(["git", "push", "origin", "main"], cwd=str(ROOT), shell=True, capture_output=True, text=True)
    print("[GIT] 主分支 (main) 已推送到 GitHub!")
    
    print("[DEPLOY] 正在推送 deploy 分支触发 Cloudflare Pages 部署...")
    temp_dir = tempfile.mkdtemp()
    for item in os.listdir(str(site_dist_dir)):
        s = os.path.join(str(site_dist_dir), item)
        d = os.path.join(temp_dir, item)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
            
    os.chdir(temp_dir)
    subprocess.run(["git", "init", "-b", "deploy"], shell=True)
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], shell=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], shell=True)
    subprocess.run(["git", "add", "-A"], shell=True)
    subprocess.run(["git", "commit", "-m", f"deploy: {msg}"], shell=True)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/kimhero110/freetoken.git"], shell=True)
    deploy_res = subprocess.run(["git", "push", "--force", "origin", "deploy"], shell=True, capture_output=True, text=True)
    os.chdir(str(ROOT))
    shutil.rmtree(temp_dir, ignore_errors=True)
    print("[DEPLOY] Cloudflare Pages (deploy 分支) 推送完成！")
    
    sync_script = ROOT / "scripts" / "sync_to_tencent.py"
    if sync_script.exists():
        print("[TENCENT] 正在通过 SSH 增量同步至腾讯云国内生产服务器 (witkit.zone)...")
        subprocess.run(["python", str(sync_script)], cwd=str(ROOT), shell=True)
        
    print("\n[SUCCESS] 全网发布完成！文章已在以下所有节点上线：")
    print("  1. Cloudflare Pages: https://freetokens.info")
    print("  2. Tencent Cloud:    https://witkit.zone\n")


def main():
    parser = argparse.ArgumentParser(description="FreeToken Article Management & Automated Publishing CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    p_new = subparsers.add_parser("new", help="Create a new article draft")
    p_new.add_argument("--slug", required=True, help="Article slug (e.g. openclaw-token-saving)")
    p_new.add_argument("--title", required=False, help="Article title")
    p_new.add_argument("--category", required=False, default="实战指南", help="Category")
    p_new.add_argument("--force", action="store_true", help="Overwrite if exists")
    
    subparsers.add_parser("build", help="Compile all articles in content/articles/ to JSON")
    subparsers.add_parser("list", help="List all compiled articles")
    
    p_pub = subparsers.add_parser("publish", help="Build and publish articles to Cloudflare & Tencent server")
    p_pub.add_argument("--slug", required=False, help="Article slug being published")
    p_pub.add_argument("--message", required=False, help="Git commit message")
    
    args = parser.parse_args()
    if args.command == "new":
        cmd_new(args)
    elif args.command == "build":
        cmd_build(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "publish":
        cmd_publish(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
