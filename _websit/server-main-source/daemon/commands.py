# -*- coding: utf-8 -*-
"""Command parsing with mainland-mobile IME tolerance (fullwidth spaces, trailing punctuation)."""

import re

VERBS = {
    "平台": "platform",
    "platform": "platform",
    "文章": "article",
    "article": "article",
    "通过": "approve",
    "approve": "approve",
    "拒绝": "reject",
    "reject": "reject",
    "撤销": "undo",
    "undo": "undo",
    "待审": "pending",
    "pending": "pending",
    "状态": "status",
    "status": "status",
    "帮助": "help",
    "help": "help",
    "?": "help",
    "？": "help",
    "谁我": "whoami",
    "whoami": "whoami",
    "确认": "confirm",
    "confirm": "confirm",
}

BARE_URL_RE = re.compile(r"^https://\S{3,300}$", re.IGNORECASE)
HTTPS_URL_RE = re.compile(r"^https://\S{3,300}$", re.IGNORECASE)
CANDIDATE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHORT_ID_RE = re.compile(r"^#?p?(\d{1,3})$", re.IGNORECASE)
CONFIRM_CODE_RE = re.compile(r"^[0-9]{6}$")
TRAILING_PUNCT = "。．.!！?？，,、;；:：~～\u00a0 "


class Command:
    __slots__ = ("verb", "arg", "raw")

    def __init__(self, verb: str, arg: str, raw: str):
        self.verb = verb
        self.arg = arg.strip()
        self.raw = raw

    def __repr__(self):  # pragma: no cover
        return f"Command({self.verb!r}, {self.arg!r})"


def normalize(text: str) -> str:
    """Trim + collapse fullwidth spaces + strip trailing punctuation repeatedly."""
    if not isinstance(text, str):
        return ""
    text = text.replace("\u3000", " ").replace("\u200b", "")
    text = text.strip()
    while text and text[-1] in TRAILING_PUNCT:
        text = text[:-1].rstrip()
    return re.sub(r"\s+", " ", text).strip()


def parse(text: str) -> Command:
    normalized = normalize(text)
    if not normalized:
        return Command("empty", "", text or "")
    if BARE_URL_RE.match(normalized):
        return Command("bare_url", normalized, text)
    parts = normalized.split(" ", 1)
    head = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    verb = VERBS.get(head) or VERBS.get(parts[0]) or "unknown"
    return Command(verb, arg, text)


def validate_url(url: str) -> bool:
    return bool(HTTPS_URL_RE.match(url or ""))


def validate_candidate_id(candidate_id: str) -> bool:
    return bool(candidate_id) and len(candidate_id) <= 200 and bool(CANDIDATE_ID_RE.match(candidate_id))


def validate_short_id(short: str):
    """'#p042' / 'p042' / '042' -> int, else None."""
    match = SHORT_ID_RE.match(normalize(short))
    return int(match.group(1)) if match else None


def validate_confirm_code(code: str) -> bool:
    return bool(CONFIRM_CODE_RE.match(normalize(code)))
