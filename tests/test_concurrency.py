"""No overselling: buyers racing for the last packs, on one connection and across two processes' connections."""

from __future__ import annotations

import asyncio

from navbatchi.data import Catalog
from navbatchi.db import Database
from navbatchi.service import Refused, Service

from .helpers import ALI, DILNOZA, VALI, Clock, Seq, service_env, stock

PARA = "paracetamol-500"


async def _try(svc: Service, uid: int, pid: int, qty: int = 1):
    try:
        return await svc.reserve(uid, pid, PARA, qty)
    except Refused as err:
        return err.code


async def test_two_buyers_race_for_the_last_pack():
    async with service_env() as (svc, _):
        await svc.set_stock(DILNOZA, PARA, 1, 5000)
        results = await asyncio.gather(_try(svc, ALI, 2), _try(svc, VALI, 2))
        assert sorted(r if isinstance(r, str) else "ok" for r in results) == ["ok", "stock"]
        row = await stock(svc, 2, PARA)
        assert (row["qty"], row["reserved"]) == (1, 1)


async def test_two_connections_never_oversell(tmp_path):
    """Two Database connections to one file behave like two server processes: SQLite's write lock plus the
    conditional UPDATE keep the total held at or below what is on the shelf."""
    path = str(tmp_path / "race.db")
    clock = Clock()
    async with service_env(clock, path=path) as (svc_a, _):
        await svc_a.set_stock(DILNOZA, PARA, 3, 5000)
        db_b = await Database.open(path)
        svc_b = Service(db_b, Catalog.default(), clock=clock, rng=Seq([7, 7, 7]))
        buyers = list(range(5001, 5011))
        for uid in buyers:
            await svc_a.touch_user(uid, f"U{uid}", "uz")
        try:
            calls = [_try(svc_a if i % 2 else svc_b, uid, 2) for i, uid in enumerate(buyers)]
            results = await asyncio.gather(*calls)
        finally:
            await db_b.close()
        ok = [r for r in results if not isinstance(r, str)]
        assert len(ok) == 3
        assert {r for r in results if isinstance(r, str)} == {"stock"}
        assert len({r["code"] for r in ok}) == 3  # codes stay unique per pharmacy even with a colliding generator
        row = await stock(svc_a, 2, PARA)
        assert (row["qty"], row["reserved"]) == (3, 3)


async def test_database_refuses_oversell_even_if_the_app_had_a_bug():
    async with service_env() as (svc, _):
        try:
            await svc.db.run("UPDATE stock SET reserved = qty + 1 WHERE pharmacy_id = 2 AND med_id = ?", (PARA,))
        except Exception as err:  # sqlite3.IntegrityError: CHECK constraint failed
            assert "CHECK" in str(err)
        else:
            raise AssertionError("the CHECK constraint must refuse reserved > qty")
