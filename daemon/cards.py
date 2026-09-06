# -*- coding: utf-8 -*-
"""Feishu card builders per plan §2A: header(status+entity) / body(decision data) / footer(id+actions).

Every untrusted-derived string (page text, LLM output, URLs, notes) must pass
through lark_escape() before entering lark_md content.
"""

import json

REVOKE_URL = "https://github.com/settings/personal-access-tokens"


def lark_escape(text) -> str:
    """Escape lark_md control characters in untrusted strings."""
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _card(title: str, template: str, markdown: str, buttons=None) -> dict:
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": markdown}}]
    if buttons:
        elements.append({"tag": "action", "actions": buttons})
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": title}, "template": template},
            "elements": elements,
        },
    }


def _button(text: str, url: str, style: str = "default") -> dict:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": text},
        "type": style,
        "url": url,
    }


def ack_card(kind: str, ticket_id: str, url: str) -> dict:
    titles = {"platform": "📥 已受理：平台线索", "article": "📥 已受理：文章改写"}
    return _card(
        titles.get(kind, "📥 已受理"),
        "blue",
        f"**票据**：`{lark_escape(ticket_id)}`\n**链接**：{lark_escape(url)}\n\n"
        "处理中（抓取 → 提取/改写 → 校验 → 门禁 PR），预计 2-5 分钟，进度将在此会话更新。",
    )


def progress_card(kind: str, ticket_id: str, phase: str, detail: str = "", queue: str = "") -> dict:
    phases = {
        "dispatched": "⏳ 已触发流水线",
        "running": "⚙️ 流水线运行中",
        "pr_open": "🔀 门禁 PR 已创建",
        "awaiting_gate": "🚦 等待生产门禁批准",
        "publishing": "🚀 发布中（双节点验证）",
        "done": "✅ 完成",
        "failed": "❌ 失败",
        "cancelled": "⏹ 已取消",
    }
    lines = [f"**票据**：`{lark_escape(ticket_id)}`", phases.get(phase, lark_escape(phase))]
    if detail:
        lines.append(lark_escape(detail))
    if queue:
        lines.append(f"队列：{lark_escape(queue)}")
    template = "green" if phase == "done" else ("red" if phase in ("failed",) else "blue")
    return _card("进度 · " + ("平台" if kind == "platform" else kind), template, "\n".join(lines))


def candidate_card(short_id: str, candidate_id: str, name: str, diff_lines, caveats: list) -> dict:
    diff_md = "\n".join(
        ("🟢 +" if line.startswith("+") else "🔴 -") + " " + lark_escape(line.lstrip("+-"))
        for line in diff_lines
    ) or "（全新平台，无既有对比）"
    caveats_md = "\n".join(f"⚠️ {lark_escape(item)}" for item in caveats) or ""
    body = (
        f"**平台**：{lark_escape(name)}（新平台候选）\n\n**字段变更**\n{diff_md}"
        + (f"\n\n{caveats_md}" if caveats_md else "")
    )
    footer = (
        f"\n\n---\n短号 `{lark_escape(short_id)}` · ID `{lark_escape(candidate_id)}`\n"
        "回复引用本卡片并发送：`通过` / `拒绝`"
    )
    return _card("🆕 新平台候选", "turquoise", body + footer)


def update_candidate_card(short_id: str, candidate_id: str, name: str, diff_lines) -> dict:
    diff_md = "\n".join(
        ("🟢 +" if line.startswith("+") else "🔴 -") + " " + lark_escape(line.lstrip("+-"))
        for line in diff_lines
    )
    return _card(
        "♻️ 已在库，生成更新候选",
        "turquoise",
        f"**平台**：{lark_escape(name)}\n\n**字段变更**\n{diff_md}\n\n---\n"
        f"短号 `{lark_escape(short_id)}` · ID `{lark_escape(candidate_id)}` · 回复引用：`通过` / `拒绝`",
    )


def confirm_card(candidate_id: str, code: str) -> dict:
    return _card(
        "🔐 审批确认",
        "orange",
        f"即将{'批准' if True else ''}候选 `{lark_escape(candidate_id)}`。\n\n"
        f"确认码：**{lark_escape(code)}**（5 分钟内有效，错 3 次锁定 30 分钟）\n\n"
        f"回复：`确认 {lark_escape(code)}`",
    )


def article_card(title: str, pr_url: str, preview_url: str, words: str) -> dict:
    return _card(
        "📝 文章草稿就绪（未发布）",
        "turquoise",
        f"**标题**：{lark_escape(title)}\n**篇幅**：{lark_escape(words)}\n**状态**：[draft·未发布] 需人工在 PR 审读合并\n\n"
        f"合并后将自动走验证发布管线。来源标注已强制写入。",
        buttons=[
            _button("查看 PR", pr_url, "primary"),
            _button("Cloudflare 预览", preview_url),
        ],
    )


def error_card(title: str, reason: str, suggestion: str) -> dict:
    return _card(
        "❌ " + title,
        "red",
        f"**原因**：{lark_escape(reason)}\n**建议**：{lark_escape(suggestion)}",
    )


def help_card() -> dict:
    return _card(
        "📖 命令手册",
        "blue",
        "**平台 <url> [备注]** — 提交免费 Token 平台线索，生成候选\n"
        "**文章 <url> [备注]** — 改写为本站文章草稿 PR（默认改写，可加 参数:提纲）\n"
        "**通过 / 拒绝 <短号|ID>** — 审批候选（回复引用候选卡更稳妥）\n"
        "**确认 <6位码>** — 完成审批确认（防误触）\n"
        "**待审** — 列出全部候选\n**状态** — 管线/PAT/版本\n**撤销** — 拒绝我最新提交的线索\n"
        "**谁我** — 查看我的 open_id\n\n"
        "候选不可直接修改：拒绝后重新提交。裸链接会询问是平台还是文章。全角空格/尾标点自动兼容。",
    )


def pending_list_card(items: list) -> dict:
    if not items:
        return _card("✨ 无待审候选", "green", "雷达今日未发现新源，一切清净。")
    lines = "\n".join(
        f"`{lark_escape(item['short'])}` {lark_escape(item['name'])} · 等待 {lark_escape(item['wait'])}"
        for item in items
    )
    return _card(f"📋 待审候选（{len(items)}）", "turquoise", lines + "\n\n回复引用候选卡片：`通过` / `拒绝`")


def status_card(lines: list, pat_days: str, commit: str, uptime: str) -> dict:
    body = "\n".join(lark_escape(line) for line in lines) or "全部空闲"
    return _card(
        "📊 状态",
        "blue",
        f"{body}\n\n**PAT 剩余**：{lark_escape(pat_days)} 天（自检 {'✅' if pat_days not in ('?', '失效') else '❌'}）\n"
        f"**版本**：`{lark_escape(commit)}` · 已运行 {lark_escape(uptime)}",
    )


def disambiguation_card(url: str) -> dict:
    return _card(
        "🔗 这是什么链接？",
        "orange",
        f"{lark_escape(url)}\n\n回复：`平台` 或 `文章`",
    )


def anomaly_card(action: str, detail: str) -> dict:
    return _card(
        "🚨 异常检测",
        "red",
        f"**事件**：{lark_escape(action)}\n**详情**：{lark_escape(detail)}\n\n"
        "若非本人操作，立即吊销 PAT：",
        buttons=[_button("吊销 PAT", REVOKE_URL, "primary")],
    )


def watchdog_card(ticket_id: str, run_id: int, last_seen: str) -> dict:
    return _card(
        "⏹ 看门狗触发",
        "red",
        f"票据 `{lark_escape(ticket_id)}` 的 run {run_id} 超过 30 分钟未获批准，已自动取消以释放并发组。\n"
        f"最后活跃：{lark_escape(last_seen)}\n"
        "如仍需处理请重新发起命令。",
        buttons=[_button("吊销 PAT", REVOKE_URL, "primary")],
    )


def reconnect_card(last_seen: str) -> dict:
    return _card(
        "🔌 连接已恢复",
        "orange",
        f"断线期间（最后活跃 {lark_escape(last_seen)}）未收到回执的命令**不会补跑**，请重发。\n"
        "宕机期间的健康告警已由外部看门狗发送至本群。",
    )


def daily_card(pending: list, secret_coverage: str, releases: list, approvals: int) -> dict:
    pending_md = "\n".join(f"- `{lark_escape(p)}`" for p in pending) or "- 无"
    releases_md = "\n".join(f"- {lark_escape(r)}" for r in releases) or "- 无发布"
    return _card(
        "日报 · FreeToken 管线",
        "turquoise",
        f"**待审候选**\n{pending_md}\n\n**探针 Secret 覆盖**：{lark_escape(secret_coverage)}\n\n"
        f"**昨日发布**\n{releases_md}\n\n**昨日自动批准**：{approvals} 次（异常请吊销 PAT）",
    )


def card_json(card: dict) -> str:
    # The IM API already supplies msg_type=interactive; its content is the
    # card object, not the webhook envelope {msg_type, card}.
    return json.dumps(card.get("card", card), ensure_ascii=False)
