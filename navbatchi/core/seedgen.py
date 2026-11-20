"""Demo stock and prices, generated from the catalog and always relative to "now".

A 32-bit FNV-1a hash of "<pharmacy>:<medicine>" decides whether a pharmacy carries a product, how many packs it
has and its price (85-125 % of the catalog price, rounded to 100 so'm). The JS port produces the same rows, so
the bot, the Mini App and the browser demo all show the same city.
"""

from __future__ import annotations

FNV_OFFSET = 0x811C9DC5
FNV_PRIME = 0x01000193
# A few rows are pinned so the guided demo story always has a night-time pharmacy with paracetamol in stock.
PINNED = {(2, "paracetamol-500"): (4, 112), (1, "paracetamol-500"): (12, 124)}


def h32(text: str) -> int:
    h = FNV_OFFSET
    for b in text.encode("utf-8"):
        h ^= b
        h = (h * FNV_PRIME) & 0xFFFFFFFF
    return h


def round100(n: int) -> int:
    return (n + 50) // 100 * 100


def stock_row(pharmacy_id: int, med: dict, now_ms: int) -> dict | None:
    r = h32(f"{pharmacy_id}:{med['id']}")
    bucket = r % 100
    pinned = PINNED.get((pharmacy_id, med["id"]))
    if pinned is None and bucket < 15:
        return None  # this pharmacy does not carry it
    qty = 0 if bucket < 22 else 1 + (r >> 8) % 30
    pct = 85 + (r >> 16) % 41
    if pinned is not None:
        qty, pct = pinned
    minutes = 5 + (r >> 3) % 300
    updated = (now_ms // 60_000 - minutes) * 60_000
    return {"pharmacy_id": pharmacy_id, "med_id": med["id"], "qty": qty,
            "price": round100(med["price"] * pct // 100), "updated_ms": updated}


def stock_rows(pharmacies: list[dict], meds: list[dict], now_ms: int) -> list[dict]:
    rows = []
    for ph in pharmacies:
        for med in meds:
            row = stock_row(ph["id"], med, now_ms)
            if row is not None:
                rows.append(row)
    return rows
