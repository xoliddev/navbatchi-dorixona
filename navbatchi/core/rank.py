"""Rank pharmacies for one medicine: the nearest, the cheapest and the "best choice" between them.

The slider ``weight`` goes from 0 (only distance matters) to 100 (only price matters). Both distance and price are
scaled to 0..1000 over the candidates, so the score is a whole number and the JS port gives the same order.
"""

from __future__ import annotations

from .geo import haversine_m
from .hours import status

DEFAULT_WEIGHT = 50
MAX_RESULTS = 30


def rank(offers: list[dict], lat: float, lon: float, now_ms: int, weight: int = DEFAULT_WEIGHT,
         open_only: bool = False, max_m: int | None = None, limit: int = MAX_RESULTS) -> dict:
    """``offers``: [{"pharmacy_id", "price", "available", "lat", "lon", "hours", "off"}].

    Returns {"items": [...best first], "nearest", "cheapest", "best"} (pharmacy ids, None when empty). Items get
    ``dist`` (metres), ``score`` (0..1000, lower is better) and ``hours`` status. Out-of-stock offers are dropped,
    and so are closed pharmacies when ``open_only`` (the "navbatchi" filter).
    """
    weight = max(0, min(100, int(weight)))
    items = []
    for o in offers:
        if o["available"] <= 0:
            continue
        st = status(o["hours"], o.get("off"), now_ms)
        if open_only and not st["open"]:
            continue
        dist = haversine_m(lat, lon, o["lat"], o["lon"])
        if max_m is not None and dist > max_m:
            continue
        items.append({**o, "dist": dist, "status": st})
    if not items:
        return {"items": [], "nearest": None, "cheapest": None, "best": None}
    max_d = max(i["dist"] for i in items)
    min_p = min(i["price"] for i in items)
    span = max(i["price"] for i in items) - min_p
    for i in items:
        d_part = i["dist"] * 1000 // max_d if max_d else 0
        p_part = (i["price"] - min_p) * 1000 // span if span else 0
        i["score"] = ((100 - weight) * d_part + weight * p_part) // 100
    nearest = min(items, key=lambda i: (i["dist"], i["price"], i["pharmacy_id"]))
    cheapest = min(items, key=lambda i: (i["price"], i["dist"], i["pharmacy_id"]))
    items.sort(key=lambda i: (i["score"], i["dist"], i["price"], i["pharmacy_id"]))
    return {"items": items[:limit], "nearest": nearest["pharmacy_id"], "cheapest": cheapest["pharmacy_id"],
            "best": items[0]["pharmacy_id"]}
