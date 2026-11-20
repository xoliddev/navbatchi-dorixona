"""Settings from environment variables (see .env.example). Nothing secret has a default."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader so beginners do not need extra packages. Real env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _ids(text: str) -> frozenset[int]:
    out = set()
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if part:
            if not part.isdigit():
                raise SystemExit(f"ADMIN_IDS must be numeric Telegram user ids, got {part!r}")
            out.add(int(part))
    return frozenset(out)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    webapp_url: str = ""
    db_path: str = "data/dorixona.db"
    host: str = "0.0.0.0"  # noqa: S104 - the container must listen on all interfaces
    port: int = 8080
    admin_ids: frozenset[int] = field(default_factory=frozenset)
    seed_demo: bool = True
    initdata_max_age: int = 3600
    rate_per_minute: int = 30
    scheduler_interval: int = 30
    invite_hours: int = 72

    @classmethod
    def from_env(cls, dotenv: Path | None = Path(".env")) -> Settings:
        if dotenv is not None:
            _load_dotenv(dotenv)
        token = os.environ.get("BOT_TOKEN", "").strip()
        if not token or ":" not in token:
            raise SystemExit("BOT_TOKEN is missing. Copy .env.example to .env and paste the token from @BotFather.")
        url = os.environ.get("WEBAPP_URL", "").strip()
        if url and not url.startswith("https://"):
            raise SystemExit("WEBAPP_URL must start with https:// (Telegram opens Mini Apps only over HTTPS).")
        env = os.environ.get
        return cls(
            bot_token=token,
            webapp_url=url,
            db_path=env("DB_PATH", cls.db_path),
            host=env("HOST", cls.host),
            port=int(env("PORT", cls.port)),
            admin_ids=_ids(env("ADMIN_IDS", "")),
            seed_demo=env("SEED_DEMO", "1").strip() not in ("0", "false", "no"),
            initdata_max_age=int(env("INITDATA_MAX_AGE", cls.initdata_max_age)),
            rate_per_minute=int(env("RATE_PER_MINUTE", cls.rate_per_minute)),
            scheduler_interval=int(env("SCHEDULER_INTERVAL", cls.scheduler_interval)),
            invite_hours=int(env("INVITE_HOURS", cls.invite_hours)),
        )
