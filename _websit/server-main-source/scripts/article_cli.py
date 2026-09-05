# -*- coding: utf-8 -*-
"""
FreeToken Article Management CLI
-------------------------------------------------------
Usage:
  python scripts/article_cli.py new --slug <slug> --title <title> [--category <cat>]
  python scripts/article_cli.py build
  python scripts/article_cli.py publish --slug <slug> [--message <msg>]
  python scripts/article_cli.py list

Publishing is owned exclusively by .github/workflows/publish.yml: this CLI
never commits, pushes, force-pushes, or deploys. `publish` only validates and
compiles locally, then prints the protected release procedure.
"""

import sys
import argparse
import datetime
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "articles"
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"
SITE_DATA_DIR = SITE_DIR / "src" / "data"

CONTENT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)


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
    print("[BUILD] 通过 scripts/compile_data.py 统一编译全部数据（平台 + 文章 + sitemap）...")
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "compile_data.py")], cwd=str(ROOT))
    if result.returncode != 0:
        print("[ERROR] 数据编译失败，请检查 content/articles/ 中的 frontmatter。")
        sys.exit(1)
    articles = json.loads((DATA_DIR / "articles.json").read_text(encoding="utf-8"))
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
    # Mandatory Pre-Flight Healthcheck Guard
    healthcheck_script = ROOT / "scripts" / "healthcheck.py"
    if healthcheck_script.exists():
        res = subprocess.run([sys.executable, str(healthcheck_script)], cwd=str(ROOT))
        if res.returncode != 0:
            print("[GUARD BLOCKED] 关键防御检查未通过，已阻断发布准备流程！")
            sys.exit(1)

    print("[PUBLISH] 生产发布由受保护的 publish.yml 工作流独占执行，本命令不执行任何 Git 或部署操作。")
    cmd_build()

    print("\n[NEXT] 请按以下受保护流程上线（与 README《数据更新流程》一致）：")
    print("  1. git checkout -b <branch> && git add content/ data/ site/ && git commit && git push -u origin <branch>")
    print("  2. 在 GitHub 打开 PR 合并到 main，等待 CI（测试 + 构建 + 冒烟验证）通过")
    print("  3. publish.yml 将自动：部署 Cloudflare Pages 与腾讯云、核验双节点公网 release-id、发送飞书上线通知")
    print("\n[INFO] 审批候选（平台更新/能力探针）同样会在批准后自动触发同一发布流水线。")


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
    
    p_pub = subparsers.add_parser("publish", help="Validate and compile articles, then print the protected release procedure")
    p_pub.add_argument("--slug", required=False, help="Article slug being published")
    p_pub.add_argument("--message", required=False, help="Suggested git commit message (applied manually)")
    
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
