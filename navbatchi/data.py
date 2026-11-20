"""The medicine catalog, districts and the fictional pharmacies, read from shared/data/*.json.

The bot, the API, the Mini App and the browser demo all read these same files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "shared" / "data"
UNITS_RU = {"mg": "мг", "mcg": "мкг", "g": "г", "ml": "мл"}


def load(name: str) -> list[dict]:
    with open(DATA_DIR / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


@dataclass
class Catalog:
    meds: list[dict]
    districts: list[dict]
    pharmacies: list[dict]
    by_id: dict[str, dict] = field(init=False)
    district_ids: set[str] = field(init=False)

    def __post_init__(self) -> None:
        self.by_id = {m["id"]: m for m in self.meds}
        self.district_ids = {d["id"] for d in self.districts}

    @classmethod
    def default(cls) -> Catalog:
        return cls(load("meds"), load("districts"), load("pharmacies"))

    def med(self, med_id: str) -> dict | None:
        return self.by_id.get(med_id) if isinstance(med_id, str) else None

    def district(self, did: str) -> dict | None:
        return next((d for d in self.districts if d["id"] == did), None)


def strength(med: dict, lang: str) -> str:
    """ "500 mg" -> "500 мг" in Russian; "0.05%" -> "0,05%" (comma decimals)."""
    s = med["strength"].replace(".", ",")
    if lang == "ru":
        num, _, unit = s.partition(" ")
        if unit in UNITS_RU:
            s = f"{num} {UNITS_RU[unit]}"
    return s


def med_label(med: dict, lang: str) -> str:
    """ "Paratsetamol 500 mg" — the name people see on buttons and cards."""
    return f"{med['name'].get(lang, med['name']['uz'])} {strength(med, lang)}"
