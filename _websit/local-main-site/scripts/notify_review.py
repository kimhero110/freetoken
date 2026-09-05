#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

import yaml

try:
    from feishu_notifier import notify_approval_success
except ImportError:
    from scripts.feishu_notifier import notify_approval_success


ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description="Notify an approved candidate review")
    parser.add_argument("--candidate-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.candidate_id) or len(args.candidate_id) > 200:
        raise SystemExit("invalid candidate ID")
    review = ROOT / "data" / "reviews" / f"{args.candidate_id}-approved.yaml"
    data = yaml.safe_load(review.read_text(encoding="utf-8")) or {}
    slug = data.get("platform_slug")
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise SystemExit("approved review has no safe platform slug")
    platform = yaml.safe_load((ROOT / "data" / "platforms" / f"{slug}.yaml").read_text(encoding="utf-8")) or {}
    if not notify_approval_success(platform):
        raise SystemExit("Feishu approval notification failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
