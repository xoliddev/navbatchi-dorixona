"""Bulk stock import (CSV from Excel or Google Sheets) and a safe export.

Import is strict: size and row limits, whole numbers only, unknown medicines reported by line. Export guards
against spreadsheet formula injection: a cell that starts with = + - @ or a control character gets a leading '.
"""

from __future__ import annotations

from .money import PriceError, parse_price, parse_qty
from .text import words

MAX_BYTES = 64 * 1024
MAX_ROWS = 500
HEADERS = {
    "med": {"med", "id", "dori", "nomi", "name", "препарат", "лекарство", "название"},
    "price": {"price", "narx", "narxi", "цена"},
    "qty": {"qty", "soni", "miqdor", "miqdori", "количество", "кол-во", "остаток"},
}
_DANGER = ("=", "+", "-", "@", "\t", "\r", "\n")


class CsvError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def split_rows(text: str, sep: str) -> list[list[str]]:
    """Minimal RFC 4180 reader: quoted cells may hold the separator, doubled quotes and newlines."""
    rows: list[list[str]] = []
    row: list[str] = []
    cell = ""
    started = quoted = False
    i = 0
    while i < len(text):
        ch = text[i]
        if quoted:
            if ch == '"' and text[i + 1: i + 2] == '"':
                cell += '"'
                i += 1
            elif ch == '"':
                quoted = False
            else:
                cell += ch
        elif ch == '"' and cell == "":
            quoted = started = True
        elif ch == sep:
            row.append(cell)
            cell, started = "", True
        elif ch in "\r\n":
            if ch == "\r" and text[i + 1: i + 2] == "\n":
                i += 1
            row.append(cell)
            rows.append(row)
            row, cell, started = [], "", False
        else:
            cell += ch
            started = True
        i += 1
    if cell or row or started:
        row.append(cell)
        rows.append(row)
    return [r for r in rows if any(c.strip() for c in r)]


def resolve_med(meds: list[dict], text: str) -> str | None:
    """A medicine id, or a name that matches exactly one product (any script, dose optional)."""
    text = text.strip()
    if any(m["id"] == text for m in meds):
        return text
    key = [w for w in words(text) if not w.isdigit() and w not in ("mg", "mkg", "mcg", "g", "ml")]
    if not key:
        return None
    found = [m["id"] for m in meds if key in (words(m["name"]["uz"]), words(m["name"]["ru"]))]
    digits = [w for w in words(text) if w.isdigit()]
    if digits:
        found = [i for i in found if all(d in words(next(m for m in meds if m["id"] == i)["strength"]) for d in digits)]
    return found[0] if len(found) == 1 else None


def parse_stock(raw: bytes | str, meds: list[dict]) -> dict:
    """-> {"rows": [{"med", "price", "qty"}], "errors": [{"line", "code"}]}. Raises CsvError for the whole file."""
    if isinstance(raw, bytes):
        if len(raw) > MAX_BYTES:
            raise CsvError("too_big")
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError as err:
            raise CsvError("encoding") from err
    elif len(raw.encode("utf-8")) > MAX_BYTES:
        raise CsvError("too_big")
    text = raw.lstrip("\ufeff")
    first = text.split("\n", 1)[0]
    sep = ";" if first.count(";") > first.count(",") else ","
    rows = split_rows(text, sep)
    if not rows:
        raise CsvError("empty")
    head = [c.strip().lower() for c in rows[0]]
    cols = {}
    for name, options in HEADERS.items():
        idx = [i for i, c in enumerate(head) if c in options]
        if len(idx) != 1:
            raise CsvError("header")
        cols[name] = idx[0]
    body = rows[1:]
    if len(body) > MAX_ROWS:
        raise CsvError("too_many_rows")
    out: dict[str, dict] = {}
    errors = []
    for n, row in enumerate(body, start=2):
        if len(row) <= max(cols.values()):
            errors.append({"line": n, "code": "columns"})
            continue
        med = resolve_med(meds, row[cols["med"]][:80])
        if med is None:
            errors.append({"line": n, "code": "med"})
            continue
        try:
            price = parse_price(row[cols["price"]][:20])
        except PriceError:
            errors.append({"line": n, "code": "price"})
            continue
        try:
            qty = parse_qty(row[cols["qty"]][:10])
        except PriceError:
            errors.append({"line": n, "code": "qty"})
            continue
        if med in out:
            errors.append({"line": n, "code": "dup"})
            continue
        out[med] = {"med": med, "price": price, "qty": qty}
    return {"rows": list(out.values()), "errors": errors}


def safe_cell(value: object) -> str:
    s = str(value)
    if s.startswith(_DANGER):
        s = "'" + s
    if any(c in s for c in ',;"\n\r'):
        s = '"' + s.replace('"', '""') + '"'
    return s


def to_csv(rows: list[list[object]]) -> str:
    return "".join(",".join(safe_cell(c) for c in row) + "\r\n" for row in rows)
