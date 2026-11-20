"""Money is a whole number of so'm. Floats are never used for prices."""

from __future__ import annotations

import re

MAX_PRICE = 10_000_000  # 10 mln so'm for one pack is already absurd
_DIGITS = re.compile(r"^[0-9]{1,9}$")


class PriceError(ValueError):
    pass


def fmt(n: int) -> str:
    """12500 -> "12 500" (space-separated thousands)."""
    if not isinstance(n, int) or isinstance(n, bool):
        raise PriceError("not an integer")
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    groups = []
    while s:
        groups.append(s[-3:])
        s = s[:-3]
    return sign + " ".join(reversed(groups))


def parse_price(text: object) -> int:
    """ "12 500", "12500", "12 500 so'm" -> 12500. Decimals, signs and zero are refused."""
    if isinstance(text, bool):
        raise PriceError("bool")
    if isinstance(text, int):
        value = text
    else:
        s = str(text or "").strip().lower()
        for suffix in ("so'm", "so‘m", "сум", "som", "sum"):
            if s.endswith(suffix):
                s = s[: -len(suffix)].strip()
        s = s.replace(" ", "").replace("\u00a0", "").replace("\u202f", "")
        if not _DIGITS.match(s):
            raise PriceError("format")
        value = int(s)
    if value < 100 or value > MAX_PRICE:
        raise PriceError("range")
    return value


def parse_qty(text: object, max_qty: int = 100_000) -> int:
    if isinstance(text, bool):
        raise PriceError("bool")
    if isinstance(text, int):
        value = text
    else:
        s = str(text or "").strip().replace(" ", "")
        if not re.fullmatch(r"[0-9]{1,6}", s):
            raise PriceError("qty")
        value = int(s)
    if value < 0 or value > max_qty:
        raise PriceError("qty")
    return value
