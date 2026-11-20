// JS port of navbatchi/bot/views.py and views_staff.py: the same screens, locale keys and callback data
// ("n:menu", "o:paracetamol-500:50:1"...), as {html, kb} where kb rows hold {text, data} | {text, app} | {text, url}.
import { minutesLeft } from '../shared/reserve.js';
import { ago, clock, dist, hoursText, medLabel, openText, price, Raw, stockLevel } from '../shared/i18n.js';

const MAX_LINES = 5;

export function makeViews(t) {
  const b = (text, data) => ({ text, data });
  const back = (lang, data) => [b(t(lang, 'btn.back'), data)];
  const kb = (rows) => rows.filter((r) => r && r.length);

  return {
    mainMenu(lang, user, hello = false) {
      const rows = [[b(t(lang, 'btn.search'), 'n:search')],
        [b(t(lang, 'btn.my'), 'n:my'), b(t(lang, 'btn.alerts'), 'n:alerts')],
        [b(t(lang, 'btn.location'), 'n:loc')], [{ text: t(lang, 'btn.app'), app: true }]];
      if (user.role === 'pharmacist') rows.push([b(t(lang, 'btn.pharm'), 'n:pharm')]);
      rows.push([b(t(lang, 'btn.lang'), 'n:lang')]);
      return { html: t(lang, hello ? 'start.hello' : 'start.menu'), kb: kb(rows) };
    },
    searchAsk: (lang) => ({ html: t(lang, 'search.ask'), kb: [back(lang, 'n:menu')] }),
    searchResults(lang, q, meds) {
      if (!meds.length) return { html: t(lang, 'search.none', { q }), kb: [back(lang, 'n:menu')] };
      const rows = meds.map((m) => [b(medLabel(m, lang) + (m.rx ? ' · Rx' : ''), `m:${m.id}`)]);
      return { html: t(lang, 'search.results', { q }), kb: [...rows, back(lang, 'n:menu')] };
    },
    locAsk(lang, districts, user) {
      const names = Object.fromEntries(districts.map((d) => [d.id, d.name[lang]]));
      const html = user.district ? t(lang, 'loc.current', { district: names[user.district] }) : t(lang, 'loc.ask');
      const buttons = districts.map((d) => b(d.name[lang], `d:${d.id}`));
      const rows = [];
      for (let i = 0; i < buttons.length; i += 3) rows.push(buttons.slice(i, i + 3));
      return { html, kb: [...rows, back(lang, 'n:menu')] };
    },
    offers(lang, res, district, w, o) {
      const med = res.med;
      const lines = [t(lang, 'offers.title', { med: medLabel(med, lang), pack: med.pack[lang], district })];
      if (med.rx) lines.push(t(lang, 'offers.rx'));
      lines.push('');
      const rows = [];
      const shown = res.items.slice(0, MAX_LINES);
      for (const key of ['nearest', 'cheapest']) {
        if (res[key] !== null && !shown.some((i) => i.pharmacy_id === res[key])) shown.push(res.items.find((i) => i.pharmacy_id === res[key]));
      }
      shown.forEach((item, k) => {
        const n = k + 1;
        const tags = ['best', 'nearest', 'cheapest'].filter((x) => res[x] === item.pharmacy_id).map((x) => t(lang, `offers.tag_${x}`));
        lines.push(t(lang, 'offers.line', { n, name: item.name, price: price(item.price), dist: dist(lang, item.dist),
          open: new Raw(openText(t, lang, item.status)), tags: tags.length ? ` · ${tags.join(', ')}` : '' }));
        rows.push([b(`${n}. ${item.name} — ${price(item.price)}`, `p:${med.id}:${item.pharmacy_id}:${w}:${o}`)]);
      });
      if (!res.items.length) lines.push(t(lang, o ? 'offers.none_open' : 'offers.none'));
      for (const a of res.analogs.slice(0, 1)) {
        lines.push('', t(lang, 'offers.analog', { name: a.label, price: price(a.price) }));
        rows.push([b(t(lang, 'btn.analog', { name: a.label }), `o:${a.id}:${w}:${o}`)]);
      }
      lines.push('', t(lang, 'disclaimer'));
      rows.push([[0, 'btn.near'], [50, 'btn.balance'], [100, 'btn.cheap']].map(([v, k]) => b((w === v ? '• ' : '') + t(lang, k),
        `o:${med.id}:${v}:${o}`)));
      rows.push([b(t(lang, o ? 'btn.night_on' : 'btn.night_off'), `o:${med.id}:${w}:${1 - o}`)]);
      rows.push([b(t(lang, 'btn.alert'), `a:${med.id}:0`)], back(lang, 'n:search'));
      return { html: lines.join('\n'), kb: rows };
    },
    card(lang, item, med, w, o, now) {
      let html = t(lang, 'card', { name: item.name, address: item[`address_${lang}`], phone: item.phone,
        hours: hoursText(t, lang, item.hours), open: new Raw(openText(t, lang, item.status)), dist: dist(lang, item.dist),
        med: medLabel(med, lang), pack: med.pack[lang], price: price(item.price), stock: stockLevel(t, lang, item.available),
        updated: ago(t, lang, item.updated_at, now) });
      const rows = [];
      if (med.rx) html += `\n\n${t(lang, 'card.rx')}`;
      else if (item.available > 0) rows.push([b(t(lang, 'btn.reserve'), `q:${med.id}:${item.pharmacy_id}:0`)]);
      rows.push([{ text: t(lang, 'btn.map'), url: `https://www.openstreetmap.org/?mlat=${item.lat}&mlon=${item.lon}#map=17/${item.lat}/${item.lon}` }]);
      rows.push(back(lang, `o:${med.id}:${w}:${o}`));
      return { html: `${html}\n\n${t(lang, 'disclaimer')}`, kb: rows };
    },
    qty(lang, med, pharmacy, available) {
      const nums = [];
      for (let n = 1; n <= Math.min(5, available); n++) nums.push(b(String(n), `q:${med.id}:${pharmacy.id}:${n}`));
      return { html: t(lang, 'res.qty', { med: medLabel(med, lang), pharmacy: pharmacy.name }),
        kb: [nums, back(lang, `p:${med.id}:${pharmacy.id}:50:0`)] };
    },
    reserved(lang, res, med, ph) {
      return { html: t(lang, 'res.ok', { med: medLabel(med, lang), qty: res.qty, total: price(res.qty * res.price), pharmacy: ph.name,
        address: ph.address[lang], phone: ph.phone, code: res.code, until: clock(res.expires_at) }),
      kb: [[b(t(lang, 'btn.cancel_res'), `r:${res.id}`)], [b(t(lang, 'btn.menu'), 'n:menu')]] };
    },
    myList(lang, items, now) {
      if (!items.length) return { html: t(lang, 'res.empty'), kb: [back(lang, 'n:menu')] };
      const lines = [t(lang, 'res.list')];
      const rows = [];
      for (const [res, med, ph] of items) {
        let st;
        if (res.status === 'held') {
          st = t(lang, 'res.held', { code: res.code, until: clock(res.expires_at), left: minutesLeft(res.expires_at, now) });
          rows.push([b(`${t(lang, 'btn.cancel_res')} · ${med.name[lang]}`, `r:${res.id}`)]);
        } else st = t(lang, `status.${res.status}`);
        lines.push('', t(lang, 'res.line', { med: medLabel(med, lang), qty: res.qty, pharmacy: ph.name, status: new Raw(st) }));
      }
      return { html: lines.join('\n'), kb: [...rows, back(lang, 'n:menu')] };
    },
    alertRadius: (lang, med) => ({ html: t(lang, 'alert.radius', { med: medLabel(med, lang) }),
      kb: [[1, 3, 5, 10].map((km) => b(t(lang, 'alert.km', { n: km }), `a:${med.id}:${km}`)), back(lang, `o:${med.id}:50:0`)] }),
    alertPrice: (lang, med) => ({ html: t(lang, 'alert.price'), kb: [[b(t(lang, 'btn.any_price'), 'y:1')], back(lang, `a:${med.id}:0`)] }),
    alertOk(lang, a, med) {
      const part = a.max_price ? t(lang, 'alert.price_part', { price: price(a.max_price) }) : '';
      return { html: t(lang, 'alert.ok', { med: medLabel(med, lang), km: a.radius_m / 1000, price: new Raw(part) }),
        kb: [[b(t(lang, 'btn.menu'), 'n:menu')]] };
    },
    alertsList(lang, items) {
      if (!items.length) return { html: t(lang, 'alert.empty'), kb: [back(lang, 'n:menu')] };
      const lines = [t(lang, 'alert.list'), ''];
      const rows = items.map(([a, med], i) => {
        const part = a.max_price ? t(lang, 'alert.price_part', { price: price(a.max_price) }) : '';
        lines.push(t(lang, 'alert.line', { n: i + 1, med: medLabel(med, lang), km: a.radius_m / 1000, price: new Raw(part) }));
        return [b(`${t(lang, 'btn.delete')} ${i + 1}`, `x:${a.id}`)];
      });
      return { html: lines.join('\n'), kb: [...rows, back(lang, 'n:menu')] };
    },
    pharmMenu: (lang, ph, held) => ({ html: t(lang, 'pharm.menu', { pharmacy: ph.name, held }),
      kb: [[b(t(lang, 'pharm.btn_code'), 'n:code')], [b(t(lang, 'pharm.btn_held', { n: held }), 'n:held')], back(lang, 'n:menu')] }),
    ask: (lang, key, to = 'pharm') => ({ html: t(lang, key), kb: [back(lang, `n:${to}`)] }),
    pharmHeld(lang, items) {
      const held = items.filter(([r]) => r.status === 'held');
      if (!held.length) return { html: t(lang, 'pharm.held_empty'), kb: [back(lang, 'n:pharm')] };
      const lines = [t(lang, 'pharm.held'), ''];
      for (const [r, m] of held) {
        lines.push(t(lang, 'pharm.held_line', { code: r.code, med: medLabel(m, lang), qty: r.qty, until: clock(r.expires_at) }));
      }
      return { html: lines.join('\n'), kb: [[b(t(lang, 'pharm.btn_code'), 'n:code')], back(lang, 'n:pharm')] };
    },
  };
}
