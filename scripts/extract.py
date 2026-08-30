#!/usr/bin/env python3
"""调用大模型 API 从页面文本中结构化提取免费额度信息。

- 读取 .cache/changed.json（由 fetch_sources.py 生成），只处理发生变更的来源
- 支持多大模型 API 配置与自动降级（Fallback）：
  1. DeepSeek (DEEPSEEK_API_KEY)
  2. 硅基流动 SiliconFlow (SILICONFLOW_API_KEY)
  3. Kimi / Moonshot (MOONSHOT_API_KEY)
  4. 阿里百炼 DashScope (DASHSCOPE_API_KEY)
  5. 自定义 OpenAI 兼容接口 (LLM_API_KEY + LLM_BASE_URL + LLM_MODEL)
- 将提取结果写回 data/platforms/<slug>.yaml 的 free_quota 等字段
- --dry-run 模式：跳过 API 调用，仅打印将要处理的内容
"""

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
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

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 FreeTokenBot/1.0"
)

# 提取提示词模板：要求模型严格输出 JSON，字段与 YAML schema 对应
PROMPT_TEMPLATE = """你是一个信息抽取助手。请从下面的网页文本中提取该平台「免费 API 额度」的信息。

要求：
1. 只输出一个纯 JSON 对象，不要输出任何前后解释或 Markdown 格式以外的文字。
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


@dataclass
class Provider:
    name: str
    base_url: str
    model: str
    api_key: str


def get_available_providers() -> list[Provider]:
    """按优先级收集所有已配置环境变量的模型提供商。"""
    providers = []

    # 1. DeepSeek 官方
    if key := os.environ.get("DEEPSEEK_API_KEY"):
        providers.append(
            Provider(
                name="DeepSeek",
                base_url="https://api.deepseek.com",
                model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
                api_key=key,
            )
        )

    # 2. 硅基流动 SiliconFlow
    if key := os.environ.get("SILICONFLOW_API_KEY"):
        providers.append(
            Provider(
                name="SiliconFlow",
                base_url="https://api.siliconflow.cn/v1",
                model=os.environ.get("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3"),
                api_key=key,
            )
        )

    # 3. Kimi / Moonshot
    if key := os.environ.get("MOONSHOT_API_KEY"):
        providers.append(
            Provider(
                name="Moonshot",
                base_url="https://api.moonshot.cn/v1",
                model=os.environ.get("MOONSHOT_MODEL", "moonshot-v1-8k"),
                api_key=key,
            )
        )

    # 4. 阿里百炼 DashScope
    if key := os.environ.get("DASHSCOPE_API_KEY"):
        providers.append(
            Provider(
                name="DashScope",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model=os.environ.get("DASHSCOPE_MODEL", "qwen-plus"),
                api_key=key,
            )
        )

    # 5. 通用自定义 OpenAI 兼容接口
    if key := os.environ.get("LLM_API_KEY"):
        providers.append(
            Provider(
                name="CustomLLM",
                base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
                model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
                api_key=key,
            )
        )

    return providers


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


def parse_json_safely(raw_content: str) -> dict | None:
    """解析模型返回的 JSON，自动处理可能的 Markdown 代码块包裹。"""
    raw = raw_content.strip()
    # 去除 ```json ... ``` 标记
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 正则提取最外层花括号
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return None


def call_llm_with_fallback(providers: list[Provider], text: str) -> dict | None:
    """按优先级依次调用已配置的 LLM，失败时自动降级到下一个提供商。"""
    prompt = PROMPT_TEMPLATE.format(text=text[:8000])

    for prov in providers:
        print(f"  [AI 提取] 尝试提供商: {prov.name} (模型: {prov.model})")
        try:
            client = OpenAI(api_key=prov.api_key, base_url=prov.base_url, timeout=30.0)
            kwargs = {
                "model": prov.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            }
            # DeepSeek / Moonshot 等支持 json_object
            if prov.name in {"DeepSeek", "Moonshot", "CustomLLM"}:
                kwargs["response_format"] = {"type": "json_object"}

            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content or ""
            data = parse_json_safely(content)
            if data is not None:
                print(f"  [AI 提取成功] 由 {prov.name} 完成解析")
                return data
            else:
                print(f"  [解析警告] {prov.name} 返回内容无法解析为 JSON: {content[:100]}...")
        except Exception as exc:
            print(f"  [提供商失败] {prov.name} 报错: {exc}")

    print("  [全部失败] 所有已配置的大模型 API 均调用失败")
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

    providers = []
    if not args.dry_run:
        providers = get_available_providers()
        if not providers:
            print("错误：未找到任何可用的大模型 API Key。")
            print("请至少配置以下之一：DEEPSEEK_API_KEY, SILICONFLOW_API_KEY, MOONSHOT_API_KEY, DASHSCOPE_API_KEY, LLM_API_KEY")
            return 1
        print(f"已加载 {len(providers)} 个模型提供商: {', '.join(p.name for p in providers)}")

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
            print(f"  [dry-run] 将发送 {len(text)} 字符文本至大模型，跳过实际调用")
            continue

        raw_result = call_llm_with_fallback(providers, text)
        extracted = validate_extracted(raw_result)
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
