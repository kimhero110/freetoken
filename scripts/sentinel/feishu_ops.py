# -*- coding: utf-8 -*-
"""
WitKit Sentinel: Feishu Ops Notification Dispatcher
---------------------------------------------------
- Dispatches formatted alert (Red 🚨), recovery (Green 🟢), and summary (Blue 📊) cards
- Full HMAC-SHA256 signature verification & custom keyword compliance
"""

import os
import time
import json
import hmac
import hashlib
import base64
import urllib.request
import urllib.error


def generate_signature(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def send_card(webhook_url: str, secret: str, card_dict: dict) -> bool:
    if not webhook_url:
        print("[SENTINEL OPS] No webhook URL configured.")
        return False

    payload = dict(card_dict)
    if secret:
        ts = int(time.time())
        sign = generate_signature(secret, ts)
        payload["timestamp"] = str(ts)
        payload["sign"] = sign

    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("StatusCode") == 0 or data.get("code") == 0:
                print("[SENTINEL OPS] Card dispatched successfully.")
                return True
            else:
                print(f"[SENTINEL OPS] Feishu returned code: {data}")
                return False
    except Exception as e:
        print(f"[SENTINEL OPS] Failed to dispatch card: {e}")
        return False


def get_nav_buttons() -> list:
    return [
        {
            "tag": "button",
            "text": {
                "tag": "plain_text",
                "content": "⚡ witkit.zone (国内生产)"
            },
            "type": "default",
            "url": "https://witkit.zone"
        },
        {
            "tag": "button",
            "text": {
                "tag": "plain_text",
                "content": "🌍 FreeTokens.info (全球CDN)"
            },
            "type": "default",
            "url": "https://freetokens.info"
        },
        {
            "tag": "button",
            "text": {
                "tag": "plain_text",
                "content": "📊 Umami 监控大盘"
            },
            "type": "default",
            "url": "https://analytics.witkit.zone"
        }
    ]


def send_ops_alert(webhook_url: str, secret: str, target_name: str, target_type: str, ip: str, error_msg: str, os_type: str = None) -> bool:
    """Send Red Alert Card when a host or service fails."""
    os_badge = f" ({os_type.upper()})" if os_type else ""
    card = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🚨 【FreeToken 运维告警】{target_name}{os_badge} 异常离线！"
                },
                "template": "red"
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**🎯 目标对象**\n`{target_name}`"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**🏷️ 资产类型**\n`{target_type}`"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**🌐 Tailscale/目标IP**\n`{ip}`"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**⏱️ 发现时间**\n`{time.strftime('%Y-%m-%d %H:%M:%S')}`"
                            }
                        }
                    ]
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**⚠️ 故障诊断详情**\n<font color='red'>{error_msg}</font>\n\n*请及时检查该主机电源、网络连通性或服务进程。*"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "action",
                    "actions": get_nav_buttons()
                }
            ]
        }
    }
    return send_card(webhook_url, secret, card)


def send_ops_recovery(webhook_url: str, secret: str, target_name: str, target_type: str, ip: str, recovery_msg: str, os_type: str = None) -> bool:
    """Send Green Recovery Card when a host or service recovers."""
    os_badge = f" ({os_type.upper()})" if os_type else ""
    card = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🟢 【FreeToken 故障自愈】{target_name}{os_badge} 已恢复正常"
                },
                "template": "green"
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**🎯 目标对象**\n`{target_name}`"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**🏷️ 资产类型**\n`{target_type}`"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**🌐 Tailscale/目标IP**\n`{ip}`"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**⏱️ 恢复时间**\n`{time.strftime('%Y-%m-%d %H:%M:%S')}`"
                            }
                        }
                    ]
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**✅ 自愈状态确认**\n{recovery_msg}\n\n*节点与网络服务均已重新上线，数据链路恢复通畅。*"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "action",
                    "actions": get_nav_buttons()
                }
            ]
        }
    }
    return send_card(webhook_url, secret, card)


def send_ops_summary(webhook_url: str, secret: str, total_nodes: int, online_nodes: int, node_list: list, service_list: list) -> bool:
    """Send summary status card."""
    node_lines = []
    for n in node_list:
        icon = "🟢" if n["online"] else "🔴"
        os_icon = "🪟" if n["os"] == "windows" else "🐧" if n["os"] == "linux" else "🍎" if n["os"] == "macOS" else "💻"
        node_lines.append(f"{icon} {os_icon} **{n['name']}** (`{n['ip']}`) - {n['status']}")

    svc_lines = []
    for s in service_list:
        icon = "🟢" if s["healthy"] else "🔴"
        svc_lines.append(f"{icon} **{s['name']}** - {s['detail']}")

    card = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📊 【FreeToken 运维巡检】主机资源池健康报告"
                },
                "template": "turquoise"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**📈 资源池概览**：在线 **{online_nodes}** / 共 **{total_nodes}** 台主机\n\n**🖥️ Tailscale 主机池状态**：\n" + "\n".join(node_lines) + "\n\n**📦 关键业务服务状态**：\n" + "\n".join(svc_lines)
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "action",
                    "actions": get_nav_buttons()
                }
            ]
        }
    }
    return send_card(webhook_url, secret, card)
