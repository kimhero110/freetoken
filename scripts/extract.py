#!/usr/bin/env python3
"""调用 DeepSeek API 从页面文本中结构化提取免费额度信息。

- 读取 .cache/changed.json（由 fetch_sources.py 生成），只处理发生变更的来源
- 重新抓取对应页面文本，调用 deepseek-chat（OpenAI 兼容接口）提取字段
- 将提取结果写回 data/platforms/<slug>.yaml 的 free_quota 等字段
- --dry-run 模式：跳过 API 调用，仅打印将要处理的内容
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS_DIR = ROOT / "data" / "platforms"
CHANGED_FILE = ROOT / ".cache" / "changed.json"
HASHES_FILE = ROOT / ".cache" / "hashes.json"

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 FreeTokenBot/1.0"
)

# 提取提示词模板：要求模型严格输出 JSON，字段与 YAML schema 对应
PROMPT_TEMPLATE = """你是一个信息抽取助手。请从下面的网页文本中提取该平台「免费 API 额度」的信息。

要求：
1. 只输出一个 JSON 对象，不要输出任何其他文字。
2. JSON 结构如下：
{{
  "free_quota": {{
    "amount": <数字或null>,
    "unit": "<单位，如 tokens / 次/天 / 元>",
    "type": "<永久|限时|每日>",
    "conditions": ["<条件1>", "<条件2>"]
  }},
  "intro": "<一段 50 字以内的中文 SEO 简介文案>"
}}
3. 如果文本中没有明确的免费额度信息，free_quota 各字段填 null 或空列表。

网页文本：
---
{text}
---"""


def fetch_text(url: str) -> str | None:
    """重新抓取页面文本（与 fetch_sources.py 逻辑一致）。"""
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  [抓取失败] {url}: {exc}")
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def call_deepseek(client: OpenAI, text: str) -> dict | None:
    """调用 DeepSeek 提取结构化信息，失败返回 None。"""
    # 截断过长的页面文本，控制 token 消耗
    prompt = PROMPT_TEMPLATE.format(text=text[:8000])
    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as exc:
        print(f"  [API 调用失败] {exc}")
        return None


def validate_extracted(value: object) -> dict | None:
    """校验并规范化模型输出，阻止异常类型或超长网页内容写入 YAML。"""
    if not isinstance(value, dict):
        return None
    quota = value.get("free_quota")
    intro = value.get("intro")
    if not isinstance(quota, dict) or not isinstance(intro, str):
        return None

    amount = quota.get("amount")
    unit = quota.get("unit")
    quota_type = quota.get("type")
    conditions = quota.get("conditions", [])
    if isinstance(amount, bool) or (
        amount is not None and (not isinstance(amount, (int, float)) or amount < 0)
    ):
        return None
    if unit is not None and (not isinstance(unit, str) or len(unit) > 40):
        return None
    if quota_type is not None and quota_type not in {"永久", "限时", "每日"}:
        return None
    if not isinstance(conditions, list) or len(conditions) > 10:
        return None
    if any(not isinstance(item, str) or len(item) > 200 for item in conditions):
        return None
    intro = intro.strip()
    if not intro or len(intro) > 200:
        return None

    return {
        "free_quota": {
            "amount": amount,
            "unit": unit,
            "type": quota_type,
            "conditions": conditions,
        },
        "intro": intro,
    }


def update_platform_yaml(slug: str, extracted: dict) -> None:
    """将提取结果合并回平台 YAML（保守更新，只覆盖提取到的字段）。"""
    yf = PLATFORMS_DIR / f"{slug}.yaml"
    entry = yaml.safe_load(yf.read_text(encoding="utf-8"))

    quota = extracted.get("free_quota") or {}
    if quota.get("amount") is not None:
        entry.setdefault("free_quota", {})
        entry["free_quota"].update({k: v for k, v in quota.items() if v is not None})
        # 数据由 AI 提取，标记为待人工核实
        entry["status"] = "unverified"
    if extracted.get("intro"):
        entry["intro"] = extracted["intro"]
    entry["last_checked"] = date.today().isoformat()

    yf.write_text(
        yaml.safe_dump(entry, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(f"  [已更新] {yf}")


def main() -> int:
    parser = argparse.ArgumentParser(description="从变更来源中结构化提取免费额度信息")
    parser.add_argument("--dry-run", action="store_true", help="跳过 API 调用，仅打印计划")
    args = parser.parse_args()

    if not CHANGED_FILE.exists():
        print("未找到 .cache/changed.json，请先运行 fetch_sources.py")
        return 0  # 首轮或全量缓存缺失时不视为错误

    changed = json.loads(CHANGED_FILE.read_text(encoding="utf-8"))
    if not changed:
        print("本轮无变更来源，跳过提取")
        return 0

    client = None
    if not args.dry_run:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            print("错误：缺少环境变量 DEEPSEEK_API_KEY（或使用 --dry-run）")
            return 1
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    hashes = {}
    if HASHES_FILE.exists():
        hashes = json.loads(HASHES_FILE.read_text(encoding="utf-8"))
    pending_hashes = dict(hashes)
    failed = False

    for item in changed:
        slug, url = item["platform"], item["url"]
        print(f"处理 {slug} - {url}")
        text = fetch_text(url)
        if text is None:
            failed = True
            continue
        current_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if current_hash != item["hash"]:
            print("  [跳过] 页面在检测后再次变化，将在下一轮重新处理")
            failed = True
            continue
        if args.dry_run:
            print(f"  [dry-run] 将发送 {len(text)} 字符文本至 DeepSeek，跳过实际调用")
            continue
        extracted = validate_extracted(call_deepseek(client, text))
        if extracted is None:
            print("  [校验失败] 模型输出不符合平台数据 schema")
            failed = True
            continue
        update_platform_yaml(slug, extracted)
        pending_hashes[url] = item["hash"]

    if not args.dry_run and not failed:
        HASHES_FILE.write_text(
            json.dumps(pending_hashes, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if failed:
        print("本轮存在失败项，未推进来源哈希；下次运行将自动重试")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
