"""Small shared pieces: the refusal error and input cleaning."""

from __future__ import annotations

import re

_CONTROL = re.compile(r"[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")
LANGS = ("uz", "ru")


class Refused(Exception):
    """An action that is not allowed; ``code`` maps to an ``err.<code>`` text."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def clean_text(text: object, limit: int) -> str:
    """Drop control and bidi characters, squeeze spaces, cut to ``limit`` characters."""
    return " ".join(_CONTROL.sub(" ", str(text or "")).split())[:limit]


def norm_lang(code: str | None) -> str:
    return "ru" if code and code[:2].lower() == "ru" else "uz"
