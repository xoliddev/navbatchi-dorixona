"""Regenerate shared/test_vectors.json from the Python core.

pytest checks that the file is up to date (so the Python core and the vectors never drift apart), and
``node --test`` checks the JS port against the very same vectors.

    python scripts/make_vectors.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from navbatchi.core import alerts, catalog, csvio, geo, hours, money, rank, reserve, seedgen, text  # noqa: E402

OUT = ROOT / "shared" / "test_vectors.json"
NOW = 1_795_000_000_000  # 2026-11-18 11:06 UTC (16:06 in Tashkent), a Wednesday


def load(name: str):
    with open(ROOT / "shared" / "data" / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def err(fn, *args):
    try:
        return {"ok": fn(*args)}
    except (reserve.ReserveError, csvio.CsvError) as e:
        return {"error": e.code}
    except (money.PriceError, hours.HoursError):
        return {"error": "invalid"}


def offers_for(med_id: str, rows: list[dict], phs: dict[int, dict]) -> list[dict]:
    out = []
    for r in rows:
        if r["med_id"] != med_id:
            continue
        p = phs[r["pharmacy_id"]]
        out.append({"pharmacy_id": p["id"], "price": r["price"], "available": r["qty"], "lat": p["lat"], "lon": p["lon"],
                    "hours": p["hours"], "off": p["off"]})
    return out


def build() -> dict:
    meds, phs_list = load("meds"), load("pharmacies")
    phs = {p["id"]: p for p in phs_list}
    rows = seedgen.stock_rows(phs_list, meds, NOW)
    v: dict = {"now": NOW}

    texts = ["Парацетамол", "paratsetamol", "paracetamol", "PARATSETAMOL 500", "Ibuprofen", "ибупрофен", "Xlorgeksidin",
             "chlorhexidine", "Хлоргексидин", "Seftriakson", "цефтриаксон", "ceftriaxone", "Amoksitsillin", "амоксициллин",
             "Navro'z", "Navroʻz", "g'alla", "ёд", "Юнусобод", "щука", "Ўзбекистон", "Қалампир", "Ғалаба", "Ҳаёт",
             "nitroglycerin", "Нитроглицерин", "azithromycin", "азитромицин", "a", "  ", "x-ray 2.0"]
    v["words"] = [{"in": t, "out": text.words(t)} for t in texts]
    pairs = [("parasetamol", "parasitamol"), ("abc", "acb"), ("kitten", "sitting"), ("", "abc"), ("ibuprofen", "ibuprfoen"),
             ("short", "muchlongerword"), ("seftriaxon", "seftriaxon")]
    v["distance"] = [{"a": a, "b": b, "limit": lim, "out": text.distance(a, b, lim)} for a, b in pairs for lim in (1, 2, 3)]

    queries = ["парацетамол", "paratsetamol", "paracetamol", "paratsitamol", "paraceamol", "paraset", "febrinol", "фебринол",
               "ибупрофен", "ibuprfen", "xlorgeksidin", "chlorhexidine", "hlorgeksidin", "vitamin c", "витамин с",
               "seftriakson", "ceftriaxone", "amoxicillin", "амоксициллин", "dorotaverin", "spazmolin", "artrogel",
               "diklofenak", "omeprazol 20", "omeprazol 40", "paratsetamol 500", "asd", "pa", "", "кислота", "kislota",
               "atsetilsalitsil", "loratadin", "лоратадин", "allerfin", "tsetirizin", "цетиризин", "nitroglitserin",
               "metamizol", "salbutamol", "сальбутамол", "azitromitsin", "a" * 200]
    v["search"] = [{"q": q, "out": catalog.search(meds, q)} for q in queries]
    v["analogs"] = [{"id": m["id"], "out": catalog.analogs(meds, m["id"])} for m in meds]
    mins: dict[str, int] = {}
    for r in rows:
        if r["qty"] > 0:
            mins[r["med_id"]] = min(mins.get(r["med_id"], r["price"]), r["price"])
    v["cheaper"] = [{"id": m["id"], "min": mins, "out": catalog.cheaper_analogs(meds, m["id"], mins)} for m in meds
                    if m["brand"]][:4]
    v["cheaper"].append({"id": "paracetamol-500", "min": {"febrinol-500": 100}, "out": catalog.cheaper_analogs(
        meds, "paracetamol-500", {"febrinol-500": 100})})

    pts = [(41.3111, 69.2797, p["lat"], p["lon"]) for p in phs_list] + [(0, 0, 0, 0), (41.3, 69.2, 41.3, 69.3),
                                                                        (-33.9, 151.2, 51.5, -0.12)]
    v["haversine"] = [{"p": list(p), "out": geo.haversine_m(*p)} for p in pts]
    v["fmt_distance"] = [{"m": m, "lang": lang, "out": geo.fmt_distance(m, lang)}
                         for m in (0, 5, 949, 950, 999, 1000, 1049, 1050, 1234, 9999, 12345) for lang in ("uz", "ru")]
    v["valid_point"] = [{"p": p, "out": geo.valid_point(*p)} for p in
                        ([41.3, 69.2], [91, 0], [0, 181], ["41.3", "69.2"], [None, 1], ["x", 1], [-90, -180])]
    v["districts"] = [{"p": [p["lat"], p["lon"]], "out": geo.nearest_district(p["lat"], p["lon"], load("districts"))}
                      for p in phs_list]

    specs = [("24/7", []), ("08:00-22:00", []), ("08:00-02:00", []), ("08:00-24:00", []), ("08:00-21:00", [6]),
             ("09:00-03:00", [6]), ("00:00-24:00", [0])]
    v["hours"] = []
    for spec, off in specs:
        for step in range(0, 7 * 24 * 60, 97):  # a week in odd steps, so every minute pattern shows up
            t = NOW + step * 60_000
            v["hours"].append({"spec": spec, "off": off, "now": t, "out": hours.status(spec, off, t)})
    v["hours_bad"] = [{"spec": s, "out": err(hours.parse, s)} for s in
                      ("8:00-22:00", "08:00-08:00", "25:00-26:00", "08:00-24:30", "", "24/7", "00:00-24:00", "22:00-06:00")]

    v["rank"] = []
    v["rank_offers"] = {m: offers_for(m, rows, phs) for m in ("paracetamol-500", "ibuprofen-200", "febrinol-500",
                                                               "ceftriaxone-1g")}
    for med in ("paracetamol-500", "ibuprofen-200", "febrinol-500", "ceftriaxone-1g"):
        offers = v["rank_offers"][med]
        for weight in (0, 30, 50, 100):
            for open_only in (False, True):
                for t in (NOW, NOW + 12 * 3_600_000):
                    res = rank.rank(offers, 41.3111, 69.2797, t, weight, open_only, None)
                    v["rank"].append({"med": med, "weight": weight, "open_only": open_only, "now": t, "max_m": None,
                                      "out": res})
        res = rank.rank(offers, 41.3111, 69.2797, NOW, 50, False, 4000)
        v["rank"].append({"med": med, "weight": 50, "open_only": False, "now": NOW, "max_m": 4000, "out": res})

    v["reserve_check"] = [{"in": list(c), "out": err(reserve.check, *c)} for c in
                          ((False, 1, 5, 0), (True, 1, 5, 0), (False, 0, 5, 0), (False, 6, 9, 0), (False, 2, 1, 0),
                           (False, 1, 1, 0), (False, 1, 5, 3), (False, 5, 5, 2))]
    v["codes"] = [{"n": n, "out": reserve.make_code(n)} for n in (0, 7, 999_999, 1_000_000, 123_456_789)]
    v["clean_code"] = [{"in": s, "out": reserve.clean_code(s)} for s in
                       ("482913", "482 913", "482-913", " 482913 ", "48291", "4829134", "abcdef", "", "１２３４５６")]
    v["minutes_left"] = [{"exp": e, "now": n, "out": reserve.minutes_left(e, n)} for e, n in
                         ((NOW + 7_200_000, NOW), (NOW + 1, NOW), (NOW, NOW), (NOW - 5, NOW), (NOW + 60_001, NOW))]
    v["moves"] = [{"s": s, "a": a, "out": err(reserve.move, s, a)} for s in reserve.STATUSES
                  for a in ("confirm", "cancel", "expire")]

    para = offers_for("paracetamol-500", rows, phs)
    v["alerts"] = [{"alert": a, "offers": para, "out": alerts.match(a, para)} for a in (
        {"lat": 41.3111, "lon": 69.2797, "radius_m": 1000, "max_price": None},
        {"lat": 41.3111, "lon": 69.2797, "radius_m": 5000, "max_price": None},
        {"lat": 41.3111, "lon": 69.2797, "radius_m": 10000, "max_price": 4500},
        {"lat": 41.3111, "lon": 69.2797, "radius_m": 3000, "max_price": 1000},
        {"lat": 41.2068, "lon": 69.2462, "radius_m": 1000, "max_price": 3800})]

    v["money_fmt"] = [{"n": n, "out": money.fmt(n)} for n in (0, 5, 100, 999, 1000, 12500, 1234567, -4500, 10_000_000)]
    v["money_parse"] = [{"in": s, "out": err(money.parse_price, s)} for s in
                        ("12500", "12 500", "12 500 so'm", "12500 сум", "12.5", "1,5", "-100", "0", "99", "100",
                         "10000000", "10000001", "", "abc", "1e5", 4500, 3.5, True)]
    v["qty_parse"] = [{"in": s, "out": err(money.parse_qty, s)} for s in ("0", "12", " 7 ", "-1", "1.5", "100001", "", 3)]

    csvs = {
        "basic": "med,price,qty\nparacetamol-500,4 500,12\nIbuprofen 200 mg,9000,0\n",
        "semicolon_bom": "\ufeffnomi;narx;soni\r\nПарацетамол;4500;3\r\nФебринол;19 000;1\r\n",
        "errors": "med,price,qty\nunknown,100,1\nparacetamol-500,12.5,1\nparacetamol-500,4500,x\nparacetamol-500\n"
                  "paracetamol-500,4500,2\nparacetamol-500,4600,3\n",
        "quoted": 'dori,narx,soni\n"Paratsetamol",4500,"10"\n"Diklofenak gel","14 000",5\n',
        "bad_header": "a,b,c\n1,2,3\n",
        "dup_header": "med,med,price,qty\n",
        "empty": "\n\n",
        "too_many": "med,price,qty\n" + "paracetamol-500,4500,1\n" * 501,
        "too_big": "med,price,qty\n" + "x" * (70 * 1024),
        "formula": "med,price,qty\n=HYPERLINK(1),4500,1\n",
    }
    v["csv"] = [{"name": k, "in": s, "out": err(csvio.parse_stock, s, meds)} for k, s in csvs.items()]
    v["safe_cell"] = [{"in": s, "out": csvio.safe_cell(s)} for s in
                      ("Paratsetamol", "=1+1", "+998", "-5", "@SUM(A1)", "a,b", 'say "hi"', "\tx", "12 500", "line\nbreak")]

    v["h32"] = [{"in": s, "out": seedgen.h32(s)} for s in ("", "a", "1:paracetamol-500", "16:artrogel-1", "Ўзбек")]
    v["seed"] = {"now": NOW, "rows": rows}
    v["seed_other_day"] = {"now": NOW + 40 * 86_400_000 + 123_456, "count": len(seedgen.stock_rows(
        phs_list, meds, NOW + 40 * 86_400_000 + 123_456))}
    return v


def dump(v: dict) -> str:
    """One vector per line: diffs stay readable and no line is huge."""
    lines = ["{"]
    keys = list(v)
    for n, k in enumerate(keys):
        tail = "," if n < len(keys) - 1 else ""
        val = v[k]
        if isinstance(val, list):
            inner = ",\n".join("    " + json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in val)
            lines.append(f'  "{k}": [\n{inner}\n  ]{tail}')
        else:
            lines.append(f'  "{k}": {json.dumps(val, ensure_ascii=False, separators=(",", ":"))}{tail}')
    lines.append("}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    OUT.write_text(dump(build()), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
