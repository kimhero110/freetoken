# -*- coding: utf-8 -*-
"""
FreeToken Feishu Robot Notification Engine (Security & Multi-Link v3.0)
------------------------------------------------------------------------
- Security: Supports HMAC-SHA256 signature verification (timestamp + sign)
- Security: Hardens custom keyword 'FreeToken' across all cards
- Actions: Multi-domain quick navigation (FreeTokens.info + witkit.zone + Umami analytics)
"""

import os
import time
import json
import hmac
import hashlib
import base64
import urllib.request
import urllib.error

DEFAULT_KEYWORD = "FreeToken"


def get_feishu_webhook() -> str:
    return os.environ.get("FEISHU_WEBHOOK_URL", "").strip()


def get_feishu_secret() -> str:
    return os.environ.get("FEISHU_SECRET", "").strip()


def generate_signature(secret: str, timestamp: int) -> str:
    """Feishu HMAC-SHA256 signature algorithm."""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def send_feishu_card(card_payload: dict, secret: str = None) -> bool:
    webhook = get_feishu_webhook()
    if not webhook:
        print("[FEISHU] No webhook configured, skipping notification.")
        return False

    secret_to_use = secret or get_feishu_secret()

    payload = dict(card_payload)
    if secret_to_use:
        ts = int(time.time())
        sign = generate_signature(secret_to_use, ts)
        payload["timestamp"] = str(ts)
        payload["sign"] = sign

    req = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("StatusCode") == 0 or data.get("code") == 0:
                print("[FEISHU] Message card delivered successfully.")
                return True
            else:
                print(f"[FEISHU] API error/warning: {data}")
                return False
    except Exception as e:
        print(f"[FEISHU] Delivery failed: {e}")
        return False


def get_standard_action_buttons(candidate_url: str = None, candidate_slug: str = None) -> list:
    """Generate the standardized 3-site navigation button group + candidate action."""
    buttons = []
    if candidate_url:
        buttons.append({
            "tag": "button",
            "text": {
                "tag": "plain_text",
                "content": "🌐 访问官网核实"
            },
            "type": "primary",
            "url": candidate_url
        })

    buttons.extend([
        {
            "tag": "button",
            "text": {
                "tag": "plain_text",
                "content": "⚡ witkit.zone (国内直连)"
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
                "content": "📊 实时监控大盘"
            },
            "type": "default",
            "url": "https://analytics.witkit.zone"
        }
    ])
    return buttons


def notify_new_candidate(candidate: dict, secret: str = None) -> bool:
    """Send an interactive card when radar discovers a high-scoring free API platform."""
    slug = candidate.get("slug", "unknown")
    name = candidate.get("name") or candidate.get("title") or slug
    url = candidate.get("url", "")
    score = candidate.get("score", 0)
    free_quota = candidate.get("free_quota", "探测到免费额度 / 免费模型接口")
    tags_str = " · ".join(candidate.get("tags", ["免绑定", "OpenAI兼容", "限时体验"]))
    gotchas = candidate.get("gotchas", "该平台已被雷达高分捕获，请人工复核门槛（如是否需要海外手机、是否有并发限制）。")

    card = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"⚡ 【FreeToken 算力雷达】新源发现：{name}"
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**🏷️ 平台标识**\n`{slug}`"
                            }
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**🎯 匹配得分**\n`{score}/11 分`"
                            }
                        }
                    ]
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**🎁 识别免费额度**\n{free_quota}\n\n**🔖 特性标签**\n{tags_str}\n\n**💡 AI 避坑提示**\n{gotchas}"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": f"💡 FreeToken 人工决策指引：可在终端运行 `python scripts/review_candidates.py --approve {slug}` 或在对话框输入“通过 {slug}”一键发布上线。"
                        }
                    ]
                },
                {
                    "tag": "action",
                    "actions": get_standard_action_buttons(candidate_url=url, candidate_slug=slug)
                }
            ]
        }
    }
    return send_feishu_card(card, secret=secret)


def notify_approval_success(platform: dict, secret: str = None) -> bool:
    """Send a card when a candidate is approved; deployment is announced separately after verification."""
    name = platform.get("name", "新平台")
    slug = platform.get("slug", "")
    free_info = platform.get("free_quota", {}).get("details", "免费 Token 额度已就绪")

    card = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🎉 【FreeToken 算力雷达】新源审批通过：{name}"
                },
                "template": "green"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**✅ 候选已批准并入档！**\n\n- **平台代号**：`{slug}`\n- **免费额度**：{free_info}\n- **发布状态**：生产发布流水线已自动触发，双节点公网验证通过后将发送上线通知。"
                    }
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "⚡ 查看 witkit.zone 详情"
                            },
                            "type": "primary",
                            "url": f"https://witkit.zone/platform/{slug}/"
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "🌍 查看 FreeTokens.info"
                            },
                            "type": "default",
                            "url": f"https://freetokens.info/platform/{slug}/"
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
                }
            ]
        }
    }
    return send_feishu_card(card, secret=secret)


def notify_deploy_success(release_id: str, run_url: str, secret: str = None) -> bool:
    """Send a card only after both public nodes serve the verified release."""
    card = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🚀 【FreeToken】生产发布已上线"
                },
                "template": "green"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            "**✅ 双节点发布验证通过！**\n\n"
                            f"- **发布标识**：`{release_id}`\n"
                            "- **验证范围**：Cloudflare Pages (`freetokens.info`) 与腾讯云 (`witkit.zone`) 公网 "
                            "`release-id.txt` 一致性核验\n"
                            f"- **流水线**：[查看发布记录]({run_url})"
                        )
                    }
                },
                {
                    "tag": "action",
                    "actions": get_standard_action_buttons()
                }
            ]
        }
    }
    return send_feishu_card(card, secret=secret)


def send_ping(secret: str = None) -> bool:
    """Send a connection confirmation card."""
    card = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "⚡ 【FreeToken 算力雷达】安全配置已升级"
                },
                "template": "turquoise"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**🛡️ 安全配置与三站直达链接已就绪！**\n\n- **自定义关键词约定**：`FreeToken`（所有卡片标题均已锁定此关键词）\n- **签名校验支持**：已内置 HMAC-SHA256 算法，支持 `FEISHU_SECRET` 密钥校验\n- **导航矩阵**：下方已集成国内 `witkit.zone`、海外 `FreeTokens.info` 与 `Umami` 监控大盘。"
                    }
                },
                {
                    "tag": "action",
                    "actions": get_standard_action_buttons()
                }
            ]
        }
    }
    return send_feishu_card(card, secret=secret)


if __name__ == "__main__":
    send_ping()
