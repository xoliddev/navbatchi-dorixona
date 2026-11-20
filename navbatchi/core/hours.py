"""Opening hours in Tashkent time (UTC+5 all year: Uzbekistan has no daylight saving time since 1992).

A schedule is ``"24/7"`` or ``"HH:MM-HH:MM"`` plus weekly days off (0 = Monday ... 6 = Sunday). A closing time at
or before the opening time means the pharmacy works past midnight ("08:00-02:00"); "24:00" is midnight.
"""

from __future__ import annotations

import re

TZ_OFFSET_MS = 5 * 3_600_000
DAY_MS = 86_400_000
_SPAN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-4]):([0-5]\d)$")


class HoursError(ValueError):
    pass


def parse(spec: str) -> tuple[int, int] | None:
    """``"08:00-22:00"`` -> (480, 1320) minutes; ``"24/7"`` -> None."""
    spec = (spec or "").strip()
    if spec == "24/7":
        return None
    m = _SPAN.match(spec)
    if not m:
        raise HoursError(spec)
    start = int(m.group(1)) * 60 + int(m.group(2))
    end = int(m.group(3)) * 60 + int(m.group(4))
    if end > 1440 or (start == end % 1440 and end != 1440):
        raise HoursError(spec)
    return start, end


def local_parts(now_ms: int) -> tuple[int, int, int]:
    """UTC milliseconds -> (days since epoch, weekday 0=Mon, minute of day) in Tashkent."""
    local = now_ms + TZ_OFFSET_MS
    day = local // DAY_MS
    minute = (local % DAY_MS) // 60_000
    return day, (day + 3) % 7, minute  # 1970-01-01 was a Thursday


def hhmm(minute: int) -> str:
    minute %= 1440
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _open_at(span: tuple[int, int], off: list[int], weekday: int, minute: int) -> bool:
    start, end = span
    if end > start:  # same day
        return weekday not in off and start <= minute < end
    yesterday = (weekday + 6) % 7
    return (weekday not in off and minute >= start) or (yesterday not in off and minute < end)


def status(spec: str, off: list[int] | None, now_ms: int) -> dict:
    """{"open", "h24", "until"} when open, {"open", "h24", "opens", "day"} when closed (day: 0 today, 1 tomorrow...)."""
    off = list(off or [])
    span = parse(spec)
    if span is None:
        return {"open": True, "h24": True}
    _, weekday, minute = local_parts(now_ms)
    start, end = span
    if _open_at(span, off, weekday, minute):
        return {"open": True, "h24": False, "until": "24:00" if end == 1440 else hhmm(end)}
    for ahead in range(0, 8):
        wd = (weekday + ahead) % 7
        if wd in off:
            continue
        if ahead > 0 or minute < start:
            return {"open": False, "h24": False, "opens": hhmm(start), "day": ahead}
    return {"open": False, "h24": False, "opens": hhmm(start), "day": 7}


def open_now(spec: str, off: list[int] | None, now_ms: int) -> bool:
    return status(spec, off, now_ms)["open"]
