"""Run everything in one process: ``python -m navbatchi``.

* the Telegram bot (long polling),
* the aiohttp server with the Mini App and its API,
* the scheduler loop (expired reservations, price alerts; state lives in SQLite, so a restart loses nothing).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import MenuButtonWebApp, WebAppInfo
from aiohttp import web

from . import scheduler
from .bot.notify import Notifier
from .bot.setup import BotConfig, build_dispatcher
from .config import Settings
from .data import Catalog
from .db import Database
from .service import Service
from .web import make_app

log = logging.getLogger("navbatchi")


async def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = Settings.from_env()
    catalog = Catalog.default()
    db = await Database.open(cfg.db_path)
    if cfg.seed_demo and await db.seed(catalog.pharmacies, catalog.meds, int(time.time() * 1000)):
        log.info("seeded the fictional demo city (%d pharmacies)", len(catalog.pharmacies))
    service = Service(db, catalog, admins=cfg.admin_ids, invite_hours=cfg.invite_hours)
    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    me = await bot.get_me()
    dp = build_dispatcher(service, bot, BotConfig(me.username or "", cfg.webapp_url), cfg.rate_per_minute)
    notifier = Notifier(bot, service)
    if cfg.webapp_url:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Xarita", web_app=WebAppInfo(
            url=cfg.webapp_url)))

    app = make_app(service, cfg.bot_token, notifier, cfg.initdata_max_age, cfg.rate_per_minute,
                   bot_username=me.username or "")
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, cfg.host, cfg.port).start()
    log.info("Mini App and API on http://%s:%s/webapp/  bot: @%s", cfg.host, cfg.port, me.username)
    loop = asyncio.create_task(scheduler.loop(service, notifier, cfg.scheduler_interval))
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        loop.cancel()
        await runner.cleanup()
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
