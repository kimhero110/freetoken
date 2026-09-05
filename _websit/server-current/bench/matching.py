"""Deterministic semantic matching: normalization + synonym tables.

Replaces naive substring checks so that equivalent answers like
"阿根廷队" / "Argentina" or "16.7%" / "1/6" or "6只鸡和4只兔" all judge
correctly -- without any LLM involvement.
"""

import re
import unicodedata

_CN_DIGIT = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

_CN_FRACTIONS = {
    "二分之一": "1/2", "三分之一": "1/3", "四分之一": "1/4",
    "五分之一": "1/5", "六分之一": "1/6", "七分之一": "1/7",
    "八分之一": "1/8", "九分之一": "1/9", "十分之一": "1/10",
    "七分之九": "9/9", "三分之二": "2/3", "九分之七": "7/9",
}
_CN_FRACTIONS["七分之九"] = "7/9"

_NUM_KEEP = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff/%.+\-]")
_TXT_KEEP = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]")
_NUM_FIND = re.compile(r"(?<![0-9.])(\d+(?:\.\d+)?)(?![0-9])")


def _cn_frac(text):
    for k, v in _CN_FRACTIONS.items():
        text = text.replace(k, v)
    return text


def norm_num(text):
    """Keep numbers/operators; for numeric scanning."""
    s = unicodedata.normalize("NFKC", text or "")
    s = s.replace("×", "*").replace("÷", "/").replace("／", "/")
    s = _cn_frac(s)
    s = re.sub(r"\s+", "", s)
    return s.lower()


def norm_text(text):
    """Aggressive normalization for text synonyms (punct stripped)."""
    s = unicodedata.normalize("NFKC", text or "")
    s = s.replace("×", "*").replace("÷", "/")
    s = _cn_frac(s)
    s = re.sub(r"\s+", "", s)
    return _TXT_KEEP.sub("", s).lower()


def numbers_in(text):
    return [float(m.group(1)) for m in _NUM_FIND.finditer(norm_num(text))]


def has_standalone_number(text, value, tol=0.0):
    """True if `value` appears as a standalone number (no 60-in-160 false hit)."""
    for n in numbers_in(text):
        if abs(n - value) <= max(tol, 1e-9):
            return True
    return False


def match_fraction(text, num, den):
    """7/9 == '7/9' == '0.78' == '78%' == '七分之九'."""
    target = num / float(den)
    if ("%d/%d" % (num, den)) in norm_num(text):
        return True
    for n in numbers_in(text):
        if abs(n - target) <= 0.006:
            return True
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%", text or ""):
        if abs(float(m.group(1)) / 100.0 - target) <= 0.006:
            return True
    return False


def match_jitui(text, ji, tu):
    """'鸡6兔4' / '鸡：6只，兔：4只' / '有6只鸡和4只兔' all match."""
    s = norm_num(text)
    pat_ji = re.search(r"鸡[^0-9]{0,6}%d|%d[^0-9]{0,4}鸡" % (ji, ji), s)
    pat_tu = re.search(r"兔[^0-9]{0,6}%d|%d[^0-9]{0,4}兔" % (tu, tu), s)
    return bool(pat_ji and pat_tu)


def match_text(text, variants):
    """Substring match on aggressively normalized text (CJK/ASCII kept)."""
    hay = norm_text(text)
    return any(norm_text(v) in hay for v in variants)


def check(text, specs):
    """specs: list of tuples. ('text',[variants]) / ('num',v[,tol]) /
    ('frac',n,d) / ('jitui',ji,tu). True if ANY spec matches."""
    for spec in specs:
        kind = spec[0]
        if kind == "text":
            if match_text(text, spec[1]):
                return True
        elif kind == "num":
            tol = spec[2] if len(spec) > 2 else 0.0
            if has_standalone_number(text, spec[1], tol):
                return True
        elif kind == "frac":
            if match_fraction(text, spec[1], spec[2]):
                return True
        elif kind == "jitui":
            if match_jitui(text, spec[1], spec[2]):
                return True
    return False

