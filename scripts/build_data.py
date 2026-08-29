#!/usr/bin/env python3
"""合并 data/platforms/*.yaml 为站点构建所需的 JSON。

输出：site/src/data/platforms.json
每条记录附加 slug（由 YAML 文件名派生），供 Astro 页面路由使用。
"""

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS_DIR = ROOT / "data" / "platforms"
OUT_FILE = ROOT / "site" / "src" / "data" / "platforms.json"

# YAML 中日期会被解析为 date 对象，JSON 序列化前统一转成字符串
def default_serializer(obj):
    return obj.isoformat()


def main() -> int:
    entries = []
    for yf in sorted(PLATFORMS_DIR.glob("*.yaml")):
        entry = yaml.safe_load(yf.read_text(encoding="utf-8"))
        entry["slug"] = yf.stem
        entries.append(entry)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2, default=default_serializer),
        encoding="utf-8",
    )
    print(f"已合并 {len(entries)} 个平台条目 -> {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
