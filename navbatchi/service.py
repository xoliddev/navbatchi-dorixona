"""Everything a customer can do, shared by the bot and the Mini App API: users, location, search, ranked offers,
reservations and price alerts. Pharmacist and admin actions live in staff.py (mixed in below).

Every method re-checks who is asking; nothing the client sends is trusted for authorization.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from collections.abc import Callable

from .common import LANGS, Refused, clean_text, norm_lang
from .core import alerts as alert_rules
from .core import catalog as search_rules
from .core import reserve as rules
from .core.geo import haversine_m, nearest_district, valid_point
from .core.hours import status
from .core.money import PriceError, parse_price
from .core.rank import rank
from .data import Catalog
from .db import Database
from .staff import StaffMixin


class Service(StaffMixin):
    def __init__(self, db: Database, catalog: Catalog, clock: Callable[[], float] | None = None,
                 rng: Callable[[int], int] = secrets.randbelow, admins: frozenset[int] = frozenset(),
                 invite_hours: int = 72) -> None:
        self.db, self.catalog, self.rng, self.admins = db, catalog, rng, frozenset(admins)
        self.clock = clock or (lambda: time.time() * 1000)
        self.invite_hours = invite_hours

    def now(self) -> int:
        return int(self.clock())

    # ── users ──
    async def user(self, uid: int) -> dict | None:
        return await self.db.one("SELECT * FROM users WHERE id = ?", (uid,))

    async def touch_user(self, uid: int, name: str, lang_code: str | None = None) -> dict:
        name = clean_text(name, 64) or "-"
        row = await self.user(uid)
        if row is None:
            await self.db.run("INSERT OR IGNORE INTO users (id, name, lang, created_at) VALUES (?, ?, ?, ?)",
                              (uid, name, norm_lang(lang_code), self.now()))
            row = await self.user(uid)
        elif row["name"] != name:
            await self.db.run("UPDATE users SET name = ? WHERE id = ?", (name, uid))
            row["name"] = name
        row["admin"] = uid in self.admins
        return row

    async def set_lang(self, uid: int, lang: str) -> None:
        if lang not in LANGS:
            raise Refused("generic")
        await self.db.run("UPDATE users SET lang = ? WHERE id = ?", (lang, uid))

    async def set_location(self, uid: int, lat: object, lon: object) -> str:
        if not valid_point(lat, lon):
            raise Refused("location")
        la, lo = round(float(lat), 6), round(float(lon), 6)  # type: ignore[arg-type]
        district = nearest_district(la, lo, self.catalog.districts)
        await self.db.run("UPDATE users SET lat = ?, lon = ?, district = ? WHERE id = ?", (la, lo, district, uid))
        return district

    async def set_district(self, uid: int, district_id: str) -> dict:
        d = self.catalog.district(district_id)
        if d is None:
            raise Refused("location")
        await self.db.run("UPDATE users SET lat = ?, lon = ?, district = ? WHERE id = ?",
                          (d["lat"], d["lon"], d["id"], uid))
        return d

    # ── search and offers ──
    def search(self, text: str) -> list[dict]:
        return [self.catalog.by_id[h["id"]] for h in search_rules.search(self.catalog.meds, clean_text(text, 64))]

    def med(self, med_id: str) -> dict:
        med = self.catalog.med(med_id)
        if med is None:
            raise Refused("not_found")
        return med

    async def pharmacy(self, pid: int) -> dict:
        row = await self.db.one("SELECT * FROM pharmacies WHERE id = ? AND active = 1", (pid,))
        if row is None:
            raise Refused("not_found")
        row["off"] = json.loads(row["off"])
        return row

    async def raw_offers(self, med_id: str) -> list[dict]:
        rows = await self.db.all(
            "SELECT s.pharmacy_id, s.price, s.qty - s.reserved AS available, s.qty, s.updated_at, p.lat, p.lon, "
            "p.hours, p.off, p.name, p.phone, p.address_uz, p.address_ru, p.district FROM stock s "
            "JOIN pharmacies p ON p.id = s.pharmacy_id WHERE s.med_id = ? AND p.active = 1", (med_id,))
        for r in rows:
            r["off"] = json.loads(r["off"])
        return rows

    async def offers(self, med_id: str, lat: float, lon: float, weight: int = 50, open_only: bool = False,
                     max_m: int | None = None) -> dict:
        med = self.med(med_id)
        if not valid_point(lat, lon):
            raise Refused("location")
        now = self.now()
        res = rank(await self.raw_offers(med_id), float(lat), float(lon), now, weight, open_only, max_m)
        prices = {med_id: min((i["price"] for i in res["items"]), default=None)}
        for aid in search_rules.analogs(self.catalog.meds, med_id):
            items = rank(await self.raw_offers(aid), float(lat), float(lon), now, weight, open_only, max_m)["items"]
            prices[aid] = min((i["price"] for i in items), default=None)
        mins = {k: v for k, v in prices.items() if v is not None}
        return {**res, "med": med, "analogs": search_rules.cheaper_analogs(self.catalog.meds, med_id, mins), "now": now}

    async def offer_at(self, med_id: str, pid: int, lat: float, lon: float) -> dict:
        """One pharmacy's offer for the card screen (also when it is out of stock or closed)."""
        self.med(med_id)
        row = next((r for r in await self.raw_offers(med_id) if r["pharmacy_id"] == pid), None)
        if row is None or not valid_point(lat, lon):
            raise Refused("not_found")
        return {**row, "dist": haversine_m(float(lat), float(lon), row["lat"], row["lon"]),
                "status": status(row["hours"], row["off"], self.now())}

    # ── reservations ──
    async def reserve(self, uid: int, pid: int, med_id: str, qty: int) -> dict:
        med = self.med(med_id)
        now = self.now()
        async with self.db.tx() as c:
            sql = "SELECT COUNT(*) FROM reservations WHERE user_id = ? AND status = 'held'"
            async with c.execute(sql, (uid,)) as cur:
                active = (await cur.fetchone())[0]
            sql = ("SELECT s.qty - s.reserved AS available, s.price FROM stock s JOIN pharmacies p ON "
                   "p.id = s.pharmacy_id WHERE s.pharmacy_id = ? AND s.med_id = ? AND p.active = 1")
            async with c.execute(sql, (pid, med_id)) as cur:
                row = await cur.fetchone()
            if row is None:
                raise Refused("not_found")
            try:
                rules.check(bool(med["rx"]), qty, row["available"], active)
            except rules.ReserveError as err:
                raise Refused(err.code) from err
            # the real guard: one conditional UPDATE, so two buyers can never both take the last pack
            cur = await c.execute("UPDATE stock SET reserved = reserved + ? WHERE pharmacy_id = ? AND med_id = ? "
                                  "AND qty - reserved >= ?", (qty, pid, med_id, qty))
            if cur.rowcount != 1:
                raise Refused("stock")
            for _ in range(10):
                code = rules.make_code(self.rng(1_000_000))
                try:
                    cur = await c.execute(
                        "INSERT INTO reservations (user_id, pharmacy_id, med_id, qty, price, code, created_at, "
                        "expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (uid, pid, med_id, qty, row["price"], code, now, rules.expires_at(now)))
                    break
                except sqlite3.IntegrityError:
                    continue  # this code is already held at this pharmacy: draw another
            else:
                raise Refused("generic")
            rid = cur.lastrowid
        return await self.reservation(rid)

    async def reservation(self, rid: int) -> dict:
        row = await self.db.one("SELECT * FROM reservations WHERE id = ?", (rid,))
        if row is None:
            raise Refused("not_found")
        return row

    async def my_reservations(self, uid: int, limit: int = 10) -> list[dict]:
        return await self.db.all("SELECT * FROM reservations WHERE user_id = ? ORDER BY status != 'held', id DESC "
                                 "LIMIT ?", (uid, limit))

    async def cancel(self, uid: int, rid: int) -> dict:
        now = self.now()
        async with self.db.tx() as c:
            async with c.execute("SELECT * FROM reservations WHERE id = ? AND user_id = ?", (rid, uid)) as cur:
                res = await cur.fetchone()
            if res is None:
                raise Refused("not_found")
            try:
                rules.move(res["status"], "cancel")
            except rules.ReserveError as err:
                raise Refused("state") from err
            await self._release(c, res, "cancelled", now)
        return await self.reservation(rid)

    @staticmethod
    async def _release(c, res, status: str, now: int, by: int | None = None) -> bool:
        cur = await c.execute("UPDATE reservations SET status = ?, done_at = ?, done_by = ? WHERE id = ? AND "
                              "status = 'held'", (status, now, by, res["id"]))
        if cur.rowcount != 1:
            return False
        if status == "picked":  # handed over: the packs leave the shelf
            await c.execute("UPDATE stock SET qty = qty - ?, reserved = reserved - ?, updated_at = ? WHERE "
                            "pharmacy_id = ? AND med_id = ?", (res["qty"], res["qty"], now, res["pharmacy_id"],
                                                               res["med_id"]))
        else:  # cancelled or expired: the packs go back on sale
            await c.execute("UPDATE stock SET reserved = reserved - ? WHERE pharmacy_id = ? AND med_id = ?",
                            (res["qty"], res["pharmacy_id"], res["med_id"]))
        return True

    async def expire_due(self, limit: int = 200) -> list[dict]:
        """Release every reservation whose 2 hours are over. Safe to run from several loops at once."""
        now = self.now()
        done = []
        async with self.db.tx() as c:
            async with c.execute("SELECT * FROM reservations WHERE status = 'held' AND expires_at <= ? ORDER BY "
                                 "expires_at LIMIT ?", (now, limit)) as cur:
                due = [dict(r) for r in await cur.fetchall()]
            for res in due:
                if await self._release(c, res, "expired", now):
                    done.append({**res, "status": "expired"})
        return done

    # ── price alerts ──
    async def add_alert(self, uid: int, med_id: str, radius_km: int, max_price: object = None) -> dict:
        self.med(med_id)
        user = await self.user(uid)
        if not user or user["lat"] is None:
            raise Refused("no_location")
        if radius_km not in alert_rules.RADII_KM:
            raise Refused("generic")
        try:
            price = None if max_price in (None, "", 0) else parse_price(max_price)
        except PriceError as err:
            raise Refused("price") from err
        async with self.db.tx() as c:
            async with c.execute("SELECT COUNT(*) FROM alerts WHERE user_id = ? AND fired_at IS NULL", (uid,)) as cur:
                if (await cur.fetchone())[0] >= alert_rules.MAX_ALERTS_PER_USER:
                    raise Refused("too_many_alerts")
            cur = await c.execute("INSERT INTO alerts (user_id, med_id, lat, lon, radius_m, max_price, created_at) "
                                  "VALUES (?, ?, ?, ?, ?, ?, ?)", (uid, med_id, user["lat"], user["lon"],
                                                                   radius_km * 1000, price, self.now()))
            aid = cur.lastrowid
        return await self.db.one("SELECT * FROM alerts WHERE id = ?", (aid,))

    async def my_alerts(self, uid: int) -> list[dict]:
        return await self.db.all("SELECT * FROM alerts WHERE user_id = ? AND fired_at IS NULL ORDER BY id", (uid,))

    async def delete_alert(self, uid: int, aid: int) -> None:
        if await self.db.run("DELETE FROM alerts WHERE id = ? AND user_id = ? AND fired_at IS NULL", (aid, uid)) != 1:
            raise Refused("not_found")

    async def run_alerts(self) -> list[dict]:
        """Fire every alert whose condition now holds. Each alert is claimed with a conditional UPDATE first, so
        it is delivered at most once even if two loops run or the process restarts mid-way."""
        fired = []
        pending = await self.db.all("SELECT * FROM alerts WHERE fired_at IS NULL ORDER BY id LIMIT 500")
        offers: dict[str, list[dict]] = {}
        for a in pending:
            if a["med_id"] not in offers:
                offers[a["med_id"]] = await self.raw_offers(a["med_id"])
            hit = alert_rules.match(a, offers[a["med_id"]])
            if hit is None:
                continue
            claimed = await self.db.run("UPDATE alerts SET fired_at = ?, pharmacy_id = ?, price = ? WHERE id = ? AND "
                                        "fired_at IS NULL", (self.now(), hit["pharmacy_id"], hit["price"], a["id"]))
            if claimed == 1:
                fired.append({**a, **hit})
        return fired
