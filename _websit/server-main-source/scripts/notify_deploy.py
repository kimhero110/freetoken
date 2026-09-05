#!/usr/bin/env python3
"""Send the Feishu card announcing a dual-node verified production release."""
import argparse
import re

try:
    from feishu_notifier import notify_deploy_success
except ImportError:
    from scripts.feishu_notifier import notify_deploy_success


def main():
    parser = argparse.ArgumentParser(description="Notify a verified production release")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--run-url", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]{14}-[a-f0-9]{12}", args.release_id):
        raise SystemExit("invalid release ID")
    if not args.run_url.startswith("https://"):
        raise SystemExit("invalid run URL")
    if not notify_deploy_success(args.release_id, args.run_url):
        raise SystemExit("Feishu deploy notification failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
