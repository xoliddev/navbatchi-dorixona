"""Price alerts: "tell me when X is in stock within N km" or "... under P so'm".

An alert fires once. The scheduler claims it atomically before sending, so a restart never sends it twice.
"""

from __future__ import annotations

from .geo import haversine_m

RADII_KM = (1, 3, 5, 10)
MAX_ALERTS_PER_USER = 5


def match(alert: dict, offers: list[dict]) -> dict | None:
    """The cheapest offer that satisfies the alert (then the nearest), or None.

    ``alert``: {"lat", "lon", "radius_m", "max_price" (None = any price)}; ``offers`` as in rank.rank().
    """
    best = None
    for o in offers:
        if o["available"] <= 0:
            continue
        if alert.get("max_price") is not None and o["price"] > alert["max_price"]:
            continue
        dist = haversine_m(alert["lat"], alert["lon"], o["lat"], o["lon"])
        if dist > alert["radius_m"]:
            continue
        key = (o["price"], dist, o["pharmacy_id"])
        if best is None or key < best[0]:
            best = (key, {"pharmacy_id": o["pharmacy_id"], "price": o["price"], "dist": dist})
    return best[1] if best else None
