"""Numbers to words for the local Amharic and Afaan Oromoo voices (Phase U6).

The MMS text-to-speech voices have no digits in their alphabet: fed "76%",
they would silently say nothing for the figure. Every number is therefore
spelled out in the target language before synthesis, value for value
(CLAUDE.md doctrine 1: the spoken answer must carry the model's numbers).

Covers what the advisor's answers contain: integers up to 999 999, thousands
separators, decimals (read digit by digit after the point), percentages, and
the units mm, m and °C. Wording is a machine draft for native review.
"""
from __future__ import annotations

import re
from typing import Literal

Lang = Literal["am", "om"]

# --------------------------------------------------------------------- Amharic
_AM_UNITS = ["ዜሮ", "አንድ", "ሁለት", "ሦስት", "አራት", "አምስት", "ስድስት", "ሰባት", "ስምንት", "ዘጠኝ"]
_AM_TENS = {10: "አሥር", 20: "ሃያ", 30: "ሠላሳ", 40: "አርባ", 50: "ሃምሳ", 60: "ስልሳ", 70: "ሰባ", 80: "ሰማንያ", 90: "ዘጠና"}


def _am_below_100(n: int) -> str:
    if n < 10:
        return _AM_UNITS[n]
    if n < 20:
        return "አሥር" if n == 10 else f"አሥራ {_AM_UNITS[n - 10]}"
    tens, unit = divmod(n, 10)
    return _AM_TENS[tens * 10] + (f" {_AM_UNITS[unit]}" if unit else "")


def _am_below_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts: list[str] = []
    if hundreds:
        parts.append("መቶ" if hundreds == 1 else f"{_AM_UNITS[hundreds]} መቶ")
    if rest or not parts:
        parts.append(_am_below_100(rest))
    return " ".join(parts)


def _am_int(n: int) -> str:
    thousands, rest = divmod(n, 1000)
    parts: list[str] = []
    if thousands:
        parts.append(f"{_am_below_1000(thousands)} ሺህ")
    if rest or not parts:
        parts.append(_am_below_1000(rest))
    return " ".join(parts)


# ---------------------------------------------------------------- Afaan Oromoo
_OM_UNITS = ["duwwaa", "tokko", "lama", "sadii", "afur", "shan", "jaha", "torba", "saddeet", "sagal"]
_OM_TENS = {20: "digdama", 30: "soddoma", 40: "afurtama", 50: "shantama", 60: "jaatama",
            70: "torbaatama", 80: "saddeettama", 90: "sagaltama"}


def _om_below_100(n: int) -> str:
    if n < 10:
        return _OM_UNITS[n]
    if n < 20:
        return "kudhan" if n == 10 else f"kudha {_OM_UNITS[n - 10]}"
    tens, unit = divmod(n, 10)
    word = _OM_TENS[tens * 10]
    # Joining form: the final -a becomes -ii (digdama -> digdamii tokko).
    return f"{word[:-1]}ii {_OM_UNITS[unit]}" if unit else word


def _om_below_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts: list[str] = []
    if hundreds:
        parts.append("dhibba tokko" if hundreds == 1 else f"dhibba {_OM_UNITS[hundreds]}")
    if rest or not parts:
        parts.append(_om_below_100(rest))
    return " fi ".join(parts)


def _om_int(n: int) -> str:
    thousands, rest = divmod(n, 1000)
    parts: list[str] = []
    if thousands:
        parts.append(f"kuma {_om_below_1000(thousands)}")
    if rest or not parts:
        parts.append(_om_below_1000(rest))
    return " fi ".join(parts)


# ----------------------------------------------------------------------- shared
_WORDS = {
    "am": {"int": _am_int, "digit": _AM_UNITS, "point": "ነጥብ", "minus": "አሉታዊ",
           "percent": "{n} በመቶ", "mm": "ሚሊ ሜትር", "m": "ሜትር", "c": "ዲግሪ ሴልሺየስ"},
    "om": {"int": _om_int, "digit": _OM_UNITS, "point": "tuqaa", "minus": "hir'ina",
           "percent": "dhibbeentaa {n}", "mm": "milimeetira", "m": "meetira", "c": "digirii selsiyesii"},
}

_NUMBER = re.compile(
    # Oromo also writes the percent sign first ("%76").
    r"(?P<pre>%\s*)?"
    # A sign only where it cannot be a hyphen ("8-10" is a range, not minus ten).
    r"(?:(?<![\w)])(?P<sign>[-−]))?(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<frac>\d+))?"
    r"(?:\s*(?P<unit>%|°\s*C|mm\b|m\b|ሚሜ|ሜ(?![ሀ-፿])))?"
)


def number_words(value: str, lang: Lang) -> str:
    """One number as words: '1,416' -> words for 1416; '2.34' -> two point three four."""
    w = _WORDS[lang]
    whole, _, frac = value.replace(",", "").partition(".")
    n = int(whole)
    out = w["int"](n) if n < 1_000_000 else " ".join(w["digit"][int(d)] for d in whole)
    if frac:
        out += f" {w['point']} " + " ".join(w["digit"][int(d)] for d in frac)
    return out


def verbalize(text: str, lang: Lang) -> str:
    """Replace every number (with its %, mm, m or °C) by words in ``lang``."""
    w = _WORDS[lang]

    def repl(m: re.Match[str]) -> str:
        value = m.group("int") + (f".{m.group('frac')}" if m.group("frac") else "")
        words = number_words(value, lang)
        if m.group("sign"):
            words = f"{w['minus']} {words}"
        unit = (m.group("unit") or "").replace(" ", "")
        unit = {"ሚሜ": "mm", "ሜ": "m"}.get(unit, unit)
        if unit == "%" or m.group("pre"):
            return w["percent"].format(n=words)
        if unit == "°C":
            return f"{words} {w['c']}"
        if unit in ("mm", "m"):
            return f"{words} {w[unit]}"
        return words

    out = _NUMBER.sub(repl, text.replace("~", ""))
    return re.sub(r"\s{2,}", " ", out).strip()
