// The browser demo's logic, headless: seeding on any date (30 days in a row, across New Year), the guided story
// through the simulated bot, expiry, alerts, forged buttons and the Mini App API stand-in.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { makeT } from '../shared/i18n.js';
import { apiFor } from '../demo/api.js';
import { BotSim } from '../demo/bot.js';
import { makeViews } from '../demo/bot-views.js';
import { ALI, createDemo, DILNOZA, PHARMACY, SARDOR } from '../demo/seed.js';
import { runStep, STEPS, tap } from '../demo/story.js';

const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url), 'utf8'));
const shared = { meds: read('../shared/data/meds.json'), pharmacies: read('../shared/data/pharmacies.json'),
  districts: read('../shared/data/districts.json') };
const t = makeT({ uz: read('../shared/locales/uz.json'), ru: read('../shared/locales/ru.json') });
const views = makeViews(t);
const HOUR = 3_600_000;
const at = (iso, hh, mm = 0) => Date.parse(`${iso}T00:00:00Z`) + (hh - 5) * HOUR + mm * 60_000; // Tashkent time

function world(startMs, lang = 'uz') {
  let now = startMs;
  const backend = createDemo({ ...shared, now: () => now, lang });
  const alerts = [];
  const bots = {};
  for (const uid of [ALI, DILNOZA]) {
    bots[uid] = new BotSim(backend, uid, t, views, { onAlert: (x) => alerts.push(x) });
    bots[uid].start();
  }
  backend.on((ev) => {
    const to = ev.type === 'new_res' ? ev.to : [ev.to];
    for (const uid of to) bots[uid]?.deliver(ev);
  });
  return { backend, bots, alerts, advance: (ms) => { now += ms; } };
}

const last = (bot) => bot.messages.at(-1).html;
const stock = (b, pid, med) => b.stock.get(`${pid}:${med}`);

test('seed and full story work on 30 consecutive days, across New Year, at any hour', async () => {
  for (let d = 0; d < 30; d++) {
    const day = new Date(Date.parse('2026-12-17T00:00:00Z') + d * 86_400_000).toISOString().slice(0, 10);
    for (const hour of [0, 9, 23]) {
      const { backend, bots } = world(at(day, hour, 30));
      for (const s of backend.stock.values()) assert.ok(s.qty >= 0 && s.reserved >= 0 && s.reserved <= s.qty);
      const held = backend.reservations.filter((r) => r.status === 'held');
      assert.equal(held.length, 1, `${day} ${hour}`);
      assert.ok(held[0].expires_at > backend.nowMs());
      for (let n = 1; n <= STEPS.length; n++) await runStep(n, { backend, bots });
      const res = backend.reservations.filter((r) => r.user_id === ALI).at(-1);
      assert.equal(res.status, 'picked', `${day} ${hour}`);
      assert.equal(stock(backend, PHARMACY, 'paracetamol-500').qty, 2);
      assert.match(last(bots[ALI]), /berildi/);
      assert.match(bots[DILNOZA].messages.map((m) => m.html).join('\n'), /Berildi: <b>Paratsetamol 500 mg<\/b> × 2/);
      const night = new Date(backend.nowMs() + 5 * HOUR);
      assert.equal(night.getUTCHours(), 3, 'story jumps to 03:00 Tashkent');
    }
  }
});

test('story texts: night filter hides closed pharmacies, nearest and cheapest are both marked', async () => {
  const { backend, bots } = world(at('2026-12-31', 23, 10));
  await runStep(1, { backend, bots });
  const day = last(bots[ALI]);
  assert.match(day, /eng yaqin/);
  assert.match(day, /eng arzon/);
  await runStep(2, { backend, bots });
  await runStep(3, { backend, bots });
  const night = bots[ALI].messages.find((m) => m.kb.some((r) => r.some((b) => b.data === 'o:paracetamol-500:50:0')));
  assert.ok(night.html.includes('Sokin Tun 24') && !night.html.includes('Oq Terak'));
  assert.equal(new Date(backend.nowMs()).getUTCFullYear(), 2026); // 03:00 on 1 January in Tashkent is still 2026 UTC
});

test('expiry releases the stock and tells the customer', () => {
  const w = world(at('2027-02-28', 21));
  const before = stock(w.backend, PHARMACY, 'paracetamol-500').reserved;
  w.backend.reserve(ALI, PHARMACY, 'paracetamol-500', 3);
  w.backend.skipHours(2);
  assert.equal(stock(w.backend, PHARMACY, 'paracetamol-500').reserved, before);
  assert.match(last(w.bots[ALI]), /muddati o'tdi/);
  assert.ok(w.backend.reservations.filter((r) => r.user_id === SARDOR && r.status === 'expired').length >= 1);
});

test('price alert fires once when a pharmacist lowers the price', () => {
  const w = world(at('2026-11-20', 12));
  w.backend.addAlert(ALI, 'paracetamol-500', 3, 4000);
  w.backend.tick();
  assert.equal(w.backend.myAlerts(ALI).length, 1);
  w.backend.setStock(DILNOZA, 'paracetamol-500', 10, '3 900');
  assert.match(last(w.bots[ALI]), /Topildi!.*3 900 so'm/s);
  assert.equal(w.backend.myAlerts(ALI).length, 0);
  w.backend.setStock(DILNOZA, 'paracetamol-500', 12, 3800);
  assert.equal(w.bots[ALI].messages.filter((m) => m.html.includes('Topildi!')).length, 1);
});

test('buttons are validated, rx cannot be reserved, roles hold', () => {
  const w = world(at('2026-11-20', 12));
  const ali = w.bots[ALI];
  for (const data of ['m:evil', 'q:paracetamol-500:2:9', 'o:paracetamol-500:37:0', 'p:paracetamol-500:2:50:5', 'zz', 'd:atlantis']) {
    ali.press(ali.messages.at(-1).id, data);
    assert.equal(w.alerts.at(-1), 'Bu tugma eskirgan. Bosh menyudan boshlang.', data);
  }
  ali.press(ali.messages.at(-1).id, 'q:amoxicillin-500:2:1');
  assert.match(w.alerts.at(-1), /retsept/);
  ali.press(ali.messages.at(-1).id, 'n:pharm');
  assert.equal(w.alerts.at(-1), "Bu bo'lim siz uchun emas.");
  ali.type('Ибупрофен');
  assert.ok(ali.messages.at(-1).kb.flat().some((b) => b.text === 'Ibuprofen 200 mg'));
  tap(ali, /^m:ibuprofen-200$/);
  assert.match(last(ali), /eng yaqin/);
});

test('Mini App API stand-in: same shapes and refusals as the server', async () => {
  const w = world(at('2026-11-20', 12));
  const api = apiFor(w.backend, ALI);
  const me = await api.me();
  assert.equal(me.location.district, 'mirobod');
  const offers = await api.offers({ med: 'paracetamol-500', lat: me.location.lat, lon: me.location.lon, w: 50, open: false });
  assert.deepEqual([offers.nearest, offers.cheapest], [1, 12]);
  assert.ok(offers.items.every((i) => 'score' in i && 'status' in i && !('qty' in i)));
  await assert.rejects(api.pharm(), { code: 'forbidden' });
  const res = await api.reserve({ pharmacy: 2, med: 'paracetamol-500', qty: 1 });
  const ph = apiFor(w.backend, DILNOZA);
  await assert.rejects(ph.pharmConfirm('000000'), { code: 'code_not_found' });
  assert.equal((await ph.pharmConfirm(res.code)).status, 'picked');
  const csv = await ph.pharmExport();
  assert.ok(csv.startsWith('med,name,price,qty,reserved\r\n'));
  const imp = await ph.pharmImport('med,price,qty\nparacetamol-500,4700,8\n=cmd(),1,1\n');
  assert.deepEqual([imp.updated, imp.errors.map((e) => e.code)], [1, ['med']]);
  await assert.rejects(ph.pharmImport('a,b\n'), { code: 'csv_header' });
});
