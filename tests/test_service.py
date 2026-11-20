"""Service rules: offers, reservations, expiry, pharmacist and admin actions, alerts, invites."""

from __future__ import annotations

import pytest

from navbatchi import scheduler
from navbatchi.service import Refused

from .helpers import ADMIN, ALI, CENTRE, DILNOZA, OYBEK, VALI, service_env, stock

PARA = "paracetamol-500"


async def test_offers_show_nearest_cheapest_and_analogs():
    async with service_env() as (svc, clock):
        res = await svc.offers(PARA, *CENTRE, weight=50)
        assert (res["nearest"], res["cheapest"]) == (1, 12)
        assert res["items"][0]["pharmacy_id"] == res["best"]
        brand = await svc.offers("febrinol-500", *CENTRE)
        assert brand["analogs"] and brand["analogs"][0]["id"] == PARA  # the cheaper generic is offered
        clock.set_local(3)  # 03:00: only the 24/7 pharmacies are open
        night = await svc.offers(PARA, *CENTRE, open_only=True)
        assert 1 not in [i["pharmacy_id"] for i in night["items"]]
        assert all(i["status"]["open"] for i in night["items"])
        assert {2, 6}.issubset({i["pharmacy_id"] for i in night["items"]})
        with pytest.raises(Refused, match="location"):
            await svc.offers(PARA, 91, 0)
        with pytest.raises(Refused, match="not_found"):
            await svc.offers("no-such-med", *CENTRE)


async def test_reserve_confirm_decrements_stock():
    async with service_env() as (svc, _):
        before = await stock(svc, 2, PARA)
        res = await svc.reserve(ALI, 2, PARA, 2)
        assert res["status"] == "held" and len(res["code"]) == 6 and res["code"].isdigit()
        assert res["expires_at"] - res["created_at"] == 120 * 60_000
        assert (await stock(svc, 2, PARA))["reserved"] == 2
        done = await svc.confirm_code(DILNOZA, f"{res['code'][:3]} {res['code'][3:]}")
        assert done["status"] == "picked" and done["done_by"] == DILNOZA
        after = await stock(svc, 2, PARA)
        assert (after["qty"], after["reserved"]) == (before["qty"] - 2, 0)
        with pytest.raises(Refused, match="code_not_found"):
            await svc.confirm_code(DILNOZA, res["code"])  # a code works once


async def test_reservation_rules():
    async with service_env() as (svc, _):
        with pytest.raises(Refused, match="rx"):
            await svc.reserve(ALI, 2, "amoxicillin-500", 1)
        with pytest.raises(Refused, match="qty"):
            await svc.reserve(ALI, 2, PARA, 6)
        with pytest.raises(Refused, match="stock"):
            await svc.reserve(ALI, 2, PARA, 5)  # only 4 on the shelf
        with pytest.raises(Refused, match="not_found"):
            await svc.reserve(ALI, 999, PARA, 1)
        for _ in range(3):
            await svc.reserve(ALI, 6, PARA, 1)
        with pytest.raises(Refused, match="too_many"):
            await svc.reserve(ALI, 6, PARA, 1)
        mine = await svc.my_reservations(ALI)
        with pytest.raises(Refused, match="not_found"):
            await svc.cancel(VALI, mine[0]["id"])  # not his
        cancelled = await svc.cancel(ALI, mine[0]["id"])
        assert cancelled["status"] == "cancelled"
        with pytest.raises(Refused, match="state"):
            await svc.cancel(ALI, mine[0]["id"])


async def test_expiry_releases_stock_once():
    async with service_env() as (svc, clock):
        res = await svc.reserve(ALI, 2, PARA, 3)
        clock.skip(minutes=119)
        assert await svc.expire_due() == []
        clock.skip(minutes=1)
        with pytest.raises(Refused, match="code_expired"):
            await svc.confirm_code(DILNOZA, res["code"])
        expired = await svc.expire_due()
        assert [r["id"] for r in expired] == [res["id"]]
        assert await svc.expire_due() == []  # idempotent
        row = await stock(svc, 2, PARA)
        assert (row["qty"], row["reserved"]) == (4, 0)
        assert (await svc.reservation(res["id"]))["status"] == "expired"


async def test_pharmacist_only_touches_own_pharmacy():
    async with service_env() as (svc, _):
        res = await svc.reserve(ALI, 2, PARA, 1)
        with pytest.raises(Refused, match="code_not_found"):
            await svc.confirm_code(OYBEK, res["code"])  # pharmacy 6 cannot hand out pharmacy 2's packs
        await svc.set_stock(OYBEK, PARA, 50, "3 900")
        assert (await stock(svc, 6, PARA))["qty"] == 50
        assert (await stock(svc, 2, PARA))["qty"] == 4
        assert {r["pharmacy_id"] for r in await svc.stock_list(OYBEK)} == {6}
        assert await svc.pharm_reservations(OYBEK) == []
        for call in (svc.stock_list(ALI), svc.set_stock(ALI, PARA, 1, 1000), svc.confirm_code(ALI, res["code"]),
                     svc.pharm_reservations(ALI), svc.export_csv(ALI), svc.import_csv(ALI, b"med,price,qty\n")):
            with pytest.raises(Refused, match="forbidden"):
                await call
        with pytest.raises(Refused, match="below_reserved"):
            await svc.set_stock(DILNOZA, PARA, 0, 5000)
        with pytest.raises(Refused, match="stock_value"):
            await svc.set_stock(DILNOZA, PARA, 3, "4.5")


async def test_csv_import_and_export():
    async with service_env() as (svc, _):
        await svc.reserve(ALI, 2, PARA, 2)
        csv = "nomi;narx;soni\nПарацетамол;5 100;1\nIbuprofen;9 900;40\nyo'q dori;100;1\n".encode()
        res = await svc.import_csv(DILNOZA, csv)
        assert res["updated"] == 1
        assert {e["code"] for e in res["errors"]} == {"med", "below_reserved"}
        assert (await stock(svc, 2, "ibuprofen-200"))["price"] == 9900
        with pytest.raises(Refused, match="csv_header"):
            await svc.import_csv(DILNOZA, b"a,b\n1,2\n")
        with pytest.raises(Refused, match="csv_too_big"):
            await svc.import_csv(DILNOZA, b"x" * 70_000)
        out = await svc.export_csv(DILNOZA)
        assert out.startswith("med,name,price,qty,reserved\r\n")
        assert "ibuprofen-200,Ibuprofen,9900,40,0" in out


async def test_invites_and_admin():
    async with service_env() as (svc, clock):
        with pytest.raises(Refused, match="forbidden"):
            await svc.create_invite(ALI, 3)
        token = await svc.create_invite(ADMIN, 3)
        assert (await svc.redeem_invite(VALI, token))["id"] == 3
        assert (await svc.user(VALI))["role"] == "pharmacist"
        with pytest.raises(Refused, match="invite"):
            await svc.redeem_invite(ALI, token)  # single use
        old = await svc.create_invite(ADMIN, 4)
        clock.skip(hours=73)
        with pytest.raises(Refused, match="invite"):
            await svc.redeem_invite(ALI, old)
        with pytest.raises(Refused, match="invite"):
            await svc.redeem_invite(ALI, "'; DROP TABLE users; --")
        pid = await svc.add_pharmacy(ADMIN, "Yangi Dorixona", "Chilonzor, 1-uy", 41.28, 69.21, "09:00-21:00",
                                     "+998 71 000 99 99")
        assert (await svc.pharmacy(pid))["district"] == "chilonzor"
        for bad in (dict(hours="9-21"), dict(phone="call me"), dict(lat=100), dict(name="x")):
            args = {"name": "Yangi", "address": "Chilonzor 1", "lat": 41.28, "lon": 69.21, "hours": "09:00-21:00",
                    "phone": "+998710009999", **bad}
            with pytest.raises(Refused):
                await svc.add_pharmacy(ADMIN, **args)
        with pytest.raises(Refused, match="forbidden"):
            await svc.add_pharmacy(ALI, "X Farm", "Somewhere 1", 41.3, 69.2, "24/7", "+998710000000")


class Notes:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    async def expired(self, res: dict) -> None:
        self.sent.append(("expired", res))

    async def alert(self, alert: dict) -> None:
        self.sent.append(("alert", alert))


async def test_price_alert_fires_once():
    async with service_env() as (svc, clock):
        with pytest.raises(Refused, match="no_location"):
            await svc.add_alert(ADMIN, "salbutamol-100", 3)
        with pytest.raises(Refused, match="price"):
            await svc.add_alert(ALI, "salbutamol-100", 3, "arzon")
        alert = await svc.add_alert(ALI, "loperamide-2", 1, "5 000")
        assert alert["radius_m"] == 1000 and alert["max_price"] == 5000
        notes = Notes()
        await svc.set_stock(DILNOZA, "loperamide-2", 0, 4000)  # pharmacy 2 is 2.2 km away: outside 1 km
        assert (await scheduler.tick(svc, notes))["alerts"] == 0
        pharmacist_1 = 3001
        await svc.touch_user(pharmacist_1, "Kamola", "uz")
        await svc.redeem_invite(pharmacist_1, await svc.create_invite(ADMIN, 1))
        await svc.set_stock(pharmacist_1, "loperamide-2", 5, 5500)  # near, but too expensive
        assert (await scheduler.tick(svc, notes))["alerts"] == 0
        await svc.set_stock(pharmacist_1, "loperamide-2", 5, 4900)
        assert (await scheduler.tick(svc, notes))["alerts"] == 1
        assert notes.sent[-1][1]["pharmacy_id"] == 1 and notes.sent[-1][1]["price"] == 4900
        assert (await scheduler.tick(svc, notes))["alerts"] == 0  # never twice
        assert await svc.my_alerts(ALI) == []
        res = await svc.reserve(VALI, 2, PARA, 1)
        clock.skip(hours=2)
        assert (await scheduler.tick(svc, notes))["expired"] == 1
        assert notes.sent[-1] == ("expired", {**res, "status": "expired"})
