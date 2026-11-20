"""Pharmacist and admin actions (mixed into Service).

A pharmacist is linked to exactly one pharmacy through a single-use invite from an admin, and every action here
looks that pharmacy up from the database: the pharmacy id is never taken from the client.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from .common import Refused, clean_text
from .core import reserve as rules
from .core.csvio import CsvError, parse_stock, to_csv
from .core.geo import nearest_district, valid_point
from .core.hours import HoursError, parse
from .core.money import PriceError, parse_price, parse_qty
from .security import TOKEN_RE, new_invite_token, token_digest

if TYPE_CHECKING:
    from .service import Service

PHONE_RE = re.compile(r"^\+?[0-9][0-9 ()-]{6,19}$")


class StaffMixin:
    # ── pharmacist ──
    async def pharmacy_of(self: Service, uid: int) -> int:
        user = await self.user(uid)
        if not user or user["role"] != "pharmacist" or not user["pharmacy_id"]:
            raise Refused("forbidden")
        return int(user["pharmacy_id"])

    async def stock_list(self: Service, uid: int) -> list[dict]:
        pid = await self.pharmacy_of(uid)
        rows = await self.db.all("SELECT * FROM stock WHERE pharmacy_id = ?", (pid,))
        order = {m["id"]: i for i, m in enumerate(self.catalog.meds)}
        return sorted(rows, key=lambda r: order.get(r["med_id"], 1_000_000))

    async def _put_stock(self: Service, c, pid: int, med_id: str, qty: int, price: int, now: int) -> bool:
        async with c.execute("SELECT reserved FROM stock WHERE pharmacy_id = ? AND med_id = ?", (pid, med_id)) as cur:
            row = await cur.fetchone()
        if row is not None and qty < row["reserved"]:
            return False  # cannot drop below what customers already hold
        await c.execute(
            "INSERT INTO stock (pharmacy_id, med_id, qty, price, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (pharmacy_id, med_id) DO UPDATE SET qty = excluded.qty, price = excluded.price, "
            "updated_at = excluded.updated_at", (pid, med_id, qty, price, now))
        return True

    async def set_stock(self: Service, uid: int, med_id: str, qty: object, price: object) -> dict:
        pid = await self.pharmacy_of(uid)
        self.med(med_id)
        try:
            q, p = parse_qty(qty), parse_price(price)
        except PriceError as err:
            raise Refused("stock_value") from err
        async with self.db.tx() as c:
            if not await self._put_stock(c, pid, med_id, q, p, self.now()):
                raise Refused("below_reserved")
        return await self.db.one("SELECT * FROM stock WHERE pharmacy_id = ? AND med_id = ?", (pid, med_id))

    async def import_csv(self: Service, uid: int, raw: bytes) -> dict:
        pid = await self.pharmacy_of(uid)
        try:
            parsed = parse_stock(raw, self.catalog.meds)
        except CsvError as err:
            raise Refused(f"csv_{err.code}") from err
        errors = list(parsed["errors"])
        updated = 0
        now = self.now()
        async with self.db.tx() as c:
            for row in parsed["rows"]:
                if await self._put_stock(c, pid, row["med"], row["qty"], row["price"], now):
                    updated += 1
                else:
                    errors.append({"line": 0, "code": "below_reserved", "med": row["med"]})
        return {"updated": updated, "errors": errors}

    async def export_csv(self: Service, uid: int) -> str:
        rows = await self.stock_list(uid)
        out = [["med", "name", "price", "qty", "reserved"]]
        for r in rows:
            med = self.catalog.med(r["med_id"])
            out.append([r["med_id"], med["name"]["uz"] if med else r["med_id"], r["price"], r["qty"], r["reserved"]])
        return to_csv(out)

    async def pharm_reservations(self: Service, uid: int, limit: int = 20) -> list[dict]:
        pid = await self.pharmacy_of(uid)
        return await self.db.all(
            "SELECT * FROM reservations WHERE pharmacy_id = ? ORDER BY status != 'held', "
            "CASE WHEN status = 'held' THEN expires_at ELSE -id END LIMIT ?", (pid, limit))

    async def confirm_code(self: Service, uid: int, code: object) -> dict:
        """The customer shows the 6-digit code; the pharmacist types it; the packs leave the shelf."""
        pid = await self.pharmacy_of(uid)
        clean = rules.clean_code(code)
        if clean is None:
            raise Refused("code")
        now = self.now()
        async with self.db.tx() as c:
            async with c.execute("SELECT * FROM reservations WHERE pharmacy_id = ? AND code = ? AND status = 'held'",
                                 (pid, clean)) as cur:
                res = await cur.fetchone()
            if res is None:
                raise Refused("code_not_found")
            if res["expires_at"] <= now:
                raise Refused("code_expired")  # the expiry loop releases it
            await self._release(c, res, "picked", now, by=uid)
        return await self.reservation(res["id"])

    # ── admin ──
    def require_admin(self: Service, uid: int) -> None:
        if uid not in self.admins:
            raise Refused("forbidden")

    async def list_pharmacies(self: Service) -> list[dict]:
        rows = await self.db.all("SELECT * FROM pharmacies WHERE active = 1 ORDER BY id")
        for r in rows:
            r["off"] = json.loads(r["off"])
        return rows

    async def add_pharmacy(self: Service, uid: int, name: object, address: object, lat: object, lon: object,
                           hours: object, phone: object) -> int:
        self.require_admin(uid)
        name_s, addr = clean_text(name, 60), clean_text(address, 160)
        if len(name_s) < 2 or len(addr) < 5:
            raise Refused("pharmacy_fields")
        if not valid_point(lat, lon):
            raise Refused("location")
        hours_s = clean_text(hours, 11)
        try:
            parse(hours_s)
        except HoursError as err:
            raise Refused("hours") from err
        phone_s = clean_text(phone, 20)
        if not PHONE_RE.match(phone_s):
            raise Refused("phone")
        la, lo = float(lat), float(lon)  # type: ignore[arg-type]
        district = nearest_district(la, lo, self.catalog.districts)
        async with self.db.tx() as c:
            cur = await c.execute(
                "INSERT INTO pharmacies (name, district, lat, lon, hours, off, phone, address_uz, address_ru) "
                "VALUES (?, ?, ?, ?, ?, '[]', ?, ?, ?)", (name_s, district, la, lo, hours_s, phone_s, addr, addr))
            return int(cur.lastrowid)

    async def create_invite(self: Service, uid: int, pid: int) -> str:
        """Single-use invite link for a pharmacist of ``pid``; only its SHA-256 is stored."""
        self.require_admin(uid)
        await self.pharmacy(pid)
        token = new_invite_token()
        now = self.now()
        await self.db.run("INSERT INTO invites (digest, pharmacy_id, created_by, created_at, expires_at) VALUES "
                          "(?, ?, ?, ?, ?)", (token_digest(token), pid, uid, now, now + self.invite_hours * 3_600_000))
        return token

    async def redeem_invite(self: Service, uid: int, token: str) -> dict:
        if not isinstance(token, str) or not TOKEN_RE.match(token):
            raise Refused("invite")
        now = self.now()
        async with self.db.tx() as c:
            async with c.execute("SELECT * FROM invites WHERE digest = ? AND used_at IS NULL AND expires_at > ?",
                                 (token_digest(token), now)) as cur:
                inv = await cur.fetchone()
            if inv is None:
                raise Refused("invite")
            await c.execute("UPDATE invites SET used_at = ?, used_by = ? WHERE digest = ? AND used_at IS NULL",
                            (now, uid, inv["digest"]))
            await c.execute("UPDATE users SET role = 'pharmacist', pharmacy_id = ? WHERE id = ?",
                            (inv["pharmacy_id"], uid))
        return await self.pharmacy(inv["pharmacy_id"])
