# -*- coding: utf-8 -*-
"""Feishu OpenAPI client wrapper. Thin on purpose: SDK-dependent, verified on server, not unit-tested locally."""

import logging

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    P2ImMessageReceiveV1,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
    PatchMessageRequest,
    PatchMessageRequestBody,
)

from .cards import card_json

log = logging.getLogger("feishu")


class FeishuClient:
    def __init__(self, app_id: str, app_secret: str):
        self.client = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .log_level(lark.LogLevel.WARNING)
            .build()
        )

    def send_card(self, chat_id: str, card: dict, message_id: str = "") -> str:
        """Reply in-thread when message_id given, else send to chat. Returns new message_id."""
        body = ReplyMessageRequestBody.builder() \
            .content(card_json(card)) \
            .msg_type("interactive") \
            .build()
        request = ReplyMessageRequest.builder() \
            .message_id(message_id or chat_id) \
            .request_body(body) \
            .build()
        response = self.client.im.v1.message.reply(request)
        if not response.success():
            log.error("send_card failed: %s %s", response.code, response.msg)
            return ""
        return response.data.message_id or ""

    def patch_card(self, message_id: str, card: dict) -> bool:
        """Update a previously sent card in place (progress/summary cards)."""
        request = PatchMessageRequest.builder() \
            .message_id(message_id) \
            .request_body(PatchMessageRequestBody.builder().content(card_json(card)).build()) \
            .build()
        response = self.client.im.v1.message.patch(request)
        if not response.success():
            log.warning("patch_card failed (deleted card?): %s %s", response.code, response.msg)
            return False
        return True


def extract_message(event_data: P2ImMessageReceiveV1):
    """Return (sender_open_id, chat_id, message_id, text) or None for non-text messages."""
    try:
        message = event_data.event.message
        sender = event_data.event.sender
        if message.message_type != "text":
            return None
        import json
        content = json.loads(message.content or "{}")
        text = str(content.get("text", "")).strip()
        # strip @bot mention markers
        if text.startswith("@_user_"):
            text = text.split(" ", 1)[-1] if " " in text else ""
        return sender.open_id, message.chat_id, message.message_id, text
    except (AttributeError, ValueError):
        return None
