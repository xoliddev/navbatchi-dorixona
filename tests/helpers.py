"""Shared helpers: a seeded in-memory city, a clock the tests can move, and the people in the stories."""

from __future__ import annotations

from contextlib import asynccontextmanager

from navbatchi.data import Catalog
from navbatchi.db import Database
from navbatchi.service import Service

NOW = 1_795_000_000_000  # Wednesday 2026-11-18, 16:06 in Tashkent (the same moment as the shared vectors)
ADMIN, ALI, VALI, DILNOZA, OYBEK = 9001, 1001, 1002, 2002, 2006  # Dilnoza works at pharmacy 2, Oybek at 6
CENTRE = (41.3111, 69.2797)


class Clock:
    def __init__(self, start: int = NOW) -> None:
        self.now = start

    def __call__(self) -> int:
        return self.now

    def skip(self, minutes: float = 0, hours: float = 0, days: float = 0) -> None:
        self.now += int((minutes + hours * 60 + days * 1440) * 60_000)

    def set_local(self, hour: int, minute: int = 0) -> None:
        """Move forward to the next HH:MM in Tashkent."""
        target = hour * 60 + minute
        current = ((self.now + 5 * 3_600_000) // 60_000) % 1440
        self.now += ((target - current) % 1440 or 1440) * 60_000


class Seq:
    """Deterministic "random" numbers for pickup codes."""

    def __init__(self, values: list[int] | None = None) -> None:
        self.values = list(values or [])
        self.n = 0

    def __call__(self, bound: int) -> int:
        self.n += 1
        return self.values.pop(0) if self.values else (self.n * 104_729) % bound


@asynccontextmanager
async def service_env(clock: Clock | None = None, path: str = ":memory:", rng=None):
    clock = clock or Clock()
    catalog = Catalog.default()
    db = await Database.open(path)
    await db.seed(catalog.pharmacies, catalog.meds, clock())
    svc = Service(db, catalog, clock=clock, rng=rng or Seq(), admins=frozenset({ADMIN}))
    for uid, name in ((ADMIN, "Admin"), (ALI, "Ali"), (VALI, "Vali"), (DILNOZA, "Dilnoza"), (OYBEK, "Oybek")):
        await svc.touch_user(uid, name, "uz")
    await svc.set_location(ALI, *CENTRE)
    await svc.set_location(VALI, *CENTRE)
    for uid, pid in ((DILNOZA, 2), (OYBEK, 6)):
        await svc.redeem_invite(uid, await svc.create_invite(ADMIN, pid))
    try:
        yield svc, clock
    finally:
        await db.close()


async def stock(svc: Service, pid: int, med: str) -> dict:
    return await svc.db.one("SELECT * FROM stock WHERE pharmacy_id = ? AND med_id = ?", (pid, med))
