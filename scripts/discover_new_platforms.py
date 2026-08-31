#!/usr/bin/env python3
"""自动探测与发现全球新免费 API Token 平台的雷达脚本 (Radar Scanner)。

- 自动抓取开源社区 Awesome-Lists、公共 API 列表及开发者社区
- 对比当前 data/platforms/ 中已收录的域名，自动去重
- 调用已配置的大模型（DeepSeek/SiliconFlow等）智能评估候选网站
- 若符合要求，自动生成标准 YAML 条目并存入 data/platforms/<slug>.yaml
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS_DIR = ROOT / "data" / "platforms"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 FreeTokenRadar/1.0"
)

# 种子发现源列表（精选高质量免费资源聚合库）
DISCOVERY_SOURCES = [
    "https://raw.githubusercontent.com/cheahjs/free-llm-api-resources/main/README.md",
    "https://raw.githubusercontent.com/ripienaar/free-for-dev/master/README.md",
]

DISCOVERY_PROMPT = """你是一个资深 AI 开发者与信息雷达分析师。请分析下面的网页/项目内容，判断它是否提供面向开发者的「免费 API 额度 / 免费大模型层级 / 免费开发者 Token」。

要求：
1. 如果它【不是】免费开发者 API（比如只是普通收费软件、普通资讯文章），请只输出：
{{"is_valid": false}}

2. 如果它【确实提供】免费 API / Token / 免费开发层级，请只输出一个纯 JSON 对象，格式如下：
{{
  "is_valid": true,
  "slug": "<英文小写连字符唯一标识，如 groq 或 zhipu-ai>",
  "name": "<中文平台名>",
  "name_en": "<英文平台名>",
  "website": "<官网地址>",
  "category": "<llm-api | cloud | tools | multimodal | web3-faucet>",
  "free_quota": {{
    "amount": <数字或null>,
    "unit": "<单位，如万 tokens / 请求/天 / 次/月 / 美元>",
    "type": "<永久 | 每日 | 限时>",
    "conditions": ["<领取或使用条件1>", "<使用条件2>"]
  }},
  "register_url": "<注册或控制台直达链接>",
  "docs_url": "<开发文档链接>",
  "intro": "<50字以内的吸引人的中文SEO简介>",
  "tags": ["<标签1>", "<标签2>", "<标签3>"]
}}

待分析内容：
---
{text}
---"""


def get_existing_domains() -> set[str]:
    """收集已有平台的所有域名与 slug，用于去重。"""
    domains = set()
    for yf in PLATFORMS_DIR.glob("*.yaml"):
        domains.add(yf.stem.lower())
        try:
            data = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
            for key in ("website", "register_url", "docs_url"):
                if url := data.get(key):
                    if host := urlparse(url).netloc.lower():
                        domains.add(host)
                        domains.add(re.sub(r"^www\.", "", host))
        except Exception:
            pass
    return domains


def fetch_candidate_urls() -> list[str]:
    """从种子源提取候选 URL。"""
    candidates = []
    for src in DISCOVERY_SOURCES:
        print(f"[雷达扫描] 正在扫描种子源: {src}")
        try:
            resp = requests.get(src, headers={"User-Agent": UA}, timeout=20)
            if resp.status_code == 200:
                urls = re.findall(r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s\)\]\"]*)?', resp.text)
                for u in urls:
                    host = urlparse(u).netloc.lower()
                    if host and "github.com" not in host and "twitter.com" not in host:
                        candidates.append(u)
        except Exception as exc:
            print(f"  [无法访问种子源] {src}: {exc}")
    return list(set(candidates))


def extract_page_text(url: str) -> str | None:
    """抓取目标页面纯文本。"""
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:6000]
    except Exception:
        return None


def get_llm_client():
    if key := os.environ.get("DEEPSEEK_API_KEY"):
        return OpenAI(api_key=key, base_url="https://api.deepseek.com"), "deepseek-chat"
    if key := os.environ.get("SILICONFLOW_API_KEY"):
        return OpenAI(api_key=key, base_url="https://api.siliconflow.cn/v1"), "deepseek-ai/DeepSeek-V3"
    if key := os.environ.get("MOONSHOT_API_KEY"):
        return OpenAI(api_key=key, base_url="https://api.moonshot.cn/v1"), "moonshot-v1-8k"
    return None, ""


def main() -> int:
    print("========================================")
    print("🔍 启动 FreeToken 全球新免费资源发现雷达")
    print("========================================")

    all_dp = get_existing_domains()
    print(f"[去重库] 当前已收录平台及关联域名数: {len(all_dp)}")

    cand_l = fetch_candidate_urls()
    print(f"[发现雷达] 共提取到 {len(cand_l)} 个候选链接")

    client, model_n = get_llm_client()
    if not client:
        print("[提示] API Key 未配置，以仅扫描模式运行")

    new_found = 0
    for url in cand_l[:25]:
        host = urlparse(url).netloc.lower()
        clean_host = re.sub(r"^www\.", "", host)

        if host in all_dp or clean_host in all_dp:
            continue

        print(f"\n[评估新目标] {url}")
        text = extract_page_text(url)
        if not text or len(text) < 100:
            continue

        if not client:
            continue

        try:
            resp = client.chat.completions.create(
                model=model_n,
                messages=[{"role": "user", "content": DISCOVERY_PROMPT.format(text=text)}],
                temperature=0.1,
            )
            content = resp.choices[0].message.content or ""
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if not match:
                continue
            data = json.loads(match.group(0))

            if data.get("is_valid") and data.get("slug"):
                slug = re.sub(r'[^a-z0-9-]', '', data["slug"].lower())
                target_file = PLATFORMS_DIR / f"{slug}.yaml"
                if target_file.exists():
                    continue

                yaml_entry = {
                    "name": data.get("name", slug),
                    "name_en": data.get("name_en", slug),
                    "website": data.get("website", url),
                    "category": data.get("category", "llm-api"),
                    "free_quota": data.get("free_quota", {}),
                    "register_url": data.get("register_url", url),
                    "docs_url": data.get("docs_url", url),
                    "source_urls": [url],
                    "last_verified": date.today().isoformat(),
                    "status": "unverified",
                    "intro": data.get("intro", "新发现的免费 Token 资源平台"),
                    "tags": data.get("tags", ["自动雷达", "新收录"]),
                }

                target_file.write_text(
                    yaml.safe_dump(yaml_entry, allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )
                print(f"  🎉 [收录新免费 API] -> {target_file}")
                all_dp.add(host)
                new_found += 1
        except Exception as exc:
            print(f"  [评估异常] {exc}")

    print(f"\n[雷达扫描完毕] 本次共自动发现并收录新平台: {new_found}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
