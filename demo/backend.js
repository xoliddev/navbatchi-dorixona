// In-browser stand-in for the server: the same rules as navbatchi/service.py and staff.py, on the JS port of the
// core. Nothing leaves the browser. The clock can be moved forward ("+1 soat") to watch hours and holds change.
import { cheaperAnalogs, analogs, search } from '../shared/catalog.js';
import { haversineM, nearestDistrict, validPoint } from '../shared/geo.js';
import { status } from '../shared/hours.js';
import { rank } from '../shared/rank.js';
import * as rules from '../shared/reserve.js';
import { match, RADII_KM, MAX_ALERTS_PER_USER } from '../shared/alerts.js';
import { parsePrice, parseQty } from '../shared/money.js';
import { CsvError, parseStock, toCsv } from '../shared/csvio.js';
import { stockRows } from '../shared/seedgen.js';

const HOUR = 3_600_000;

export class Refused extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

const wrap = (fn) => {
  try {
    return fn();
  } catch (e) {
    if (e instanceof rules.ReserveError || e instanceof CsvError) throw new Refused(e.code);
    throw e;
  }
};

export class DemoBackend {
  constructor({ now = () => Date.now(), meds, pharmacies, districts, rng = null }) {
    this.realNow = now;
    this.offset = 0;
    this.meds = meds;
    this.byId = Object.fromEntries(meds.map((m) => [m.id, m]));
    this.pharmacies = pharmacies;
    this.districts = districts;
    this.users = {};
    this.stock = new Map();
    this.reservations = [];
    this.alerts = [];
    this.nextId = 1;
    this.rng = rng ?? ((n) => crypto.getRandomValues(new Uint32Array(1))[0] % n);
    this.listeners = new Set();
    for (const r of stockRows(pharmacies, meds, this.nowMs())) {
      this.stock.set(`${r.pharmacy_id}:${r.med_id}`, { ...r, reserved: 0, updated_at: r.updated_ms });
    }
  }

  // ── clock and events ──
  nowMs() { return this.realNow() + this.offset; }
  skipHours(n) {
    this.offset += n * HOUR;
    this.tick();
    this.emit({ type: 'clock', now: this.nowMs() });
  }
  /** Move forward to the next HH:MM in Tashkent. */
  setLocal(hour, minute = 0) {
    const cur = Math.floor((this.nowMs() + 5 * HOUR) / 60_000) % 1440;
    const ahead = ((hour * 60 + minute - cur) % 1440 + 1440) % 1440 || 1440;
    this.offset += ahead * 60_000;
    this.tick();
    this.emit({ type: 'clock', now: this.nowMs() });
  }
  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  emit(ev) { for (const fn of this.listeners) fn(ev); }
  tick() {
    for (const r of this.expireDue()) this.emit({ type: 'expired', to: r.user_id, res: r });
    for (const a of this.runAlerts()) this.emit({ type: 'alert', to: a.user_id, alert: a });
  }

  // ── users ──
  addUser(id, name, lang = 'uz', extra = {}) {
    this.users[id] = { id, name, lang, role: 'customer', pharmacy_id: null, lat: null, lon: null, district: null, ...extra };
    return this.users[id];
  }
  user(uid) { return this.users[uid]; }
  setLang(uid, lang) {
    if (!['uz', 'ru'].includes(lang)) throw new Refused('generic');
    this.users[uid].lang = lang;
  }
  setLocation(uid, lat, lon) {
    if (!validPoint(lat, lon)) throw new Refused('location');
    const u = this.users[uid];
    Object.assign(u, { lat: Number(lat), lon: Number(lon), district: nearestDistrict(Number(lat), Number(lon), this.districts) });
    return u.district;
  }
  setDistrict(uid, did) {
    const d = this.districts.find((x) => x.id === did);
    if (!d) throw new Refused('location');
    Object.assign(this.users[uid], { lat: d.lat, lon: d.lon, district: d.id });
    return d;
  }

  // ── search and offers ──
  search(text) { return search(this.meds, String(text ?? '').slice(0, 64)).map((h) => this.byId[h.id]); }
  med(id) {
    const m = this.byId[id];
    if (!m) throw new Refused('not_found');
    return m;
  }
  pharmacy(pid) {
    const p = this.pharmacies.find((x) => x.id === pid);
    if (!p) throw new Refused('not_found');
    return p;
  }
  rawOffers(medId) {
    const out = [];
    for (const p of this.pharmacies) {
      const s = this.stock.get(`${p.id}:${medId}`);
      if (!s) continue;
      out.push({ pharmacy_id: p.id, price: s.price, available: s.qty - s.reserved, qty: s.qty, updated_at: s.updated_at,
        lat: p.lat, lon: p.lon, hours: p.hours, off: p.off, name: p.name, phone: p.phone, address_uz: p.address.uz,
        address_ru: p.address.ru, district: p.district });
    }
    return out;
  }
  offers(medId, lat, lon, { weight = 50, openOnly = false } = {}) {
    const med = this.med(medId);
    if (!validPoint(lat, lon)) throw new Refused('location');
    const now = this.nowMs();
    const res = rank(this.rawOffers(medId), lat, lon, now, { weight, openOnly });
    const minOf = (items) => (items.length ? Math.min(...items.map((i) => i.price)) : null);
    const prices = { [medId]: minOf(res.items) };
    for (const aid of analogs(this.meds, medId)) prices[aid] = minOf(rank(this.rawOffers(aid), lat, lon, now, { weight, openOnly }).items);
    const mins = Object.fromEntries(Object.entries(prices).filter(([, v]) => v !== null));
    return { ...res, med, analogs: cheaperAnalogs(this.meds, medId, mins), now };
  }
  offerAt(medId, pid, lat, lon) {
    const row = this.rawOffers(medId).find((r) => r.pharmacy_id === pid);
    if (!row) throw new Refused('not_found');
    return { ...row, dist: haversineM(lat, lon, row.lat, row.lon), status: status(row.hours, row.off, this.nowMs()) };
  }

  // ── reservations ──
  reserve(uid, pid, medId, qty) {
    const med = this.med(medId);
    const s = this.stock.get(`${pid}:${medId}`);
    if (!s) throw new Refused('not_found');
    const active = this.reservations.filter((r) => r.user_id === uid && r.status === 'held').length;
    wrap(() => rules.check(Boolean(med.rx), qty, s.qty - s.reserved, active));
    const used = new Set(this.reservations.filter((r) => r.pharmacy_id === pid && r.status === 'held').map((r) => r.code));
    let code = rules.makeCode(this.rng(1_000_000));
    while (used.has(code)) code = rules.makeCode(this.rng(1_000_000));
    s.reserved += qty;
    const now = this.nowMs();
    const res = { id: this.nextId++, user_id: uid, pharmacy_id: pid, med_id: medId, qty, price: s.price, code, status: 'held',
      created_at: now, expires_at: rules.expiresAt(now), done_at: null, done_by: null };
    this.reservations.push(res);
    this.emit({ type: 'new_res', res, to: this.staffOf(pid) });
    return { ...res };
  }
  staffOf(pid) { return Object.values(this.users).filter((u) => u.role === 'pharmacist' && u.pharmacy_id === pid).map((u) => u.id); }
  release(res, next, by = null) {
    if (res.status !== 'held') return false;
    const s = this.stock.get(`${res.pharmacy_id}:${res.med_id}`);
    res.status = next;
    res.done_at = this.nowMs();
    res.done_by = by;
    if (next === 'picked') {
      s.qty -= res.qty;
      s.updated_at = this.nowMs();
    }
    s.reserved -= res.qty;
    return true;
  }
  myReservations(uid) {
    return this.reservations.filter((r) => r.user_id === uid)
      .sort((a, b) => (a.status !== 'held') - (b.status !== 'held') || b.id - a.id).slice(0, 10).map((r) => ({ ...r }));
  }
  cancel(uid, rid) {
    const res = this.reservations.find((r) => r.id === rid && r.user_id === uid);
    if (!res) throw new Refused('not_found');
    wrap(() => rules.move(res.status, 'cancel'));
    this.release(res, 'cancelled');
    return { ...res };
  }
  expireDue() {
    const now = this.nowMs();
    return this.reservations.filter((r) => r.status === 'held' && r.expires_at <= now)
      .filter((r) => this.release(r, 'expired')).map((r) => ({ ...r }));
  }

  // ── alerts ──
  addAlert(uid, medId, km, maxPrice = null) {
    this.med(medId);
    const u = this.users[uid];
    if (u.lat === null) throw new Refused('no_location');
    if (!RADII_KM.includes(km)) throw new Refused('generic');
    let price = null;
    if (maxPrice !== null && maxPrice !== '' && maxPrice !== undefined) {
      try { price = parsePrice(maxPrice); } catch { throw new Refused('price'); }
    }
    if (this.alerts.filter((a) => a.user_id === uid && a.fired_at === null).length >= MAX_ALERTS_PER_USER) {
      throw new Refused('too_many_alerts');
    }
    const a = { id: this.nextId++, user_id: uid, med_id: medId, lat: u.lat, lon: u.lon, radius_m: km * 1000,
      max_price: price, created_at: this.nowMs(), fired_at: null, pharmacy_id: null, price: null };
    this.alerts.push(a);
    return { ...a };
  }
  myAlerts(uid) { return this.alerts.filter((a) => a.user_id === uid && a.fired_at === null).map((a) => ({ ...a })); }
  deleteAlert(uid, aid) {
    const i = this.alerts.findIndex((a) => a.id === aid && a.user_id === uid && a.fired_at === null);
    if (i < 0) throw new Refused('not_found');
    this.alerts.splice(i, 1);
  }
  runAlerts() {
    const fired = [];
    for (const a of this.alerts.filter((x) => x.fired_at === null)) {
      const hit = match(a, this.rawOffers(a.med_id));
      if (!hit) continue;
      Object.assign(a, { fired_at: this.nowMs(), pharmacy_id: hit.pharmacy_id, price: hit.price });
      fired.push({ ...a, ...hit });
    }
    return fired;
  }

  // ── pharmacist ──
  pharmacyOf(uid) {
    const u = this.users[uid];
    if (!u || u.role !== 'pharmacist' || !u.pharmacy_id) throw new Refused('forbidden');
    return u.pharmacy_id;
  }
  stockList(uid) {
    const pid = this.pharmacyOf(uid);
    return this.meds.map((m) => this.stock.get(`${pid}:${m.id}`)).filter(Boolean).map((s) => ({ ...s }));
  }
  putStock(pid, medId, qty, price) {
    const key = `${pid}:${medId}`;
    const s = this.stock.get(key);
    if (s && qty < s.reserved) return false;
    this.stock.set(key, { pharmacy_id: pid, med_id: medId, reserved: s?.reserved ?? 0, qty, price, updated_at: this.nowMs() });
    return true;
  }
  setStock(uid, medId, qty, price) {
    const pid = this.pharmacyOf(uid);
    this.med(medId);
    let q;
    let p;
    try { q = parseQty(qty); p = parsePrice(price); } catch { throw new Refused('stock_value'); }
    if (!this.putStock(pid, medId, q, p)) throw new Refused('below_reserved');
    this.tick();
    return { ...this.stock.get(`${pid}:${medId}`) };
  }
  importCsv(uid, text) {
    const pid = this.pharmacyOf(uid);
    let parsed;
    try { parsed = parseStock(text, this.meds); } catch (e) { throw new Refused(`csv_${e.code}`); }
    const errors = [...parsed.errors];
    let updated = 0;
    for (const r of parsed.rows) {
      if (this.putStock(pid, r.med, r.qty, r.price)) updated += 1;
      else errors.push({ line: 0, code: 'below_reserved', med: r.med });
    }
    this.tick();
    return { updated, errors };
  }
  exportCsv(uid) {
    const rows = this.stockList(uid).map((r) => [r.med_id, this.byId[r.med_id].name.uz, r.price, r.qty, r.reserved]);
    return toCsv([['med', 'name', 'price', 'qty', 'reserved'], ...rows]);
  }
  pharmReservations(uid) {
    const pid = this.pharmacyOf(uid);
    return this.reservations.filter((r) => r.pharmacy_id === pid)
      .sort((a, b) => (a.status !== 'held') - (b.status !== 'held') || (a.status === 'held' ? a.expires_at - b.expires_at : b.id - a.id))
      .slice(0, 20).map((r) => ({ ...r }));
  }
  confirmCode(uid, code) {
    const pid = this.pharmacyOf(uid);
    const clean = rules.cleanCode(code);
    if (clean === null) throw new Refused('code');
    const res = this.reservations.find((r) => r.pharmacy_id === pid && r.code === clean && r.status === 'held');
    if (!res) throw new Refused('code_not_found');
    if (res.expires_at <= this.nowMs()) throw new Refused('code_expired');
    this.release(res, 'picked', uid);
    this.emit({ type: 'picked', to: res.user_id, res: { ...res } });
    return { ...res };
  }
}
