"""Reservation (bron) rules: how much, for how long, and which status changes are allowed.

The database enforces the stock part atomically; these rules decide what to ask it for.
"""

from __future__ import annotations

import re

HOLD_MINUTES = 120
MAX_QTY = 5
MAX_ACTIVE_PER_USER = 3
CODE_RE = re.compile(r"^[0-9]{6}$")
STATUSES = ("held", "picked", "cancelled", "expired")
_MOVES = {("held", "confirm"): "picked", ("held", "cancel"): "cancelled", ("held", "expire"): "expired"}


class ReserveError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def check(rx: bool, qty: int, available: int, active: int = 0) -> None:
    """Raise ReserveError("rx" | "qty" | "stock" | "too_many") when the reservation is not allowed."""
    if rx:
        raise ReserveError("rx")
    if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1 or qty > MAX_QTY:
        raise ReserveError("qty")
    if active >= MAX_ACTIVE_PER_USER:
        raise ReserveError("too_many")
    if available < qty:
        raise ReserveError("stock")


def make_code(n: int) -> str:
    """A random integer -> 6-digit pickup code (leading zeros kept)."""
    return f"{n % 1_000_000:06d}"


def clean_code(text: object) -> str | None:
    """What the pharmacist typed -> a 6-digit code, or None. Spaces and dashes are forgiven: "482 913"."""
    s = re.sub(r"[\s-]", "", str(text or ""))[:12]
    return s if CODE_RE.match(s) else None


def expires_at(created_ms: int) -> int:
    return created_ms + HOLD_MINUTES * 60_000


def minutes_left(expires_ms: int, now_ms: int) -> int:
    """Whole minutes until expiry, rounded up; 0 once expired."""
    left = expires_ms - now_ms
    return 0 if left <= 0 else -(-left // 60_000)


def move(status: str, action: str) -> str:
    """held --confirm--> picked, --cancel--> cancelled, --expire--> expired. Anything else is refused."""
    try:
        return _MOVES[(status, action)]
    except KeyError:
        raise ReserveError("state") from None
