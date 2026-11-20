"""Messages the bot sends on its own: a new reservation for the pharmacist, "picked up" and "expired" for the
customer, and fired price alerts. Used by the bot, the Mini App API and the scheduler loop."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..core.geo import haversine_m
from ..data import med_label
from ..i18n import clock, dist, price, t
from .cb import Ph

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot: Bot, service) -> None:
        self.bot, self.svc = bot, service

    async def _send(self, uid: int, text: str, markup=None) -> None:
        try:
            await self.bot.send_message(uid, text, reply_markup=markup, disable_web_page_preview=True)
        except TelegramAPIError as err:  # blocked the bot, deleted account...
            log.info("could not notify %s: %s", uid, err)

    async def _lang(self, uid: int) -> str:
        return ((await self.svc.user(uid)) or {}).get("lang", "uz")

    async def new_reservation(self, res: dict) -> None:
        med = self.svc.catalog.med(res["med_id"])
        staff = await self.svc.db.all("SELECT id, lang FROM users WHERE role = 'pharmacist' AND pharmacy_id = ?",
                                      (res["pharmacy_id"],))
        for s in staff:
            await self._send(s["id"], t(s["lang"], "pharm.new_res", med=med_label(med, s["lang"]), qty=res["qty"],
                                        code=res["code"], until=clock(res["expires_at"])))

    async def picked(self, res: dict) -> None:
        lang = await self._lang(res["user_id"])
        med = self.svc.catalog.med(res["med_id"])
        await self._send(res["user_id"], t(lang, "res.picked", med=med_label(med, lang), qty=res["qty"]))

    async def expired(self, res: dict) -> None:
        lang = await self._lang(res["user_id"])
        med = self.svc.catalog.med(res["med_id"])
        ph = await self.svc.db.one("SELECT name FROM pharmacies WHERE id = ?", (res["pharmacy_id"],))
        await self._send(res["user_id"], t(lang, "res.expired", med=med_label(med, lang), qty=res["qty"],
                                           pharmacy=(ph or {}).get("name", "")))

    async def alert(self, a: dict) -> None:
        lang = await self._lang(a["user_id"])
        med = self.svc.catalog.med(a["med_id"])
        ph = await self.svc.db.one("SELECT name, lat, lon FROM pharmacies WHERE id = ?", (a["pharmacy_id"],))
        if med is None or ph is None:
            return
        meters = haversine_m(a["lat"], a["lon"], ph["lat"], ph["lon"])
        button = InlineKeyboardButton(text=t(lang, "btn.view"),
                                      callback_data=Ph(med=a["med_id"], pid=a["pharmacy_id"], w=50, o=0).pack())
        await self._send(a["user_id"], t(lang, "alert.fired", med=med_label(med, lang), price=price(a["price"]),
                                         pharmacy=ph["name"], dist=dist(lang, meters)),
                         InlineKeyboardMarkup(inline_keyboard=[[button]]))
