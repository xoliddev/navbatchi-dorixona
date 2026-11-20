"""Distances on the map. Haversine is plenty for a city; results are whole metres."""

from __future__ import annotations

import math

EARTH_M = 6_371_000.0
LAT_RANGE = (-90.0, 90.0)
LON_RANGE = (-180.0, 180.0)
TASHKENT = (41.3111, 69.2797)  # Amir Temur square: the demo's "you are here"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    s1, s2 = math.sin(dp / 2), math.sin(dl / 2)
    a = s1 * s1 + math.cos(p1) * math.cos(p2) * s2 * s2
    return math.floor(2 * EARTH_M * math.asin(min(1.0, math.sqrt(a))) + 0.5)


def valid_point(lat: object, lon: object) -> bool:
    try:
        la, lo = float(lat), float(lon)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return math.isfinite(la) and math.isfinite(lo) and LAT_RANGE[0] <= la <= LAT_RANGE[1] \
        and LON_RANGE[0] <= lo <= LON_RANGE[1]


def nearest_district(lat: float, lon: float, districts: list[dict]) -> str:
    return min(districts, key=lambda d: (haversine_m(lat, lon, d["lat"], d["lon"]), d["id"]))["id"]


def fmt_distance(m: int, lang: str = "uz") -> str:
    """850 -> "850 m"; 1234 -> "1,2 km" (comma decimals, as people write it here)."""
    if m < 1000:
        return f"{m} {'м' if lang == 'ru' else 'm'}"
    tenths = (m + 50) // 100
    return f"{tenths // 10},{tenths % 10} {'км' if lang == 'ru' else 'km'}"
