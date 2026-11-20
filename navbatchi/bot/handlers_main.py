"""/start (with pharmacist invite links), the main menu, language, location and free-text search."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from ..common import Refused
from ..data import Catalog
from ..i18n import t
from . import views
from .cb import Dist, Flow, Nav
from .setup import show

router = Router(name="main")
fallback = Router(name="fallback")
DISTRICTS = {d["id"] for d in Catalog.default().districts}


async def menu(event, svc, me: int, cfg, hello: bool = False) -> None:
    user = {**(await svc.user(me)), "admin": me in svc.admins}
    await show(event, views.main_menu(user["lang"], user, cfg.webapp_url, hello))


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, state: FSMContext, svc, me, lang, cfg) -> None:
    await state.clear()
    arg = (command.args or "").strip()
    if arg.startswith("inv_"):
        ph = await svc.redeem_invite(me, arg[4:])
        await message.answer(t(lang, "pharm.joined", pharmacy=ph["name"]))
    await menu(message, svc, me, cfg, hello=not arg)


@router.callback_query(Nav.filter(F.to == "menu"))
async def nav_menu(cq: CallbackQuery, state: FSMContext, svc, me, cfg) -> None:
    await state.clear()
    await menu(cq, svc, me, cfg)


@router.callback_query(Nav.filter(F.to == "lang"))
async def nav_lang(cq: CallbackQuery, svc, me, lang, cfg) -> None:
    await svc.set_lang(me, "ru" if lang == "uz" else "uz")
    await menu(cq, svc, me, cfg)


@router.callback_query(Nav.filter(F.to == "search"))
async def nav_search(cq: CallbackQuery, state: FSMContext, lang) -> None:
    await state.clear()
    await show(cq, views.search_ask(lang))


@router.callback_query(Nav.filter(F.to == "loc"))
async def nav_loc(cq: CallbackQuery, svc, user, lang) -> None:
    await show(cq, views.loc_ask(lang, svc.catalog.districts, user))
    await cq.message.answer(t(lang, "loc.keyboard"), reply_markup=views.location_keyboard(lang))


async def after_location(event, state: FSMContext, svc, me, lang, cfg) -> None:
    """Continue where the user was: the medicine they picked before we knew where they are."""
    from .handlers_offers import offers_screen

    user = await svc.user(me)
    pending = (await state.get_data()).get("pending_med")
    if pending:
        await state.update_data(pending_med=None)
        await offers_screen(event, svc, user, lang, pending, 50, 0)
        return
    district = svc.catalog.district(user["district"])["name"][lang]
    if isinstance(event, Message):
        await event.answer(t(lang, "loc.saved", district=district), reply_markup=ReplyKeyboardRemove())
    else:
        await event.answer(t(lang, "loc.saved", district=district))
    await menu(event if isinstance(event, Message) else event.message, svc, me, cfg)


@router.callback_query(Dist.filter(F.did.in_(DISTRICTS)))
async def pick_district(cq: CallbackQuery, callback_data: Dist, state: FSMContext, svc, me, lang, cfg) -> None:
    await svc.set_district(me, callback_data.did)
    await after_location(cq, state, svc, me, lang, cfg)


@router.message(F.location, ~StateFilter(Flow.admin_point))
async def got_location(message: Message, state: FSMContext, svc, me, lang, cfg) -> None:
    await svc.set_location(me, message.location.latitude, message.location.longitude)
    await after_location(message, state, svc, me, lang, cfg)


@router.message(StateFilter(None), F.text)
async def free_text(message: Message, svc, lang) -> None:
    """Any text outside a step is a search: the user does not need to press "Search" first."""
    q = message.text.strip()
    if q.startswith("/"):
        raise Refused("stale")
    await show(message, views.search_results(lang, q[:64], svc.search(q)))


@fallback.callback_query()
async def stale(cq: CallbackQuery, lang) -> None:
    await cq.answer(t(lang, "err.stale"), show_alert=True)


@fallback.message()
async def other(message: Message, svc, me, cfg) -> None:
    await menu(message, svc, me, cfg)
