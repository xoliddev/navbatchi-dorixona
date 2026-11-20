"""Pharmacist and admin screens."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton as Btn

from ..data import med_label
from ..i18n import clock, price, t
from .cb import HOUR_PRESETS, Hrs, Inv, Nav, Page, Stk
from .views import back, kb

PAGE = 8


def pharm_menu(lang: str, pharmacy: dict, held: int) -> tuple:
    rows = [[Btn(text=t(lang, "pharm.btn_code"), callback_data=Nav(to="code").pack())],
            [Btn(text=t(lang, "pharm.btn_held", n=held), callback_data=Nav(to="held").pack())],
            [Btn(text=t(lang, "pharm.btn_stock"), callback_data=Page(n=0).pack())],
            [Btn(text=t(lang, "pharm.btn_csv_in"), callback_data=Nav(to="csv_in").pack()),
             Btn(text=t(lang, "pharm.btn_csv_out"), callback_data=Nav(to="csv_out").pack())],
            back(lang, Nav(to="menu").pack())]
    return t(lang, "pharm.menu", pharmacy=pharmacy["name"], held=held), kb(rows)


def ask(lang: str, key: str, to: str = "pharm") -> tuple:
    return t(lang, key), kb([back(lang, Nav(to=to).pack())])


def pharm_held(lang: str, items: list[tuple[dict, dict]]) -> tuple:
    held = [(r, m) for r, m in items if r["status"] == "held"]
    if not held:
        return t(lang, "pharm.held_empty"), kb([back(lang, Nav(to="pharm").pack())])
    lines = [t(lang, "pharm.held"), ""]
    for r, m in held:
        lines.append(t(lang, "pharm.held_line", code=r["code"], med=med_label(m, lang), qty=r["qty"],
                       until=clock(r["expires_at"])))
    return "\n".join(lines), kb([[Btn(text=t(lang, "pharm.btn_code"), callback_data=Nav(to="code").pack())],
                                 back(lang, Nav(to="pharm").pack())])


def pharm_stock(lang: str, rows: list[tuple[dict, dict]], page: int) -> tuple:
    pages = max(1, -(-len(rows) // PAGE))
    page = min(max(page, 0), pages - 1)
    buttons = [[Btn(text=t(lang, "pharm.stock_btn", med=med_label(m, lang), price=price(r["price"]), qty=r["qty"]),
                    callback_data=Stk(med=r["med_id"]).pack())] for r, m in rows[page * PAGE:(page + 1) * PAGE]]
    nav = []
    if page > 0:
        nav.append(Btn(text="‹", callback_data=Page(n=page - 1).pack()))
    if page < pages - 1:
        nav.append(Btn(text="›", callback_data=Page(n=page + 1).pack()))
    return (t(lang, "pharm.stock", page=page + 1, pages=pages),
            kb([*buttons, nav, back(lang, Nav(to="pharm").pack())]))


def pharm_stock_item(lang: str, row: dict, med: dict) -> tuple:
    return (t(lang, "pharm.stock_item", med=med_label(med, lang), price=price(row["price"]), qty=row["qty"],
              reserved=row["reserved"]), kb([back(lang, Page(n=0).pack())]))


def admin_menu(lang: str, n: int) -> tuple:
    return t(lang, "admin.menu", n=n), kb([[Btn(text=t(lang, "admin.btn_add"), callback_data=Nav(to="addph").pack())],
                                          [Btn(text=t(lang, "admin.btn_invite"),
                                               callback_data=Nav(to="invite").pack())],
                                          back(lang, Nav(to="menu").pack())])


def admin_pick(lang: str, pharmacies: list[dict]) -> tuple:
    rows = [[Btn(text=f"#{p['id']} {p['name']}", callback_data=Inv(pid=p["id"]).pack())] for p in pharmacies[:40]]
    return t(lang, "admin.pick"), kb([*rows, back(lang, Nav(to="admin").pack())])


def admin_hours(lang: str) -> tuple:
    row = [Btn(text=h, callback_data=Hrs(i=i).pack()) for i, h in enumerate(HOUR_PRESETS)]
    return t(lang, "admin.ask_hours"), kb([row[:2], row[2:], back(lang, Nav(to="admin").pack())])
