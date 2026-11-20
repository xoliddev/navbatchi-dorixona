"""Medicine -> ranked pharmacies -> pharmacy card -> reservation; my reservations; price alerts."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..common import Refused
from ..core.alerts import RADII_KM
from ..data import Catalog, med_label
from ..i18n import plain, t
from . import views
from .cb import FLAGS, WEIGHTS, Al, AlAny, AlDel, Flow, Med, Nav, Off, Ph, Qty, Res
from .setup import show

router = Router(name="offers")
MEDS = {m["id"] for m in Catalog.default().meds}
TYPED = F.text & ~F.text.startswith("/")


async def offers_screen(event, svc, user, lang: str, med_id: str, w: int, o: int) -> None:
    res = await svc.offers(med_id, user["lat"], user["lon"], weight=w, open_only=bool(o))
    for a in res["analogs"]:
        a["label"] = med_label(svc.catalog.med(a["id"]), lang)
    district = svc.catalog.district(user["district"])["name"][lang]
    await show(event, views.offers(lang, res, district, w, o))


@router.callback_query(Med.filter(F.med.in_(MEDS)))
async def pick_med(cq: CallbackQuery, callback_data: Med, state: FSMContext, svc, user, lang) -> None:
    if user["lat"] is None:
        await state.update_data(pending_med=callback_data.med)
        await show(cq, views.loc_ask(lang, svc.catalog.districts, user))
        await cq.message.answer(t(lang, "loc.keyboard"), reply_markup=views.location_keyboard(lang))
        return
    await offers_screen(cq, svc, user, lang, callback_data.med, 50, 0)


@router.callback_query(Off.filter(F.med.in_(MEDS) & F.w.in_(WEIGHTS) & F.o.in_(FLAGS)))
async def show_offers(cq: CallbackQuery, callback_data: Off, svc, user, lang) -> None:
    if user["lat"] is None:
        raise Refused("no_location")
    await offers_screen(cq, svc, user, lang, callback_data.med, callback_data.w, callback_data.o)


@router.callback_query(Ph.filter(F.med.in_(MEDS) & F.w.in_(WEIGHTS) & F.o.in_(FLAGS)))
async def show_card(cq: CallbackQuery, callback_data: Ph, svc, user, lang) -> None:
    if user["lat"] is None:
        raise Refused("no_location")
    d = callback_data
    item = await svc.offer_at(d.med, d.pid, user["lat"], user["lon"])
    await show(cq, views.card(lang, item, svc.med(d.med), d.w, d.o, svc.now()))


@router.callback_query(Qty.filter(F.med.in_(MEDS) & (F.n >= 0) & (F.n <= 5)))
async def reserve(cq: CallbackQuery, callback_data: Qty, svc, me, user, lang, notifier) -> None:
    d = callback_data
    med = svc.med(d.med)
    pharmacy = await svc.pharmacy(d.pid)
    if d.n == 0:
        if med["rx"]:
            raise Refused("rx")
        item = await svc.offer_at(d.med, d.pid, user["lat"] or 0, user["lon"] or 0)
        if item["available"] <= 0:
            raise Refused("stock")
        await show(cq, views.qty(lang, med, pharmacy, item["available"]))
        return
    res = await svc.reserve(me, d.pid, d.med, d.n)
    await show(cq, views.reserved(lang, res, med, pharmacy))
    await notifier.new_reservation(res)


async def my_screen(event, svc, me, lang) -> None:
    items = []
    for r in await svc.my_reservations(me):
        items.append((r, svc.med(r["med_id"]), await svc.pharmacy(r["pharmacy_id"])))
    await show(event, views.my_list(lang, items, svc.now()))


@router.callback_query(Nav.filter(F.to == "my"))
async def my(cq: CallbackQuery, svc, me, lang) -> None:
    await my_screen(cq, svc, me, lang)


@router.callback_query(Res.filter())
async def cancel(cq: CallbackQuery, callback_data: Res, svc, me, lang) -> None:
    await svc.cancel(me, callback_data.rid)
    await cq.answer(plain(t(lang, "res.cancelled")))
    await my_screen(cq, svc, me, lang)


@router.callback_query(Al.filter(F.med.in_(MEDS) & F.km.in_({0, *RADII_KM})))
async def alert_start(cq: CallbackQuery, callback_data: Al, state: FSMContext, svc, user, lang) -> None:
    med = svc.med(callback_data.med)
    if callback_data.km == 0:
        await state.clear()
        await show(cq, views.alert_radius(lang, med))
        return
    if user["lat"] is None:
        raise Refused("no_location")
    await state.set_state(Flow.alert_price)
    await state.update_data(alert_med=med["id"], alert_km=callback_data.km)
    await show(cq, views.alert_price(lang, med))


async def save_alert(event, state: FSMContext, svc, me, lang, price) -> None:
    data = await state.get_data()
    if not data.get("alert_med"):
        raise Refused("stale")
    alert = await svc.add_alert(me, data["alert_med"], data["alert_km"], price)
    await state.clear()
    await show(event, views.alert_ok(lang, alert, svc.med(alert["med_id"])))


@router.callback_query(AlAny.filter(F.ok == 1), StateFilter(Flow.alert_price))
async def alert_any(cq: CallbackQuery, state: FSMContext, svc, me, lang) -> None:
    await save_alert(cq, state, svc, me, lang, None)


@router.message(StateFilter(Flow.alert_price), TYPED)
async def alert_typed(message: Message, state: FSMContext, svc, me, lang) -> None:
    await save_alert(message, state, svc, me, lang, message.text.strip()[:20])


async def alerts_screen(event, svc, me, lang) -> None:
    items = [(a, svc.med(a["med_id"])) for a in await svc.my_alerts(me)]
    await show(event, views.alerts_list(lang, items))


@router.callback_query(Nav.filter(F.to == "alerts"))
async def alerts(cq: CallbackQuery, state: FSMContext, svc, me, lang) -> None:
    await state.clear()
    await alerts_screen(cq, svc, me, lang)


@router.callback_query(AlDel.filter())
async def alert_delete(cq: CallbackQuery, callback_data: AlDel, svc, me, lang) -> None:
    await svc.delete_alert(me, callback_data.aid)
    await alerts_screen(cq, svc, me, lang)
