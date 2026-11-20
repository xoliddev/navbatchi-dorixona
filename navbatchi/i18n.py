"""Texts for the bot, read from shared/locales/*.json (the Mini App and the browser demo read the same files),
plus the small formatters every screen needs: prices, distances, opening state, "updated 5 min ago"."""

from __future__ import annotations

import html
import json
import re
from functools import cache
from pathlib import Path

from .common import norm_lang
from .core.geo import fmt_distance
from .core.hours import TZ_OFFSET_MS, hhmm
from .core.money import fmt

LOCALE_DIR = Path(__file__).resolve().parent.parent / "shared" / "locales"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


class Raw(str):
    """A parameter that is already safe HTML (for example a nested, already-rendered text)."""


@cache
def catalog(lang: str) -> dict[str, str]:
    with open(LOCALE_DIR / f"{lang}.json", encoding="utf-8") as fh:
        return json.load(fh)


def render(template: str, params: dict) -> str:
    def sub(m: re.Match) -> str:
        if m.group(1) not in params:
            return m.group(0)
        value = params[m.group(1)]
        return value if isinstance(value, Raw) else html.escape(str(value), quote=False)

    return _PLACEHOLDER.sub(sub, template)


def t(lang: str, key: str, **params: object) -> str:
    """Localized text; parameters are HTML-escaped unless wrapped in ``Raw``."""
    lang = norm_lang(lang)
    template = catalog(lang).get(key) or catalog("uz").get(key) or key
    return render(template, params)


def plain(text: str) -> str:
    """For callback alerts, which show plain text."""
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def price(n: int) -> str:
    return fmt(n)


def dist(lang: str, m: int) -> str:
    return fmt_distance(m, lang)


def clock(ms: int) -> str:
    """UTC milliseconds -> "HH:MM" in Tashkent."""
    return hhmm(((ms + TZ_OFFSET_MS) // 60_000) % 1440)


def open_text(lang: str, st: dict) -> str:
    if st["open"]:
        return t(lang, "open.h24") if st["h24"] else t(lang, "open.until", time=st["until"])
    if st["day"] == 0:
        return t(lang, "open.opens_today", time=st["opens"])
    if st["day"] == 1:
        return t(lang, "open.opens_tomorrow", time=st["opens"])
    return t(lang, "open.opens_later", n=st["day"], time=st["opens"])


def ago(lang: str, then_ms: int, now_ms: int) -> str:
    minutes = max(0, (now_ms - then_ms) // 60_000)
    if minutes < 1:
        return t(lang, "ago.now")
    if minutes < 60:
        return t(lang, "ago.min", n=minutes)
    if minutes < 1440:
        return t(lang, "ago.hour", n=minutes // 60)
    return t(lang, "ago.day", n=minutes // 1440)


def stock_level(lang: str, n: int) -> str:
    if n <= 0:
        return t(lang, "stock.none")
    if n <= 3:
        return t(lang, "stock.few", n=n)
    return t(lang, "stock.some" if n < 20 else "stock.many", n=n)


def hours_text(lang: str, spec: str) -> str:
    return t(lang, "open.h24") if spec == "24/7" else spec
