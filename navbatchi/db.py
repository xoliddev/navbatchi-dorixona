"""SQLite storage (aiosqlite, WAL, indexes). Parameterised SQL only.

Stock is guarded twice: the service books units with one conditional UPDATE inside ``BEGIN IMMEDIATE``, and the
table itself refuses ``reserved > qty`` or negative numbers, so even a bug cannot oversell.
Times are UTC milliseconds.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from .core.seedgen import stock_rows

SCHEMA = """
CREATE TABLE IF NOT EXISTS pharmacies (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, district TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
  hours TEXT NOT NULL, off TEXT NOT NULL DEFAULT '[]', phone TEXT NOT NULL, address_uz TEXT NOT NULL,
  address_ru TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, lang TEXT NOT NULL DEFAULT 'uz',
  role TEXT NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'pharmacist')),
  pharmacy_id INTEGER REFERENCES pharmacies(id), lat REAL, lon REAL, district TEXT, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS stock (
  pharmacy_id INTEGER NOT NULL REFERENCES pharmacies(id), med_id TEXT NOT NULL,
  qty INTEGER NOT NULL CHECK (qty >= 0), reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0 AND reserved <= qty),
  price INTEGER NOT NULL CHECK (price > 0), updated_at INTEGER NOT NULL, PRIMARY KEY (pharmacy_id, med_id)
);
CREATE INDEX IF NOT EXISTS stock_med ON stock(med_id);
CREATE TABLE IF NOT EXISTS reservations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, pharmacy_id INTEGER NOT NULL, med_id TEXT NOT NULL,
  qty INTEGER NOT NULL CHECK (qty BETWEEN 1 AND 5), price INTEGER NOT NULL, code TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'held' CHECK (status IN ('held', 'picked', 'cancelled', 'expired')),
  created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, done_at INTEGER, done_by INTEGER
);
CREATE INDEX IF NOT EXISTS res_user ON reservations(user_id, status);
CREATE INDEX IF NOT EXISTS res_due ON reservations(status, expires_at);
CREATE INDEX IF NOT EXISTS res_pharmacy ON reservations(pharmacy_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS res_code ON reservations(pharmacy_id, code) WHERE status = 'held';
CREATE TABLE IF NOT EXISTS invites (
  digest TEXT PRIMARY KEY, pharmacy_id INTEGER NOT NULL REFERENCES pharmacies(id), created_by INTEGER NOT NULL,
  created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, used_at INTEGER, used_by INTEGER
);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, med_id TEXT NOT NULL, lat REAL NOT NULL,
  lon REAL NOT NULL, radius_m INTEGER NOT NULL, max_price INTEGER, created_at INTEGER NOT NULL,
  fired_at INTEGER, pharmacy_id INTEGER, price INTEGER
);
CREATE INDEX IF NOT EXISTS alerts_open ON alerts(fired_at, med_id);
CREATE INDEX IF NOT EXISTS alerts_user ON alerts(user_id);
"""


class Database:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn
        self.lock = asyncio.Lock()  # one transaction at a time on this connection

    @classmethod
    async def open(cls, path: str) -> Database:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(path, isolation_level=None)  # we issue BEGIN/COMMIT ourselves
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.executescript(SCHEMA)
        return cls(conn)

    async def close(self) -> None:
        await self.conn.close()

    @asynccontextmanager
    async def tx(self):
        """``BEGIN IMMEDIATE`` takes the write lock up front, so check-then-write sequences cannot interleave,
        neither between coroutines (asyncio lock) nor between processes (SQLite lock + busy_timeout)."""
        async with self.lock:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
            except BaseException:
                await self.conn.execute("ROLLBACK")
                raise
            await self.conn.execute("COMMIT")

    async def one(self, sql: str, args: tuple = ()) -> dict | None:
        async with self.conn.execute(sql, args) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def all(self, sql: str, args: tuple = ()) -> list[dict]:
        async with self.conn.execute(sql, args) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def run(self, sql: str, args: tuple = ()) -> int:
        """A single write outside an explicit transaction (autocommit). Returns rowcount."""
        async with self.lock:
            cur = await self.conn.execute(sql, args)
            return cur.rowcount

    # ── seed ──
    async def seed(self, pharmacies: list[dict], meds: list[dict], now_ms: int) -> bool:
        """Fill an empty database with the fictional demo city. Returns False when data already exists."""
        if await self.one("SELECT 1 FROM pharmacies LIMIT 1"):
            return False
        async with self.tx() as c:
            for p in pharmacies:
                await c.execute(
                    "INSERT INTO pharmacies (id, name, district, lat, lon, hours, off, phone, address_uz, address_ru) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (p["id"], p["name"], p["district"], p["lat"], p["lon"], p["hours"], json.dumps(p["off"]),
                     p["phone"], p["address"]["uz"], p["address"]["ru"]))
            for r in stock_rows(pharmacies, meds, now_ms):
                await c.execute(
                    "INSERT INTO stock (pharmacy_id, med_id, qty, price, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (r["pharmacy_id"], r["med_id"], r["qty"], r["price"], r["updated_ms"]))
        return True
