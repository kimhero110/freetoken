# -*- coding: utf-8 -*-
"""
FreeToken Feishu Robot Notification & Interactive Card Engine
------------------------------------------------------------
- Pushes rich interactive message cards for new candidate platforms
- Sends real-time approval & deployment announcements
"""

import os
import json
import urllib.request
import urllib.error

DEFAULT_WEBHOOK = "<REMOVED_FEISHU_WEBHOOK>"


def get_feishu_webhook() -> str:
    return os.environ.get("FEISHU_WEBHOOK_URL", DEFAULT_WEBHOOK)


def send_feishu_card(card_payload: dict) -> bool:
    webhook = get_feishu_webhook()
    if not webhook:
        print("[FEISHU] No webhook configured, skipping notification.")
        return False

    req = urllib.request.Request(
        webhook,
        data=json.dumps(card_payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("StatusCode") == 0 or data.get("code") == 0:
                print("[FEISHU] Message card delivered successfully.")
                return True
            else:
                print(f"[FEISHU] API warning: {data}")
                return False
    except Exception as e:
        print(f"[FEISHU] Delivery failed: {e}")
        return False


def notify_new_candidate(candidate: dict) -> bool:
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
                    "content": f"⚡ 算力雷达新发现：{name}"
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
                            "content": f"💡 人工决策指引：可在终端运行 `python scripts/review_candidates.py --approve {slug}` 一键通过并全网发布。"
                        }
                    ]
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "🌐 访问官网核对"
                            },
                            "type": "primary",
                            "url": url
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "📂 在 GitHub 审阅草稿"
                            },
                            "type": "default",
                            "url": f"https://github.com/kimhero110/freetoken/tree/main/data/candidates"
                        }
                    ]
                }
            ]
        }
    }
    return send_feishu_card(card)


def notify_approval_success(platform: dict) -> bool:
    """Send an announcement card when a candidate is officially approved and published."""
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
                    "content": f"🎉 新源审核通过：{name} 已全网上线"
                },
                "template": "green"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**🚀 平台已成功入库并发布！**\n\n- **平台代号**：`{slug}`\n- **免费额度**：{free_info}\n- **发布渠道**：Cloudflare Pages (`freetokens.info`) & 腾讯云 (`witkit.zone`)"
                    }
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "⚡ 立即查看上线页面"
                            },
                            "type": "primary",
                            "url": f"https://freetokens.info/platform/{slug}/"
                        },
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "📊 查看 Umami 监控"
                            },
                            "type": "default",
                            "url": "https://analytics.witkit.zone"
                        }
                    ]
                }
            ]
        }
    }
    return send_feishu_card(card)
