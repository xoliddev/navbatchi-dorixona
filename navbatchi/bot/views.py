"""Customer screens: (text, inline keyboard). Pure functions of data, so tests and the JS demo port stay simple."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton as Btn
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from ..core.reserve import minutes_left
from ..data import med_label
from ..i18n import Raw, ago, clock, dist, hours_text, open_text, price, stock_level, t
from .cb import Al, AlAny, AlDel, Dist, Med, Nav, Off, Ph, Qty, Res

MAX_LINES = 5


def kb(rows: list[list[Btn]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r])


def back(lang: str, data: str) -> list[Btn]:
    return [Btn(text=t(lang, "btn.back"), callback_data=data)]


def main_menu(lang: str, user: dict, webapp_url: str = "", hello: bool = False) -> tuple:
    rows = [[Btn(text=t(lang, "btn.search"), callback_data=Nav(to="search").pack())],
            [Btn(text=t(lang, "btn.my"), callback_data=Nav(to="my").pack()),
             Btn(text=t(lang, "btn.alerts"), callback_data=Nav(to="alerts").pack())],
            [Btn(text=t(lang, "btn.location"), callback_data=Nav(to="loc").pack())]]
    if webapp_url:
        rows.append([Btn(text=t(lang, "btn.app"), web_app=WebAppInfo(url=webapp_url))])
    if user.get("role") == "pharmacist":
        rows.append([Btn(text=t(lang, "btn.pharm"), callback_data=Nav(to="pharm").pack())])
    if user.get("admin"):
        rows.append([Btn(text=t(lang, "btn.admin"), callback_data=Nav(to="admin").pack())])
    rows.append([Btn(text=t(lang, "btn.lang"), callback_data=Nav(to="lang").pack())])
    return t(lang, "start.hello" if hello else "start.menu"), kb(rows)


def search_ask(lang: str) -> tuple:
    return t(lang, "search.ask"), kb([back(lang, Nav(to="menu").pack())])


def search_results(lang: str, q: str, meds: list[dict]) -> tuple:
    if not meds:
        return t(lang, "search.none", q=q), kb([back(lang, Nav(to="menu").pack())])
    rows = [[Btn(text=med_label(m, lang) + (" · Rx" if m["rx"] else ""), callback_data=Med(med=m["id"]).pack())]
            for m in meds]
    return t(lang, "search.results", q=q), kb([*rows, back(lang, Nav(to="menu").pack())])


def loc_ask(lang: str, districts: list[dict], user: dict, med: str | None = None) -> tuple:
    names = {d["id"]: d["name"][lang] for d in districts}
    text = t(lang, "loc.current", district=names[user["district"]]) if user.get("district") else t(lang, "loc.ask")
    buttons = [Btn(text=d["name"][lang], callback_data=Dist(did=d["id"]).pack()) for d in districts]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    return text, kb([*rows, back(lang, Nav(to="menu").pack())])


def location_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t(lang, "btn.send_location"), request_location=True)]],
                               resize_keyboard=True, one_time_keyboard=True)


def offers(lang: str, res: dict, district: str, w: int, o: int) -> tuple:
    med = res["med"]
    lines = [t(lang, "offers.title", med=med_label(med, lang), pack=med["pack"][lang], district=district)]
    if med["rx"]:
        lines.append(t(lang, "offers.rx"))
    lines.append("")
    rows = []
    shown = res["items"][:MAX_LINES]
    for key in ("nearest", "cheapest"):  # the two extremes are always on screen, even when they rank lower
        if res[key] is not None and all(i["pharmacy_id"] != res[key] for i in shown):
            shown.append(next(i for i in res["items"] if i["pharmacy_id"] == res[key]))
    for n, item in enumerate(shown, start=1):
        tags = [t(lang, f"offers.tag_{k}") for k in ("best", "nearest", "cheapest") if res[k] == item["pharmacy_id"]]
        lines.append(t(lang, "offers.line", n=n, name=item["name"], price=price(item["price"]),
                       dist=dist(lang, item["dist"]), open=Raw(open_text(lang, item["status"])),
                       tags=(" · " + ", ".join(tags)) if tags else ""))
        rows.append([Btn(text=f"{n}. {item['name']} — {price(item['price'])}",
                         callback_data=Ph(med=med["id"], pid=item["pharmacy_id"], w=w, o=o).pack())])
    if not res["items"]:
        lines.append(t(lang, "offers.none_open" if o else "offers.none"))
    for a in res["analogs"][:1]:
        lines += ["", t(lang, "offers.analog", name=a["label"], price=price(a["price"]))]
        rows.append([Btn(text=t(lang, "btn.analog", name=a["label"]), callback_data=Off(med=a["id"], w=w, o=o).pack())])
    lines += ["", t(lang, "disclaimer")]
    modes = [(0, "btn.near"), (50, "btn.balance"), (100, "btn.cheap")]
    rows.append([Btn(text=("• " if w == v else "") + t(lang, k), callback_data=Off(med=med["id"], w=v, o=o).pack())
                 for v, k in modes])
    rows.append([Btn(text=t(lang, "btn.night_on" if o else "btn.night_off"),
                     callback_data=Off(med=med["id"], w=w, o=1 - o).pack())])
    rows.append([Btn(text=t(lang, "btn.alert"), callback_data=Al(med=med["id"], km=0).pack())])
    rows.append(back(lang, Nav(to="search").pack()))
    return "\n".join(lines), kb(rows)


def card(lang: str, item: dict, med: dict, w: int, o: int, now: int) -> tuple:
    text = t(lang, "card", name=item["name"], address=item[f"address_{lang}"], phone=item["phone"],
             hours=hours_text(lang, item["hours"]), open=Raw(open_text(lang, item["status"])),
             dist=dist(lang, item["dist"]), med=med_label(med, lang), pack=med["pack"][lang],
             price=price(item["price"]), stock=stock_level(lang, item["available"]),
             updated=ago(lang, item["updated_at"], now))
    rows = []
    if med["rx"]:
        text += "\n\n" + t(lang, "card.rx")
    elif item["available"] > 0:
        rows.append([Btn(text=t(lang, "btn.reserve"), callback_data=Qty(med=med["id"], pid=item["pharmacy_id"],
                                                                         n=0).pack())])
    osm = f"https://www.openstreetmap.org/?mlat={item['lat']}&mlon={item['lon']}#map=17/{item['lat']}/{item['lon']}"
    rows.append([Btn(text=t(lang, "btn.map"), url=osm)])
    rows.append(back(lang, Off(med=med["id"], w=w, o=o).pack()))
    return text + "\n\n" + t(lang, "disclaimer"), kb(rows)


def qty(lang: str, med: dict, pharmacy: dict, available: int) -> tuple:
    nums = [Btn(text=str(n), callback_data=Qty(med=med["id"], pid=pharmacy["id"], n=n).pack())
            for n in range(1, min(5, available) + 1)]
    return (t(lang, "res.qty", med=med_label(med, lang), pharmacy=pharmacy["name"]),
            kb([nums, back(lang, Ph(med=med["id"], pid=pharmacy["id"], w=50, o=0).pack())]))


def reserved(lang: str, res: dict, med: dict, pharmacy: dict) -> tuple:
    text = t(lang, "res.ok", med=med_label(med, lang), qty=res["qty"], total=price(res["qty"] * res["price"]),
             pharmacy=pharmacy["name"], address=pharmacy[f"address_{lang}"], phone=pharmacy["phone"],
             code=res["code"], until=clock(res["expires_at"]))
    return text, kb([[Btn(text=t(lang, "btn.cancel_res"), callback_data=Res(rid=res["id"]).pack())],
                     [Btn(text=t(lang, "btn.menu"), callback_data=Nav(to="menu").pack())]])


def my_list(lang: str, items: list[tuple[dict, dict, dict]], now: int) -> tuple:
    if not items:
        return t(lang, "res.empty"), kb([back(lang, Nav(to="menu").pack())])
    lines, rows = [t(lang, "res.list")], []
    for res, med, ph in items:
        if res["status"] == "held":
            status = t(lang, "res.held", code=res["code"], until=clock(res["expires_at"]),
                       left=minutes_left(res["expires_at"], now))
            rows.append([Btn(text=f"{t(lang, 'btn.cancel_res')} · {med['name'][lang]}",
                             callback_data=Res(rid=res["id"]).pack())])
        else:
            status = t(lang, f"status.{res['status']}")
        lines += ["", t(lang, "res.line", med=med_label(med, lang), qty=res["qty"], pharmacy=ph["name"],
                        status=Raw(status))]
    return "\n".join(lines), kb([*rows, back(lang, Nav(to="menu").pack())])


def alert_radius(lang: str, med: dict) -> tuple:
    row = [Btn(text=t(lang, "alert.km", n=km), callback_data=Al(med=med["id"], km=km).pack()) for km in (1, 3, 5, 10)]
    return t(lang, "alert.radius", med=med_label(med, lang)), kb([row, back(lang, Off(med=med["id"], w=50,
                                                                                         o=0).pack())])


def alert_price(lang: str, med: dict) -> tuple:
    return t(lang, "alert.price"), kb([[Btn(text=t(lang, "btn.any_price"), callback_data=AlAny(ok=1).pack())],
                                        back(lang, Al(med=med["id"], km=0).pack())])


def alert_ok(lang: str, alert: dict, med: dict) -> tuple:
    part = t(lang, "alert.price_part", price=price(alert["max_price"])) if alert["max_price"] else ""
    return (t(lang, "alert.ok", med=med_label(med, lang), km=alert["radius_m"] // 1000, price=Raw(part)),
            kb([[Btn(text=t(lang, "btn.menu"), callback_data=Nav(to="menu").pack())]]))


def alerts_list(lang: str, items: list[tuple[dict, dict]]) -> tuple:
    if not items:
        return t(lang, "alert.empty"), kb([back(lang, Nav(to="menu").pack())])
    lines, rows = [t(lang, "alert.list"), ""], []
    for n, (a, med) in enumerate(items, start=1):
        part = t(lang, "alert.price_part", price=price(a["max_price"])) if a["max_price"] else ""
        lines.append(t(lang, "alert.line", n=n, med=med_label(med, lang), km=a["radius_m"] // 1000, price=Raw(part)))
        rows.append([Btn(text=f"{t(lang, 'btn.delete')} {n}", callback_data=AlDel(aid=a["id"]).pack())])
    return "\n".join(lines), kb([*rows, back(lang, Nav(to="menu").pack())])
