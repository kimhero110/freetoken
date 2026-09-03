# -*- coding: utf-8 -*-
"""
WitKit Sentinel: Daemon Runner & CLI Entrypoint
----------------------------------------------
Usage:
  python scripts/sentinel/run_daemon.py --once        # Run single sweep
  python scripts/sentinel/run_daemon.py --summary     # Run single sweep and send summary to Feishu
  python scripts/sentinel/run_daemon.py --daemon      # Run continuous background monitoring
  python scripts/sentinel/run_daemon.py --test-alert  # Send test Alert and Recovery cards to Feishu
"""

import sys
import time
import argparse
from pathlib import Path

# Add sentinel module directory to sys.path
SENTINEL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SENTINEL_DIR))

from core import SentinelEngine
from feishu_ops import send_ops_alert, send_ops_recovery


def test_feishu_alerts(engine: SentinelEngine):
    cfg = engine.config.get("feishu", {})
    webhook = cfg.get("webhook_url")
    secret = cfg.get("secret")

    print("[1/2] 发送模拟故障红色告警卡片...")
    send_ops_alert(
        webhook_url=webhook,
        secret=secret,
        target_name="测试宿主机-WinSrv2026",
        target_type="Windows 服务器",
        ip="100.64.0.99",
        error_msg="模拟告警：Tailscale 节点失联超过 60 秒，RDP (3389) 端口不可达！",
        os_type="windows"
    )

    time.sleep(2)

    print("[2/2] 发送模拟自愈绿色恢复卡片...")
    send_ops_recovery(
        webhook_url=webhook,
        secret=secret,
        target_name="测试宿主机-WinSrv2026",
        target_type="Windows 服务器",
        ip="100.64.0.99",
        recovery_msg="模拟自愈：Tailscale 握手恢复成功，RDP 端口连通正常 (延迟 12ms)。",
        os_type="windows"
    )
    print("\n✅ 模拟测试完成，请检查飞书群消息！\n")


def main():
    parser = argparse.ArgumentParser(description="WitKit Sentinel 运维监控守护引擎")
    parser.add_argument("--once", action="store_true", help="执行单次全量探活巡检")
    parser.add_argument("--summary", action="store_true", help="执行巡检并向飞书推送汇总健康大盘卡片")
    parser.add_argument("--daemon", action="store_true", help="常驻后台持续循环巡检")
    parser.add_argument("--test-alert", action="store_true", help="向飞书发送模拟红卡告警与绿卡自愈测试")
    args = parser.parse_args()

    engine = SentinelEngine()

    if args.test_alert:
        test_feishu_alerts(engine)
    elif args.summary:
        engine.run_sweep(send_summary=True)
    elif args.once:
        engine.run_sweep(send_summary=False)
    elif args.daemon:
        interval = engine.config.get("sentinel", {}).get("interval_seconds", 60)
        print(f"🚀 [WITKIT SENTINEL] 守护进程启动，监控周期: 每 {interval} 秒巡检一次 (按 Ctrl+C 退出)...")
        # Run first sweep with summary
        engine.run_sweep(send_summary=True)
        try:
            while True:
                time.sleep(interval)
                engine.run_sweep(send_summary=False)
        except KeyboardInterrupt:
            print("\n👋 守护进程已安全退出。")
    else:
        # Default to single sweep
        engine.run_sweep(send_summary=False)


if __name__ == "__main__":
    main()
