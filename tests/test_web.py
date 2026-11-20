"""Mini App API: initData HMAC + freshness, roles on every route, own-pharmacy only, validation, rate limits."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from aiohttp.test_utils import TestClient, TestServer

from navbatchi.security import sign_init_data
from navbatchi.web import make_app

from .helpers import ADMIN, ALI, CENTRE, DILNOZA, OYBEK, VALI, service_env, stock

TOKEN = "123456:TEST-ONLY-NOT-A-REAL-TOKEN"
PARA = "paracetamol-500"


def init_data(uid: int, clock, age: int = 0, token: str = TOKEN) -> str:
    fields = {"auth_date": str(clock() // 1000 - age), "query_id": "AAE-test",
              "user": json.dumps({"id": uid, "first_name": f"U{uid}", "language_code": "uz"})}
    return sign_init_data(fields, token)


@asynccontextmanager
async def api(rate: int = 1000):
    async with service_env() as (svc, clock):
        app = make_app(svc, TOKEN, notifier=None, max_age=3600, rate_per_minute=rate, bot_username="test_bot")
        client = TestClient(TestServer(app))
        await client.start_server()

        def h(uid: int, age: int = 0) -> dict:
            return {"Authorization": "tma " + init_data(uid, clock, age)}

        try:
            yield client, svc, clock, h
        finally:
            await client.close()


async def test_initdata_signature_and_freshness():
    async with api() as (client, _, clock, h):
        assert (await client.get("/api/me")).status == 401
        assert (await client.get("/api/me", headers={"Authorization": "tma hash=00"})).status == 401
        assert (await client.get("/api/me", headers=h(ALI, age=7200))).status == 401  # expired
        assert (await client.get("/api/me", headers=h(ALI, age=-600))).status == 401  # from the future
        forged = init_data(ALI, clock, token="999:ANOTHER-BOT")
        assert (await client.get("/api/me", headers={"Authorization": "tma " + forged})).status == 401
        tampered = init_data(ALI, clock).replace("1001", "1002")
        assert (await client.get("/api/me", headers={"Authorization": "tma " + tampered})).status == 401
        r = await client.get("/api/me", headers=h(ALI))
        assert r.status == 200
        body = await r.json()
        assert body["role"] == "customer" and body["location"]["district"] == "mirobod"
        assert "frame-ancestors" in r.headers["Content-Security-Policy"]
        assert r.headers["X-Content-Type-Options"] == "nosniff"


async def test_offers_reserve_cancel_through_the_api():
    async with api() as (client, svc, _, h):
        q = {"med": PARA, "lat": str(CENTRE[0]), "lon": str(CENTRE[1]), "w": "50", "open": "0"}
        body = await (await client.get("/api/offers", params=q, headers=h(ALI))).json()
        assert (body["nearest"], body["cheapest"]) == (1, 12) and body["items"][0]["pharmacy_id"] == body["best"]
        assert set(body["items"][0]) >= {"name", "phone", "price", "available", "updated_at", "status", "dist"}
        r = await client.post("/api/reserve", json={"pharmacy": 2, "med": PARA, "qty": 2}, headers=h(ALI))
        res = await r.json()
        assert r.status == 200 and len(res["code"]) == 6
        mine = await (await client.get("/api/reservations", headers=h(ALI))).json()
        assert mine["items"][0]["pharmacy"]["name"] == "Sokin Tun 24"
        assert (await client.post(f"/api/reservations/{res['id']}/cancel", headers=h(VALI))).status == 404
        assert (await client.post(f"/api/reservations/{res['id']}/cancel", headers=h(ALI))).status == 200
        assert (await stock(svc, 2, PARA))["reserved"] == 0
        rx = await client.post("/api/reserve", json={"pharmacy": 2, "med": "amoxicillin-500", "qty": 1}, headers=h(ALI))
        assert (rx.status, (await rx.json())["error"]) == (400, "rx")


async def test_input_validation():
    async with api() as (client, _, _clock, h):
        bad_bodies = [{"pharmacy": True, "med": PARA, "qty": 1}, {"pharmacy": 2, "med": PARA, "qty": 1.5},
                      {"pharmacy": 2, "med": ["x"], "qty": 1}, {"pharmacy": 2, "med": PARA * 10, "qty": 1},
                      {"pharmacy": "2; DROP TABLE stock", "med": PARA, "qty": 1}, {"pharmacy": 2, "med": PARA}]
        for body in bad_bodies:
            assert (await client.post("/api/reserve", json=body, headers=h(ALI))).status in (400, 404), body
        assert (await client.post("/api/reserve", data="not json", headers=h(ALI))).status == 400
        assert (await client.post("/api/reserve", data="[1]", headers=h(ALI))).status == 400
        for q in ({"med": PARA, "lat": "nan", "lon": "1"}, {"med": PARA, "lat": "91", "lon": "1"},
                  {"med": "nope", "lat": "41", "lon": "69"}, {"med": PARA, "lat": "41", "lon": "69", "w": "500"}):
            assert (await client.get("/api/offers", params=q, headers=h(ALI))).status in (400, 404), q
        big = "x" * 200_000
        assert (await client.post("/api/location", data=big, headers=h(ALI))).status == 413
        assert (await client.post("/api/location", json={"district": "atlantis"}, headers=h(ALI))).status == 400
        r = await client.post("/api/location", json={"district": "chilonzor"}, headers=h(ALI))
        assert (await r.json())["district"] == "chilonzor"
        assert (await client.post("/api/alerts", json={"med": PARA, "km": 2}, headers=h(ALI))).status == 400
        r = await client.post("/api/alerts", json={"med": PARA, "km": 3, "max_price": "3 000"}, headers=h(ALI))
        assert (await r.json())["max_price"] == 3000


async def test_customer_cannot_reach_pharmacist_or_admin_routes():
    async with api() as (client, _, _clock, h):
        for method, path, body in (("get", "/api/pharm", None), ("post", "/api/pharm/stock", {"med": PARA}),
                                   ("post", "/api/pharm/confirm", {"code": "123456"}),
                                   ("post", "/api/pharm/import", None), ("get", "/api/pharm/export", None),
                                   ("post", "/api/admin/pharmacies", {"name": "X"}),
                                   ("post", "/api/admin/invites", {"pharmacy": 1})):
            r = await getattr(client, method)(path, json=body, headers=h(ALI))
            assert r.status == 403, path


async def test_pharmacist_a_cannot_change_pharmacy_b():
    async with api() as (client, svc, _, h):
        res = await (await client.post("/api/reserve", json={"pharmacy": 2, "med": PARA, "qty": 1},
                                       headers=h(ALI))).json()
        r = await client.post("/api/pharm/confirm", json={"code": res["code"]}, headers=h(OYBEK))  # works at 6
        assert (r.status, (await r.json())["error"]) == (400, "code_not_found")
        r = await client.post("/api/pharm/stock", json={"med": PARA, "qty": 99, "price": 1000, "pharmacy": 2},
                              headers=h(OYBEK))  # a smuggled "pharmacy" field is ignored
        assert r.status == 200 and (await r.json())["pharmacy_id"] == 6
        assert (await stock(svc, 2, PARA))["qty"] == 4
        panel = await (await client.get("/api/pharm", headers=h(DILNOZA))).json()
        assert panel["pharmacy"]["id"] == 2 and {s["pharmacy_id"] for s in panel["stock"]} == {2}
        assert [x["code"] for x in panel["reservations"]] == [res["code"]]
        r = await client.post("/api/pharm/confirm", json={"code": res["code"]}, headers=h(DILNOZA))
        assert (await r.json())["status"] == "picked"
        r = await client.post("/api/pharm/import", data=b"med,price,qty\nparacetamol-500,5200,9\n",
                              headers=h(DILNOZA))
        assert (await r.json())["updated"] == 1
        r = await client.get("/api/pharm/export", headers=h(DILNOZA))
        assert r.headers["Content-Type"].startswith("text/csv") and "paracetamol-500" in await r.text()


async def test_admin_routes_and_rate_limit():
    async with api(rate=5) as (client, _, _clock, h):
        r = await client.post("/api/admin/invites", json={"pharmacy": 3}, headers=h(ADMIN))
        assert (await r.json())["link"].startswith("https://t.me/test_bot?start=inv_")
        r = await client.post("/api/admin/pharmacies", json={"name": "Yangi Farm", "address": "Sergeli 5-uy",
                                                              "lat": 41.22, "lon": 69.22, "hours": "24/7",
                                                              "phone": "+998 71 000 77 77"}, headers=h(ADMIN))
        assert r.status == 200
        codes = [(await client.get("/api/me", headers=h(ALI))).status for _ in range(7)]
        assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]


async def test_static_and_health():
    async with api() as (client, _, _clock, _h):
        assert (await client.get("/healthz")).status == 200
        assert (await client.get("/shared/locales/uz.json")).status == 200
        assert (await client.get("/shared/../navbatchi/config.py")).status in (403, 404)
        assert (await client.get("/webapp/../.env")).status in (403, 404)
