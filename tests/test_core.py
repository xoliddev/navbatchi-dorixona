"""Pure core: the shared vectors (the JS port checks the same file) plus the rules spelled out as plain tests."""

from __future__ import annotations

import importlib.util

import pytest

from navbatchi.core import alerts, catalog, csvio, geo, hours, money, rank, reserve, seedgen, text

from .conftest import ROOT


def _make_vectors():
    spec = importlib.util.spec_from_file_location("make_vectors", ROOT / "scripts" / "make_vectors.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_vectors_are_up_to_date():
    mod = _make_vectors()
    assert mod.dump(mod.build()) == (ROOT / "shared" / "test_vectors.json").read_text(encoding="utf-8"), \
        "run: python scripts/make_vectors.py"


@pytest.mark.parametrize("typed", ["парацетамол", "paratsetamol", "paracetamol", "Paratsetamol", "PARACETAMOL",
                                   "paratsitamol", "paraceamol", "paraset", "Парацетамол 500"])
def test_every_spelling_of_paracetamol_finds_it(meds, typed):
    assert catalog.search(meds, typed)[0]["id"] == "paracetamol-500"


def test_brand_finds_itself_and_inn_finds_the_brand(meds):
    assert [h["id"] for h in catalog.search(meds, "Febrinol")] == ["febrinol-500"]
    assert [h["id"] for h in catalog.search(meds, "фебринол")] == ["febrinol-500"]
    ids = [h["id"] for h in catalog.search(meds, "paratsetamol")]
    assert ids == ["paracetamol-500", "febrinol-500"]  # the generic first, the brand through its ingredient
    assert catalog.analogs(meds, "febrinol-500") == ["paracetamol-500"]
    cheaper = catalog.cheaper_analogs(meds, "febrinol-500", {"febrinol-500": 19_000, "paracetamol-500": 4_500})
    assert cheaper == [{"id": "paracetamol-500", "price": 4_500, "saving": 14_500}]
    assert catalog.cheaper_analogs(meds, "paracetamol-500", {"febrinol-500": 19_000, "paracetamol-500": 4_500}) == []


def test_search_ignores_noise_and_respects_dose(meds):
    assert catalog.search(meds, "") == []
    assert catalog.search(meds, "pa") == []
    assert catalog.search(meds, "omeprazol 40") == []
    assert catalog.search(meds, "x" * 10_000) == []
    assert catalog.search(meds, "хлоргексидин")[0]["id"] == "chlorhexidine-005"
    assert catalog.search(meds, "hlorgeksidin")[0]["id"] == "chlorhexidine-005"
    assert catalog.search(meds, "витамин с")[0]["id"] == "ascorbic-500"


def test_text_keys():
    assert text.words("Navroʻz o'g'il") == text.words("Navro'z ogil")
    assert text.words("Ўзбекистон") == ["ozbekiston"]
    assert text.distance("abc", "acb") == 1
    assert text.distance("kitten", "sitting", 1) == 2  # capped at limit + 1


def test_haversine_and_labels():
    assert geo.haversine_m(41.3111, 69.2797, 41.3111, 69.2797) == 0
    one_km_north = geo.haversine_m(41.3111, 69.2797, 41.3111 + 1 / 111.195, 69.2797)
    assert 995 <= one_km_north <= 1005
    assert geo.fmt_distance(850) == "850 m"
    assert geo.fmt_distance(1234, "ru") == "1,2 км"
    assert not geo.valid_point(float("nan"), 1)


def test_hours_around_midnight_and_days_off():
    wed = 1_795_000_000_000 - (16 * 3600 + 6 * 60 + 40) * 1000  # Wednesday 2026-11-18, 00:00 in Tashkent
    at = lambda h, m=0, days=0: wed + (h * 60 + m) * 60_000 + days * 86_400_000  # noqa: E731
    assert hours.status("24/7", [], at(3)) == {"open": True, "h24": True}
    assert hours.status("08:00-22:00", [], at(21, 59))["open"]
    assert hours.status("08:00-22:00", [], at(22)) == {"open": False, "h24": False, "opens": "08:00", "day": 1}
    assert hours.status("08:00-22:00", [], at(7, 30)) == {"open": False, "h24": False, "opens": "08:00", "day": 0}
    assert hours.status("08:00-02:00", [], at(1, 59)) == {"open": True, "h24": False, "until": "02:00"}
    assert not hours.status("08:00-02:00", [], at(2))["open"]
    assert hours.status("08:00-24:00", [], at(23, 59))["until"] == "24:00"
    # Sunday off: closed all Sunday, opens Monday; past-midnight hours from Saturday still count on Sunday morning
    sunday_noon = at(12, days=4)
    assert hours.status("08:00-21:00", [6], sunday_noon) == {"open": False, "h24": False, "opens": "08:00", "day": 1}
    assert hours.status("09:00-03:00", [6], at(2, days=4))["open"]
    with pytest.raises(hours.HoursError):
        hours.parse("08:00-08:00")


def test_rank_slider_moves_between_nearest_and_cheapest():
    o = lambda pid, price, lat: {"pharmacy_id": pid, "price": price, "available": 3, "lat": lat,  # noqa: E731
                                 "lon": 69.2797, "hours": "24/7", "off": []}
    offers = [o(1, 9000, 41.312), o(2, 4000, 41.36), o(3, 6000, 41.33), {**o(4, 100, 41.3115), "available": 0}]
    near = rank.rank(offers, 41.3111, 69.2797, 0, weight=0)
    cheap = rank.rank(offers, 41.3111, 69.2797, 0, weight=100)
    assert (near["nearest"], near["cheapest"], near["best"]) == (1, 2, 1)
    assert cheap["best"] == 2
    assert [i["pharmacy_id"] for i in near["items"]] == [1, 3, 2]  # out of stock (4) is never shown
    assert rank.rank([], 0, 0, 0) == {"items": [], "nearest": None, "cheapest": None, "best": None}
    closed = [{**o(5, 100, 41.3112), "hours": "08:00-09:00"}]
    assert rank.rank(closed, 41.3111, 69.2797, 0, open_only=True)["items"] == []  # 05:00 in Tashkent


def test_reservation_rules():
    with pytest.raises(reserve.ReserveError, match="rx"):
        reserve.check(True, 1, 10)
    with pytest.raises(reserve.ReserveError, match="stock"):
        reserve.check(False, 2, 1)
    with pytest.raises(reserve.ReserveError, match="qty"):
        reserve.check(False, True, 10)
    assert reserve.make_code(42) == "000042"
    assert reserve.clean_code("482 913") == "482913"
    assert reserve.clean_code("１２３４５６") is None  # ASCII digits only
    assert reserve.move("held", "confirm") == "picked"
    with pytest.raises(reserve.ReserveError):
        reserve.move("expired", "confirm")
    assert reserve.minutes_left(reserve.expires_at(0), 0) == 120


def test_alert_picks_cheapest_in_radius():
    offers = [{"pharmacy_id": 1, "price": 5000, "available": 1, "lat": 41.3111, "lon": 69.2797},
              {"pharmacy_id": 2, "price": 4000, "available": 0, "lat": 41.3111, "lon": 69.2797},
              {"pharmacy_id": 3, "price": 4500, "available": 2, "lat": 41.3200, "lon": 69.2797}]
    a = {"lat": 41.3111, "lon": 69.2797, "radius_m": 2000, "max_price": None}
    assert alerts.match(a, offers)["pharmacy_id"] == 3
    assert alerts.match({**a, "radius_m": 500}, offers)["pharmacy_id"] == 1
    assert alerts.match({**a, "max_price": 4000}, offers) is None


def test_money_is_integer_only():
    assert money.fmt(1_234_567) == "1 234 567"
    assert money.parse_price("12 500 so'm") == 12_500
    for bad in ("12.5", "1,5", "-100", "0", 3.5, True, "1e5"):
        with pytest.raises(money.PriceError):
            money.parse_price(bad)


def test_csv_import_and_safe_export(meds):
    res = csvio.parse_stock("nomi;narx;soni\r\nПарацетамол;4 500;3\r\n=cmd|' /C calc'!A0;1;1\r\n".encode(), meds)
    assert res["rows"] == [{"med": "paracetamol-500", "price": 4500, "qty": 3}]
    assert res["errors"] == [{"line": 3, "code": "med"}]
    with pytest.raises(csvio.CsvError, match="too_big"):
        csvio.parse_stock(b"med,price,qty\n" + b"x" * 70_000, meds)
    with pytest.raises(csvio.CsvError, match="encoding"):
        csvio.parse_stock(b"med,price,qty\n\xff\xfe", meds)
    out = csvio.to_csv([["med", "price"], ["=HYPERLINK(\"x\")", 4500], ["@SUM(1)", "-3"]])
    assert out.splitlines() == ["med,price", "\"'=HYPERLINK(\"\"x\"\")\",4500", "'@SUM(1),'-3"]


def test_seed_is_relative_to_now_and_stable(meds):
    phs = [{"id": i} for i in range(1, 17)]
    a = seedgen.stock_rows(phs, meds, 1_795_000_000_000)
    b = seedgen.stock_rows(phs, meds, 1_795_000_000_000 + 86_400_000)
    assert [(r["pharmacy_id"], r["med_id"], r["qty"], r["price"]) for r in a] == \
           [(r["pharmacy_id"], r["med_id"], r["qty"], r["price"]) for r in b]
    assert all(0 < 1_795_000_000_000 - r["updated_ms"] <= 305 * 60_000 for r in a)
    assert all(r["price"] % 100 == 0 and isinstance(r["price"], int) for r in a)
