"""aiohttp server: the Mini App's static files and its JSON API.

Every /api call must carry ``Authorization: tma <initData>``; the HMAC and ``auth_date`` are checked, then the call
runs *as* that Telegram user through the same Service the bot uses. Roles are checked inside the service, so a
customer gets 403 on pharmacist routes and a pharmacist can only ever reach their own pharmacy.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from aiohttp import web

from .common import Refused
from .core.csvio import MAX_BYTES
from .data import med_label
from .security import AuthError, RateLimiter, validate_init_data
from .service import Service

log = logging.getLogger(__name__)
ME = web.RequestKey("me", int)
ROOT = Path(__file__).resolve().parent.parent
CSP = ("default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; "
       "frame-ancestors https://web.telegram.org https://*.telegram.org; base-uri 'none'; form-action 'none'")
STATUS = {"forbidden": 403, "not_found": 404}
ITEM_FIELDS = ("pharmacy_id", "name", "phone", "address_uz", "address_ru", "lat", "lon", "hours", "off", "district",
               "price", "available", "updated_at", "dist", "status", "score")


def _int(value: object, lo: int, hi: int, code: str = "generic") -> int:
    """Whole numbers only: an int, or a short string of ASCII digits. Floats and booleans are refused."""
    if isinstance(value, str) and 0 < len(value) <= 12 and value.isascii() and value.isdigit():
        n = int(value)
    elif isinstance(value, int) and not isinstance(value, bool):
        n = value
    else:
        raise Refused(code)
    if not lo <= n <= hi:
        raise Refused(code)
    return n


def _float(value: object) -> float:
    try:
        if isinstance(value, bool) or (isinstance(value, str) and len(value) > 24):
            raise ValueError
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as err:
        raise Refused("location") from err


def _str(value: object, limit: int) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise Refused("generic")
    return value


async def _body(request: web.Request) -> dict:
    try:
        data = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise Refused("generic") from err
    if not isinstance(data, dict):
        raise Refused("generic")
    return data


def make_app(service: Service, bot_token: str, notifier=None, max_age: int = 3600, rate_per_minute: int = 60,
             bot_username: str = "") -> web.Application:
    limiter = RateLimiter(rate_per_minute)

    @web.middleware
    async def guard(request: web.Request, handler):
        try:
            if request.path.startswith("/api/"):
                header = request.headers.get("Authorization", "")
                if not header.startswith("tma "):
                    raise AuthError("missing")
                user = validate_init_data(header[4:], bot_token, max_age, now=service.now() / 1000)
                if not limiter.allow(user["id"]):
                    return web.json_response({"error": "rate"}, status=429)
                await service.touch_user(user["id"], user["first_name"], user["language_code"])
                request[ME] = user["id"]
            resp = await handler(request)
        except AuthError:
            resp = web.json_response({"error": "auth"}, status=401)
        except Refused as err:
            resp = web.json_response({"error": err.code}, status=STATUS.get(err.code, 400))
        resp.headers.update({"Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff",
                             "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"})
        return resp

    async def me(request: web.Request) -> web.Response:
        uid = request[ME]
        user = await service.user(uid)
        ph = None
        if user["role"] == "pharmacist" and user["pharmacy_id"]:
            p = await service.pharmacy(user["pharmacy_id"])
            ph = {"id": p["id"], "name": p["name"]}
        loc = None
        if user["lat"] is not None:
            loc = {"lat": user["lat"], "lon": user["lon"], "district": user["district"]}
        return web.json_response({"id": uid, "name": user["name"], "lang": user["lang"], "role": user["role"],
                                  "admin": uid in service.admins, "pharmacy": ph, "location": loc,
                                  "now": service.now()})

    async def lang(request: web.Request) -> web.Response:
        d = await _body(request)
        await service.set_lang(request[ME], _str(d.get("lang"), 2))
        return web.json_response({"lang": d["lang"]})

    async def location(request: web.Request) -> web.Response:
        d = await _body(request)
        if "district" in d:
            dist = await service.set_district(request[ME], _str(d["district"], 32))
            return web.json_response({"lat": dist["lat"], "lon": dist["lon"], "district": dist["id"]})
        lat, lon = _float(d.get("lat")), _float(d.get("lon"))
        district = await service.set_location(request[ME], lat, lon)
        return web.json_response({"lat": lat, "lon": lon, "district": district})

    async def offers(request: web.Request) -> web.Response:
        q = request.query
        med = _str(q.get("med"), 40)
        res = await service.offers(med, _float(q.get("lat")), _float(q.get("lon")), _int(q.get("w", 50), 0, 100),
                                   q.get("open") == "1")
        items = [{k: i[k] for k in ITEM_FIELDS} for i in res["items"]]
        return web.json_response({"med": med, "items": items, "nearest": res["nearest"], "cheapest": res["cheapest"],
                                  "best": res["best"], "analogs": res["analogs"], "now": res["now"]})

    async def reserve(request: web.Request) -> web.Response:
        d = await _body(request)
        res = await service.reserve(request[ME], _int(d.get("pharmacy"), 1, 10**9, "not_found"),
                                    _str(d.get("med"), 40), _int(d.get("qty"), 1, 5, "qty"))
        if notifier:
            await notifier.new_reservation(res)
        return web.json_response(res)

    async def reservations(request: web.Request) -> web.Response:
        out = []
        for r in await service.my_reservations(request[ME]):
            ph = await service.pharmacy(r["pharmacy_id"])
            out.append({**r, "pharmacy": {k: ph[k] for k in ("name", "phone", "address_uz", "address_ru", "lat",
                                                             "lon")}})
        return web.json_response({"items": out, "now": service.now()})

    async def cancel(request: web.Request) -> web.Response:
        rid = _int(request.match_info["rid"], 1, 10**12, "not_found")
        return web.json_response(await service.cancel(request[ME], rid))

    async def alert_add(request: web.Request) -> web.Response:
        d = await _body(request)
        price = d.get("max_price")
        if price is not None and not isinstance(price, int | str):
            raise Refused("price")
        return web.json_response(await service.add_alert(request[ME], _str(d.get("med"), 40),
                                                         _int(d.get("km"), 1, 10), price))

    async def alerts(request: web.Request) -> web.Response:
        return web.json_response({"items": await service.my_alerts(request[ME])})

    async def alert_del(request: web.Request) -> web.Response:
        await service.delete_alert(request[ME], _int(request.match_info["aid"], 1, 10**12, "not_found"))
        return web.json_response({"ok": True})

    # ── pharmacist ──
    async def pharm(request: web.Request) -> web.Response:
        uid = request[ME]
        pid = await service.pharmacy_of(uid)
        ph = await service.pharmacy(pid)
        stock = [{**r, "label": med_label(service.catalog.by_id[r["med_id"]], "uz")}
                 for r in await service.stock_list(uid) if r["med_id"] in service.catalog.by_id]
        return web.json_response({"pharmacy": {"id": pid, "name": ph["name"]}, "stock": stock,
                                  "reservations": await service.pharm_reservations(uid), "now": service.now()})

    async def pharm_stock(request: web.Request) -> web.Response:
        d = await _body(request)
        row = await service.set_stock(request[ME], _str(d.get("med"), 40), d.get("qty"), d.get("price"))
        return web.json_response(row)

    async def pharm_confirm(request: web.Request) -> web.Response:
        d = await _body(request)
        res = await service.confirm_code(request[ME], _str(d.get("code"), 16))
        if notifier:
            await notifier.picked(res)
        return web.json_response(res)

    async def pharm_import(request: web.Request) -> web.Response:
        await service.pharmacy_of(request[ME])
        raw = await request.content.read(MAX_BYTES + 1)
        return web.json_response(await service.import_csv(request[ME], raw))

    async def pharm_export(request: web.Request) -> web.Response:
        body = (await service.export_csv(request[ME])).encode("utf-8-sig")
        return web.Response(body=body, content_type="text/csv", charset="utf-8",
                            headers={"Content-Disposition": 'attachment; filename="stock.csv"'})

    # ── admin ──
    async def admin_add(request: web.Request) -> web.Response:
        d = await _body(request)
        pid = await service.add_pharmacy(request[ME], d.get("name"), d.get("address"), d.get("lat"), d.get("lon"),
                                         d.get("hours"), d.get("phone"))
        return web.json_response({"id": pid})

    async def admin_invite(request: web.Request) -> web.Response:
        d = await _body(request)
        token = await service.create_invite(request[ME], _int(d.get("pharmacy"), 1, 10**9, "not_found"))
        return web.json_response({"link": f"https://t.me/{bot_username}?start=inv_{token}"})

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def index(_: web.Request) -> web.Response:
        raise web.HTTPFound("/webapp/")

    app = web.Application(middlewares=[guard], client_max_size=MAX_BYTES + 1024)
    r = app.router
    r.add_get("/api/me", me)
    r.add_post("/api/lang", lang)
    r.add_post("/api/location", location)
    r.add_get("/api/offers", offers)
    r.add_post("/api/reserve", reserve)
    r.add_get("/api/reservations", reservations)
    r.add_post(r"/api/reservations/{rid:\d{1,12}}/cancel", cancel)
    r.add_get("/api/alerts", alerts)
    r.add_post("/api/alerts", alert_add)
    r.add_delete(r"/api/alerts/{aid:\d{1,12}}", alert_del)
    r.add_get("/api/pharm", pharm)
    r.add_post("/api/pharm/stock", pharm_stock)
    r.add_post("/api/pharm/confirm", pharm_confirm)
    r.add_post("/api/pharm/import", pharm_import)
    r.add_get("/api/pharm/export", pharm_export)
    r.add_post("/api/admin/pharmacies", admin_add)
    r.add_post("/api/admin/invites", admin_invite)
    r.add_get("/healthz", health)
    r.add_get("/", index)
    r.add_static("/webapp/", ROOT / "webapp", append_version=False)
    r.add_static("/shared/", ROOT / "shared", append_version=False)
    return app
