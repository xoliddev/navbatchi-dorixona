"""The seeded city is relative to "now": 30 consecutive days across New Year all give a usable, consistent city."""

from __future__ import annotations

from navbatchi.core.hours import status

from .helpers import CENTRE, Clock, service_env

DAY = 86_400_000
DEC_17_NOON = 1_797_490_800_000  # 2026-12-17 12:00 in Tashkent


async def test_thirty_days_across_new_year():
    counts = set()
    for d in range(30):
        clock = Clock(DEC_17_NOON + d * DAY)
        async with service_env(clock) as (svc, _):
            rows = await svc.db.all("SELECT * FROM stock")
            counts.add(len(rows))
            assert all(0 < clock() - r["updated_at"] <= 305 * 60_000 for r in rows)
            assert all(r["reserved"] == 0 and r["qty"] >= 0 and r["price"] % 100 == 0 for r in rows)
            day = await svc.offers("paracetamol-500", *CENTRE)
            assert day["nearest"] == 1 and day["cheapest"] == 12
            clock.set_local(3)
            night = await svc.offers("paracetamol-500", *CENTRE, open_only=True)
            assert night["items"] and all(i["status"]["open"] for i in night["items"])
            res = await svc.reserve(1001, 2, "paracetamol-500", 2)
            assert (await svc.confirm_code(2002, res["code"]))["status"] == "picked"
    assert len(counts) == 1


def test_new_year_midnight_is_tashkent_midnight():
    new_year = 1_798_743_600_000  # 2027-01-01 00:00 in Tashkent = 2026-12-31 19:00 UTC
    assert status("08:00-24:00", [], new_year - 60_000)["open"]
    assert not status("08:00-24:00", [], new_year)["open"]
    assert status("08:00-02:00", [], new_year + 60 * 60_000) == {"open": True, "h24": False, "until": "02:00"}
