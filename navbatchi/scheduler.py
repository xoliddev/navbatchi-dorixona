"""Background loop: release expired reservations and fire price alerts.

Both steps are idempotent (conditional UPDATEs), so a crash, a restart or two loops running at once never release
stock twice or send an alert twice.
"""

from __future__ import annotations

import asyncio
import logging

from .service import Service

log = logging.getLogger(__name__)


async def tick(service: Service, notifier) -> dict:
    expired = await service.expire_due()
    for res in expired:
        await notifier.expired(res)
    fired = await service.run_alerts()
    for alert in fired:
        await notifier.alert(alert)
    return {"expired": len(expired), "alerts": len(fired)}


async def loop(service: Service, notifier, interval: float = 30.0) -> None:
    while True:
        try:
            await tick(service, notifier)
        except Exception:  # keep the loop alive; the next tick retries
            log.exception("scheduler tick failed")
        await asyncio.sleep(interval)
