"""Callback data. aiogram parses and type-checks every field (ints stay ints); handlers then filter the allowed
values (known medicine ids, districts, slider positions) and anything else falls through to the "stale button"
handler. Nothing in callback data is trusted for authorization: the service re-checks every action."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import State, StatesGroup

NAV = {"menu", "search", "my", "alerts", "loc", "lang", "pharm", "admin", "code", "held", "csv_in", "csv_out",
       "addph", "invite"}
WEIGHTS = {0, 50, 100}
FLAGS = {0, 1}
HOUR_PRESETS = ("24/7", "08:00-22:00", "09:00-21:00", "08:00-02:00")


class Nav(CallbackData, prefix="n"):
    to: str


class Med(CallbackData, prefix="m"):
    med: str


class Off(CallbackData, prefix="o"):
    med: str
    w: int  # slider: 0 nearest .. 100 cheapest
    o: int  # 1 = "navbatchi": open now only


class Ph(CallbackData, prefix="p"):
    med: str
    pid: int
    w: int
    o: int


class Qty(CallbackData, prefix="q"):
    med: str
    pid: int
    n: int  # 0 = ask how many


class Res(CallbackData, prefix="r"):
    rid: int


class Dist(CallbackData, prefix="d"):
    did: str


class Al(CallbackData, prefix="a"):
    med: str
    km: int  # 0 = ask the radius


class AlAny(CallbackData, prefix="y"):
    ok: int


class AlDel(CallbackData, prefix="x"):
    aid: int


class Stk(CallbackData, prefix="s"):
    med: str


class Page(CallbackData, prefix="g"):
    n: int


class Inv(CallbackData, prefix="i"):
    pid: int


class Hrs(CallbackData, prefix="h"):
    i: int


class Flow(StatesGroup):
    alert_price = State()
    pharm_code = State()
    pharm_stock = State()
    pharm_csv = State()
    admin_name = State()
    admin_address = State()
    admin_point = State()
    admin_hours = State()
    admin_phone = State()
