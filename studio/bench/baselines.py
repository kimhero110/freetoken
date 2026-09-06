"""Reference baselines & thresholds. Versioned for objectivity.

All numbers are preloaded reference data (BASELINE_VERSION), not real-time
official sampling. Thresholds are rule-based and surfaced to users on /criteria.
"""

BASELINE_VERSION = "2026-09-v1"

DIMENSIONS = [
    ("authenticity", "真实性", 0.30),
    ("capability", "能力", 0.25),
    ("performance", "性能", 0.20),
    ("stability", "稳定性", 0.15),
    ("compliance", "合规", 0.10),
]

FAMILY_PATTERNS = [
    ("openai", r"gpt|o1|o3|o4|davinci|text-embedding"),
    ("anthropic", r"claude"),
    ("deepseek", r"deepseek"),
    ("qwen", r"qwen|qwq|通义"),
    ("gemini", r"gemini"),
    ("glm", r"glm|chatglm|智谱"),
    ("moonshot", r"moonshot|kimi"),
    ("doubao", r"doubao|豆包"),
    ("ernie", r"ernie|文心"),
    ("hunyuan", r"hunyuan|混元"),
    ("grok", r"grok"),
    ("meta", r"llama"),
    ("mistral", r"mistral|mixtral"),
    ("minimax", r"minimax|abab"),
]

FLAGSHIP_PAT = r"opus|4\.1|gpt-4(?!o-mini)|gpt-5|gpt-4o(?!-mini)|o1|o3|o4|ultra|(-max$)|max$|deepseek-r|deepseek-reasoner|70b|405b|pro(?!.*flash)|exp"
MINI_PAT = r"mini|nano|tiny|small|lite|haiku|flash|turbo|8b|7b|4b|3b|2b|1\.5b|1\.8b|micro|air"

TOKENIZER_ZH_PER_CHAR = {
    "openai": (0.60, 0.85),
    "anthropic": (0.55, 0.82),
    "gemini": (0.55, 0.82),
    "deepseek": (0.44, 0.62),
    "qwen": (0.46, 0.64),
    "glm": (0.46, 0.66),
    "moonshot": (0.46, 0.66),
    "meta": (0.60, 0.90),
    "mistral": (0.60, 0.90),
}
TOKENIZER_ASCII_PER_CHAR = (0.18, 0.34)

TTFT_P50_GOOD_MS = 1500
TTFT_P50_WARN_MS = 4000

TIER_LADDER_LINE = {"flagship": 7, "mid": 5, "mini": 3}
TIER_LADDER_DESC = {
    "flagship": "旗舰档参考线：≥7/8",
    "mid": "中档参考线：≥5/8",
    "mini": "轻量档参考线：≥3/8",
    "unknown": "未知档位，按中档参考线：≥5/8",
}

CONCURRENCY_WORKERS = 8
CONCURRENCY_P95_GOOD_S = 8
CONCURRENCY_P95_WARN_S = 15
CONCURRENCY_ERR_WARN = 0.10
CONCURRENCY_ERR_FAIL = 0.20

THROTTLE_RATIO_GOOD = 0.50
THROTTLE_RATIO_WARN = 0.30

COMPLIANCE_REFUSAL_GOOD = 0.25
COMPLIANCE_REFUSAL_WARN = 0.50

KNOWLEDGE_FAKE_EVENT = "2026年3月OpenAI发布的GPT-6.5 Turbo"
KNOWLEDGE_DATED = [
    ("2022年卡塔尔世界杯的冠军是哪支球队？", "阿根廷"),
    ("iPhone 15 系列改用了什么充电接口？", "USB-C"),
    ("2024年美国总统大选的当选者是谁？", "特朗普"),
    ("《三体》的作者是谁？", "刘慈欣"),
    ("光在真空中的速度大约是多少公里每秒？", "30万"),
]

VERDICT_TEXT = {
    "pass": "通过",
    "warn": "可疑",
    "fail": "未通过",
    "info": "参考",
}


def guess_family(model: str) -> str:
    import re
    m = (model or "").lower()
    for fam, pat in FAMILY_PATTERNS:
        if re.search(pat, m):
            return fam
    return "unknown"


def guess_tier(model: str) -> str:
    import re
    m = (model or "").lower()
    if re.search(MINI_PAT, m):
        return "mini"
    if re.search(FLAGSHIP_PAT, m):
        return "flagship"
    if "gpt" in m or "claude" in m or "gemini" in m:
        return "mid"
    return "mid"
