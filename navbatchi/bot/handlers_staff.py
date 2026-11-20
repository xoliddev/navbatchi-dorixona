"""Pharmacist panel (own pharmacy only: the service looks it up, it never comes from the button) and admin."""

from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..common import Refused
from ..core.csvio import MAX_BYTES
from ..data import Catalog, med_label
from ..i18n import price, t
from . import views_staff as vs
from .cb import HOUR_PRESETS, Flow, Hrs, Inv, Nav, Page, Stk
from .setup import show

router = Router(name="staff")
MEDS = {m["id"] for m in Catalog.default().meds}
TYPED = F.text & ~F.text.startswith("/")
POINT = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


async def pharm_home(event, state: FSMContext, svc, me, lang) -> None:
    await state.clear()
    pid = await svc.pharmacy_of(me)
    held = [r for r in await svc.pharm_reservations(me) if r["status"] == "held"]
    await show(event, vs.pharm_menu(lang, await svc.pharmacy(pid), len(held)))


@router.callback_query(Nav.filter(F.to == "pharm"))
async def pharm(cq: CallbackQuery, state: FSMContext, svc, me, lang) -> None:
    await pharm_home(cq, state, svc, me, lang)


@router.callback_query(Nav.filter(F.to == "code"))
async def code_ask(cq: CallbackQuery, state: FSMContext, svc, me, lang) -> None:
    await svc.pharmacy_of(me)
    await state.set_state(Flow.pharm_code)
    await show(cq, vs.ask(lang, "pharm.code_ask"))


@router.message(StateFilter(Flow.pharm_code), TYPED)
async def code_typed(message: Message, state: FSMContext, svc, me, lang, notifier) -> None:
    res = await svc.confirm_code(me, message.text)
    row = await svc.db.one("SELECT qty FROM stock WHERE pharmacy_id = ? AND med_id = ?",
                           (res["pharmacy_id"], res["med_id"]))
    await message.answer(t(lang, "pharm.code_ok", med=med_label(svc.med(res["med_id"]), lang), qty=res["qty"],
                           total=price(res["qty"] * res["price"]), left=row["qty"]))
    await notifier.picked(res)
    await pharm_home(message, state, svc, me, lang)


@router.callback_query(Nav.filter(F.to == "held"))
async def held(cq: CallbackQuery, svc, me, lang) -> None:
    items = [(r, svc.med(r["med_id"])) for r in await svc.pharm_reservations(me)]
    await show(cq, vs.pharm_held(lang, items))


@router.callback_query(Page.filter((F.n >= 0) & (F.n < 100)))
async def stock_page(cq: CallbackQuery, callback_data: Page, state: FSMContext, svc, me, lang) -> None:
    await state.clear()
    rows = [(r, svc.med(r["med_id"])) for r in await svc.stock_list(me) if r["med_id"] in MEDS]
    await show(cq, vs.pharm_stock(lang, rows, callback_data.n))


@router.callback_query(Stk.filter(F.med.in_(MEDS)))
async def stock_item(cq: CallbackQuery, callback_data: Stk, state: FSMContext, svc, me, lang) -> None:
    rows = {r["med_id"]: r for r in await svc.stock_list(me)}
    row = rows.get(callback_data.med) or {"price": 0, "qty": 0, "reserved": 0}
    await state.set_state(Flow.pharm_stock)
    await state.update_data(stock_med=callback_data.med)
    await show(cq, vs.pharm_stock_item(lang, row, svc.med(callback_data.med)))


@router.message(StateFilter(Flow.pharm_stock), TYPED)
async def stock_typed(message: Message, state: FSMContext, svc, me, lang) -> None:
    m = re.fullmatch(r"\s*([\d ]{3,12}?)\s+(\d{1,6})\s*", message.text[:40])
    if not m:
        await message.answer(t(lang, "pharm.stock_format"))
        return
    med_id = (await state.get_data()).get("stock_med")
    row = await svc.set_stock(me, med_id, m.group(2), m.group(1))
    await message.answer(t(lang, "pharm.stock_saved", med=med_label(svc.med(med_id), lang), price=price(row["price"]),
                           qty=row["qty"]))
    await pharm_home(message, state, svc, me, lang)


@router.callback_query(Nav.filter(F.to == "csv_in"))
async def csv_ask(cq: CallbackQuery, state: FSMContext, svc, me, lang) -> None:
    await svc.pharmacy_of(me)
    await state.set_state(Flow.pharm_csv)
    await show(cq, vs.ask(lang, "pharm.csv_ask"))


@router.message(StateFilter(Flow.pharm_csv), F.document)
async def csv_file(message: Message, state: FSMContext, svc, me, lang) -> None:
    doc = message.document
    if not (doc.file_name or "").lower().endswith(".csv"):
        raise Refused("csv_file")
    if (doc.file_size or 0) > MAX_BYTES:
        raise Refused("csv_too_big")
    await svc.pharmacy_of(me)
    buf = await message.bot.download(doc)
    res = await svc.import_csv(me, buf.read(MAX_BYTES + 1))
    await message.answer(t(lang, "pharm.csv_ok", n=res["updated"]))
    if res["errors"]:
        lines = ", ".join(str(e["line"] or e.get("med")) for e in res["errors"][:20])
        await message.answer(t(lang, "pharm.csv_errors", lines=lines))
    await pharm_home(message, state, svc, me, lang)


@router.callback_query(Nav.filter(F.to == "csv_out"))
async def csv_out(cq: CallbackQuery, svc, me, lang) -> None:
    data = (await svc.export_csv(me)).encode("utf-8-sig")
    await cq.answer()
    await cq.bot.send_document(me, BufferedInputFile(data, filename="stock.csv"), caption=t(lang, "pharm.csv_file"))


# ── admin ──
@router.callback_query(Nav.filter(F.to == "admin"))
async def admin(cq: CallbackQuery, state: FSMContext, svc, me, lang) -> None:
    await state.clear()
    svc.require_admin(me)
    await show(cq, vs.admin_menu(lang, len(await svc.list_pharmacies())))


@router.callback_query(Nav.filter(F.to == "invite"))
async def invite_pick(cq: CallbackQuery, svc, me, lang) -> None:
    svc.require_admin(me)
    await show(cq, vs.admin_pick(lang, await svc.list_pharmacies()))


@router.callback_query(Inv.filter())
async def invite(cq: CallbackQuery, callback_data: Inv, svc, me, lang, cfg) -> None:
    token = await svc.create_invite(me, callback_data.pid)
    ph = await svc.pharmacy(callback_data.pid)
    link = f"https://t.me/{cfg.bot_username}?start=inv_{token}"
    await show(cq, (t(lang, "admin.invite", pharmacy=ph["name"], hours=svc.invite_hours, link=link),
                    vs.kb([vs.back(lang, Nav(to="admin").pack())])))


STEPS = [(Flow.admin_name, "name", "admin.ask_address", Flow.admin_address),
         (Flow.admin_address, "address", "admin.ask_point", Flow.admin_point)]


@router.callback_query(Nav.filter(F.to == "addph"))
async def add_start(cq: CallbackQuery, state: FSMContext, svc, me, lang) -> None:
    svc.require_admin(me)
    await state.set_state(Flow.admin_name)
    await show(cq, vs.ask(lang, "admin.ask_name", "admin"))


@router.message(StateFilter(Flow.admin_name, Flow.admin_address), TYPED)
async def add_text(message: Message, state: FSMContext, svc, me, lang) -> None:
    svc.require_admin(me)
    current = await state.get_state()
    for st, field, next_key, next_state in STEPS:
        if current == st.state:
            await state.update_data(**{field: message.text[:160]})
            await state.set_state(next_state)
            await show(message, vs.ask(lang, next_key, "admin"))
            return


@router.message(StateFilter(Flow.admin_point), F.location | TYPED)
async def add_point(message: Message, state: FSMContext, svc, me, lang) -> None:
    svc.require_admin(me)
    if message.location:
        lat, lon = message.location.latitude, message.location.longitude
    else:
        m = POINT.match(message.text[:40])
        if not m:
            raise Refused("location")
        lat, lon = float(m.group(1)), float(m.group(2))
    await state.update_data(lat=lat, lon=lon)
    await state.set_state(Flow.admin_hours)
    await show(message, vs.admin_hours(lang))


async def hours_chosen(event, state: FSMContext, lang, hours: str) -> None:
    await state.update_data(hours=hours)
    await state.set_state(Flow.admin_phone)
    await show(event, vs.ask(lang, "admin.ask_phone", "admin"))


@router.callback_query(Hrs.filter((F.i >= 0) & (F.i < len(HOUR_PRESETS))), StateFilter(Flow.admin_hours))
async def add_hours_btn(cq: CallbackQuery, callback_data: Hrs, state: FSMContext, lang) -> None:
    await hours_chosen(cq, state, lang, HOUR_PRESETS[callback_data.i])


@router.message(StateFilter(Flow.admin_hours), TYPED)
async def add_hours_typed(message: Message, state: FSMContext, lang) -> None:
    await hours_chosen(message, state, lang, message.text.strip()[:11])


@router.message(StateFilter(Flow.admin_phone), TYPED)
async def add_phone(message: Message, state: FSMContext, svc, me, lang) -> None:
    d = await state.get_data()
    pid = await svc.add_pharmacy(me, d.get("name"), d.get("address"), d.get("lat"), d.get("lon"), d.get("hours"),
                                 message.text)
    ph = await svc.pharmacy(pid)
    await state.clear()
    district = svc.catalog.district(ph["district"])["name"][lang]
    await show(message, (t(lang, "admin.added", name=ph["name"], id=pid, district=district),
                         vs.admin_menu(lang, len(await svc.list_pharmacies()))[1]))
