# -*- coding: utf-8 -*-
"""
FreeToken Candidate Platform Review & One-Click Publisher
---------------------------------------------------------
- Review pending radar discoveries in data/candidates/
- One-click approve -> move to data/platforms -> recompile -> build & push
- Sends Feishu celebration card upon successful publication
"""

import sys
import os
import shutil
import argparse
from pathlib import Path
import yaml
import subprocess

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_DIR = ROOT / "data" / "candidates"
PLATFORMS_DIR = ROOT / "data" / "platforms"
CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
PLATFORMS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.append(str(ROOT / "scripts"))
try:
    from feishu_notifier import notify_approval_success
except ImportError:
    notify_approval_success = lambda x: False


def list_candidates():
    candidates = list(CANDIDATES_DIR.glob("*.yaml")) + list(CANDIDATES_DIR.glob("*.json"))
    if not candidates:
        print("[INFO] 目前没有待审候选源 (No pending candidates in data/candidates/).")
        return []

    print("\n" + "=" * 60)
    print(f"📋 【待审候选新源列表】 共 {len(candidates)} 个待决策平台")
    print("=" * 60)
    data_list = []
    for f in candidates:
        try:
            if f.suffix == ".yaml":
                d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            else:
                import json
                d = json.loads(f.read_text(encoding="utf-8"))
            slug = d.get("slug") or f.stem
            name = d.get("name") or slug
            url = d.get("website") or d.get("url") or ""
            score = d.get("score", "-")
            print(f"  • [{slug:<15}] {name:<20} | 得分: {score} | 官网: {url}")
            data_list.append((f, d))
        except Exception as e:
            print(f"  • [ERROR] 无法读取 {f.name}: {e}")
    print("=" * 60 + "\n")
    return data_list


def approve_candidate(slug: str):
    yaml_file = CANDIDATES_DIR / f"{slug}.yaml"
    json_file = CANDIDATES_DIR / f"{slug}.json"

    target_file = None
    if yaml_file.exists():
        target_file = yaml_file
    elif json_file.exists():
        target_file = json_file
    else:
        # Search by stem
        for f in CANDIDATES_DIR.glob("*"):
            if f.stem.lower() == slug.lower():
                target_file = f
                break

    if not target_file:
        print(f"[ERROR] 未找到代号为 '{slug}' 的待审候选源。请使用 --list 查看待审列表。")
        return False

    if target_file.suffix == ".yaml":
        data = yaml.safe_load(target_file.read_text(encoding="utf-8")) or {}
    else:
        import json
        data = json.loads(target_file.read_text(encoding="utf-8"))

    final_slug = data.get("slug") or target_file.stem
    dest_yaml = PLATFORMS_DIR / f"{final_slug}.yaml"

    # Write normalized YAML to platforms dir
    with open(dest_yaml, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    # Remove from candidates
    target_file.unlink()
    print(f"[OK] 成功收录！已将草稿移入: data/platforms/{final_slug}.yaml")

    # Rebuild data
    print("[1/3] 重新生成聚合数据 (compile_data.py)...")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "compile_data.py")], check=True)

    # Rebuild Astro static pages
    print("[2/3] 构建静态网页 (npm run build)...")
    site_dir = ROOT / "site"
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.run([npm_cmd, "run", "build"], cwd=site_dir, check=True)

    # Sync to tencent server if script exists
    sync_script = ROOT / "scripts" / "sync_to_tencent.py"
    if sync_script.exists():
        print("[3/3] 同步上线至腾讯云服务器...")
        try:
            subprocess.run([sys.executable, str(sync_script)], check=False)
        except Exception as e:
            print(f"[WARN] 腾讯云同步警告: {e}")

    # Notify Feishu
    print("[FEISHU] 发送审核通过上线卡片...")
    notify_approval_success(data)
    print(f"\n🎉 平台 【{data.get('name', final_slug)}】 已完成全网上线！\n")
    return True


def reject_candidate(slug: str):
    for f in CANDIDATES_DIR.glob("*"):
        if f.stem.lower() == slug.lower():
            f.unlink()
            print(f"[OK] 已拒绝并删除候选源: {f.name}")
            return True
    print(f"[ERROR] 未找到候选源: {slug}")
    return False


def main():
    parser = argparse.ArgumentParser(description="FreeToken 候选平台审核与决策终端")
    parser.add_argument("--list", action="store_true", help="列出所有待审候选平台")
    parser.add_argument("--approve", type=str, help="批准并一键上线指定平台 slug")
    parser.add_argument("--reject", type=str, help="拒绝并忽略指定平台 slug")
    args = parser.parse_args()

    if args.list:
        list_candidates()
    elif args.approve:
        approve_candidate(args.approve)
    elif args.reject:
        reject_candidate(args.reject)
    else:
        candidates = list_candidates()
        if not candidates:
            return
        choice = input("请输入要批准的平台代号 (输入 q 退出): ").strip()
        if choice and choice.lower() != "q":
            approve_candidate(choice)


if __name__ == "__main__":
    main()
