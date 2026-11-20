"""End-to-end through the real aiogram handlers with a mocked Bot API:
search -> location -> results -> card -> reserve -> pharmacist confirms the code; expiry; price alert; admin invite;
forged buttons; roles."""

from __future__ import annotations

import re

from navbatchi import scheduler

from .helpers import ADMIN, ALI, CENTRE, DILNOZA, service_env, stock
from .tg_sim import TgSim

OLIM = 1003  # a new user: no location yet


def code_in(text: str) -> str:
    m = re.search(r"<code>(\d{6})</code>", text)
    assert m, text
    return m.group(1)


async def test_search_location_results_reserve_confirm():
    async with service_env() as (svc, clock):
        sim = TgSim(svc)
        clock.set_local(3)  # 03:00 in Tashkent: the reason "navbatchi" exists
        await sim.say(OLIM, "/start")
        assert "Navbatchi Dorixona" in sim.last(OLIM) and "tibbiy maslahat emas" in sim.last(OLIM)
        assert "Xaritada ochish" in sim.buttons(OLIM) and "Dorixonam" not in sim.buttons(OLIM)
        await sim.say(OLIM, "paratsitamol")  # typo, typed straight into the chat
        assert "Paratsetamol 500 mg" in sim.buttons(OLIM) and "Febrinol 500 mg" in sim.buttons(OLIM)
        await sim.tap(OLIM, "Paratsetamol")
        assert "Joylashuv tugmasi pastda" in sim.last(OLIM)  # asked where the user is
        await sim.send_location(OLIM, *CENTRE)
        offers = sim.last(OLIM)
        assert "eng yaqin" in offers and "eng arzon" in offers and "Oq Terak Dorixona" in offers
        assert "yopiq" in offers and "24 soat" in offers and "tibbiy maslahat emas" in offers
        assert "⬅️ Orqaga" in sim.buttons(OLIM)
        await sim.tap(OLIM, "Navbatchi")
        night = sim.last(OLIM)
        assert "Oq Terak" not in night and "Sokin Tun 24" in night
        await sim.tap(OLIM, "Arzonroq")  # slider towards price
        await sim.tap(OLIM, "Muvozanat")
        await sim.tap(OLIM, next(b for b in sim.buttons(OLIM) if "Sokin Tun 24" in b))
        card = sim.last(OLIM)
        assert "+998 71 000 02 02" in card and "Ish vaqti: 24 soat" in card and "Yangilangan:" in card
        assert "Qoldiq: bor (4 ta)" in card
        await sim.tap(OLIM, "Bron qilish")
        await sim.tap(OLIM, "2")
        code = code_in(sim.last(OLIM))
        assert "Paratsetamol 500 mg</b> × 2" in sim.last(OLIM) and "05:" in sim.last(OLIM)  # held until ~05:00
        assert "Yangi bron" in sim.last(DILNOZA) and code in sim.last(DILNOZA)
        assert (await stock(svc, 2, "paracetamol-500"))["reserved"] == 2

        await sim.say(DILNOZA, "/start")
        await sim.tap(DILNOZA, "Dorixonam")
        assert "Sokin Tun 24" in sim.last(DILNOZA) and "Kutilayotgan bronlar: 1" in sim.last(DILNOZA)
        await sim.tap(DILNOZA, "Bronlar")
        assert code in sim.last(DILNOZA)
        await sim.tap(DILNOZA, "Kod bilan berish")
        await sim.say(DILNOZA, "000000")
        assert "Bunday kutilayotgan bron yo'q" in sim.last(DILNOZA)
        await sim.say(DILNOZA, f"{code[:3]} {code[3:]}")
        assert any("Berildi" in x and "Javonda 2 ta qoldi" in x for x in sim.texts(DILNOZA))
        assert "berildi" in sim.last(OLIM)
        row = await stock(svc, 2, "paracetamol-500")
        assert (row["qty"], row["reserved"]) == (2, 0)
        await sim.tap(OLIM, "Bosh menyu")
        await sim.tap(OLIM, "Mening bronlarim")
        assert "olindi" in sim.last(OLIM)


async def test_expiry_releases_and_tells_the_customer():
    async with service_env() as (svc, clock):
        sim = TgSim(svc)
        await sim.say(ALI, "Ибупрофен")
        await sim.tap(ALI, "Ibuprofen 200 mg")
        await sim.tap(ALI, "1.")
        await sim.tap(ALI, "Bron qilish")
        await sim.tap(ALI, "1")
        res = (await svc.my_reservations(ALI))[0]
        clock.skip(minutes=121)
        assert (await scheduler.tick(svc, sim.notifier))["expired"] == 1
        assert "muddati o'tdi" in sim.last(ALI)
        assert (await stock(svc, res["pharmacy_id"], "ibuprofen-200"))["reserved"] == 0
        assert (await scheduler.tick(svc, sim.notifier))["expired"] == 0


async def test_rx_cannot_be_reserved_and_price_alert_fires_once():
    async with service_env() as (svc, _):
        sim = TgSim(svc)
        await sim.say(ALI, "сальбутамол")
        await sim.tap(ALI, "Salbutamol")
        assert "Retsept bilan" in sim.last(ALI)
        await sim.tap(ALI, "1.")
        assert "Retsept bilan beriladi" in sim.last(ALI) and "Bron qilish" not in sim.buttons(ALI)
        await sim.tap_data(ALI, "q:salbutamol-100:1:1")  # a forged "reserve" button is refused by the service
        assert "retsept bilan beriladi" in sim.alerts()[-1]
        await sim.tap(ALI, "⬅️ Orqaga")
        await sim.tap(ALI, "Narx kuzatuvi")
        await sim.tap(ALI, "1 km")
        await sim.say(ALI, "arzon")
        assert "butun so'mda" in sim.last(ALI)
        await sim.say(ALI, "45 000")
        assert "Kuzatuv yoqildi" in sim.last(ALI) and "1 km" in sim.last(ALI)
        assert (await scheduler.tick(svc, sim.notifier))["alerts"] == 0  # nearest one costs 46 600

        # the admin links a pharmacist to pharmacy 1, who uploads a CSV with a lower price
        await sim.say(ADMIN, "/start")
        await sim.tap(ADMIN, "Admin")
        await sim.tap(ADMIN, "Farmatsevtni ulash")
        await sim.tap(ADMIN, "#1 Oq Terak")
        token = re.search(r"start=inv_([A-Za-z0-9_-]+)", sim.last(ADMIN)).group(1)
        kamola = 3001
        await sim.say(kamola, f"/start inv_{token}")
        assert any("Oq Terak Dorixona</b> farmatsevtisiz" in x for x in sim.texts(kamola))
        await sim.say(OLIM, f"/start inv_{token}")
        assert "ishlatilgan" in sim.last(OLIM)
        await sim.tap(kamola, "Dorixonam")
        await sim.tap(kamola, "CSV yuklash")
        await sim.send_file(kamola, "narxlar.csv", b"dori;narx;soni\nSalbutamol;44 000;3\n=evil();1;1\n")
        assert any("Yangilandi: 1" in x for x in sim.texts(kamola))
        assert any("Qabul qilinmagan qatorlar: 3" in x for x in sim.texts(kamola))
        assert (await scheduler.tick(svc, sim.notifier))["alerts"] == 1
        assert "Topildi!" in sim.last(ALI) and "44 000 so'm" in sim.last(ALI)
        assert (await scheduler.tick(svc, sim.notifier))["alerts"] == 0
        await sim.tap(ALI, "Ko'rish")
        assert "Oq Terak Dorixona" in sim.last(ALI)


async def test_pharmacist_stock_edit_and_export():
    async with service_env() as (svc, _):
        sim = TgSim(svc)
        await sim.say(DILNOZA, "/start")
        await sim.tap(DILNOZA, "Dorixonam")
        await sim.tap(DILNOZA, "Zaxira va narx")
        await sim.tap(DILNOZA, "Paratsetamol")
        await sim.say(DILNOZA, "narx")
        assert "Ikki raqam" in sim.last(DILNOZA)
        await sim.say(DILNOZA, "4 800 30")
        assert any("Saqlandi" in x and "4 800 so'm, 30 ta" in x for x in sim.texts(DILNOZA))
        await sim.tap(DILNOZA, "CSV yuklab olish")
        data = sim.session.documents[DILNOZA][-1].decode("utf-8-sig")
        assert data.startswith("med,name,price,qty,reserved") and "paracetamol-500,Paratsetamol,4800,30,0" in data


async def test_forged_buttons_and_roles():
    async with service_env() as (svc, _):
        sim = TgSim(svc)
        await sim.say(ALI, "/start")
        for data in ("m:evil-med", "q:paracetamol-500:2:9", "p:paracetamol-500:2:37:0", "o:paracetamol-500:50:7",
                     "d:atlantis", "zz:1", "n:nowhere"):
            await sim.tap_data(ALI, data)
            assert sim.alerts()[-1] == "Bu tugma eskirgan. Bosh menyudan boshlang.", data
        for data in ("n:pharm", "n:code", "n:held", "g:0", "n:csv_out", "n:admin", "n:invite", "i:1", "n:addph"):
            await sim.tap_data(ALI, data)
            assert sim.alerts()[-1] == "Bu bo'lim siz uchun emas.", data
        await sim.tap(ALI, "Русский")
        assert "Главное меню" in sim.last(ALI) and "O'zbekcha" in sim.buttons(ALI)
        await sim.tap(ALI, "Мои брони")
        assert "Броней пока нет" in sim.last(ALI) and "⬅️ Orqaga" in sim.buttons(ALI)


async def test_rate_limit_silences_floods():
    async with service_env() as (svc, _):
        sim = TgSim(svc, rate=3)
        for _ in range(6):
            await sim.say(ALI, "paratsetamol")
        assert len(sim.texts(ALI)) == 3
