// The bot, simulated in the page (ports navbatchi/bot/handlers_*.py): the same buttons, callback data and texts.
// Messages are {id, from: 'bot' | 'me', html, kb, at}; pressing a button edits that message like Telegram does.
import { clock, dist, medLabel, price } from '../shared/i18n.js';
import { RADII_KM } from '../shared/alerts.js';
import { Refused } from './backend.js';

const WEIGHTS = new Set([0, 50, 100]);
const strip = (html) => html.replace(/<[^>]+>/g, '').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

export class BotSim {
  constructor(backend, uid, t, views, { onChange = () => {}, onAlert = () => {} } = {}) {
    Object.assign(this, { b: backend, uid, t, v: views, onChange, onAlert });
    this.messages = [];
    this.state = null;
    this.data = {};
    this.ids = 1;
  }

  get user() { return this.b.user(this.uid); }
  get lang() { return this.user.lang; }

  push(screen, from = 'bot') {
    const msg = { id: this.ids++, from, html: screen.html, kb: screen.kb ?? [], at: this.b.nowMs() };
    this.messages.push(msg);
    this.onChange();
    return msg;
  }

  edit(id, screen) {
    const msg = this.messages.find((m) => m.id === id);
    if (!msg) return this.push(screen);
    Object.assign(msg, { html: screen.html, kb: screen.kb ?? [] });
    this.onChange();
    return msg;
  }

  show(id, screen) { return id ? this.edit(id, screen) : this.push(screen); }

  guard(fn, typed = false) {
    try {
      return fn();
    } catch (e) {
      if (!(e instanceof Refused)) throw e;
      const key = this.t(this.lang, `err.${e.code}`) === `err.${e.code}` ? 'err.generic' : `err.${e.code}`;
      if (typed) return this.push({ html: this.t(this.lang, key) });
      this.onAlert(strip(this.t(this.lang, key)));
      return null;
    }
  }

  start() {
    this.push({ html: '/start' }, 'me');
    this.state = null;
    this.push(this.v.mainMenu(this.lang, this.user, true));
  }

  type(text) {
    this.push({ html: text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }, 'me');
    this.guard(() => this.onText(text.trim()), true);
  }

  shareLocation(lat, lon) {
    this.push({ html: this.t(this.lang, 'demo.location') }, 'me');
    this.guard(() => {
      this.b.setLocation(this.uid, lat, lon);
      this.afterLocation(null);
    }, true);
  }

  onText(text) {
    if (this.state === 'pharm_code') {
      const res = this.b.confirmCode(this.uid, text);
      const left = this.b.stockList(this.uid).find((s) => s.med_id === res.med_id)?.qty ?? 0;
      this.state = null;
      this.push({ html: this.t(this.lang, 'pharm.code_ok', { med: medLabel(this.b.byId[res.med_id], this.lang), qty: res.qty,
        total: price(res.qty * res.price), left }) });
      return this.pharmHome(null);
    }
    if (this.state === 'alert_price') return this.saveAlert(null, text.slice(0, 20));
    return this.push(this.v.searchResults(this.lang, text.slice(0, 64), this.b.search(text)));
  }

  afterLocation(id) {
    const pending = this.data.pendingMed;
    if (pending) {
      this.data.pendingMed = null;
      return this.offers(id, pending, 50, 0);
    }
    const district = this.b.districts.find((d) => d.id === this.user.district).name[this.lang];
    this.push({ html: this.t(this.lang, 'loc.saved', { district }) });
    return this.push(this.v.mainMenu(this.lang, this.user));
  }

  offers(id, medId, w, o) {
    const u = this.user;
    if (u.lat === null) throw new Refused('no_location');
    const res = this.b.offers(medId, u.lat, u.lon, { weight: w, openOnly: Boolean(o) });
    for (const a of res.analogs) a.label = medLabel(this.b.byId[a.id], this.lang);
    const district = this.b.districts.find((d) => d.id === u.district).name[this.lang];
    return this.show(id, this.v.offers(this.lang, res, district, w, o));
  }

  pharmHome(id) {
    const pid = this.b.pharmacyOf(this.uid);
    const held = this.b.pharmReservations(this.uid).filter((r) => r.status === 'held').length;
    this.state = null;
    return this.show(id, this.v.pharmMenu(this.lang, this.b.pharmacy(pid), held));
  }

  myList(id) {
    const items = this.b.myReservations(this.uid).map((r) => [r, this.b.byId[r.med_id], this.b.pharmacy(r.pharmacy_id)]);
    return this.show(id, this.v.myList(this.lang, items, this.b.nowMs()));
  }

  saveAlert(id, maxPrice) {
    const a = this.b.addAlert(this.uid, this.data.alertMed, this.data.alertKm, maxPrice);
    this.state = null;
    return this.show(id, this.v.alertOk(this.lang, a, this.b.byId[a.med_id]));
  }

  /** A button press. Unknown or tampered data gets the same "stale button" answer as the real bot. */
  press(id, data) {
    const r = this.guard(() => this.route(id, String(data)));
    if (r === false) this.onAlert(strip(this.t(this.lang, 'err.stale')));
  }

  route(id, data) {
    const [kind, ...p] = data.split(':');
    const lang = this.lang;
    const isMed = (m) => m in this.b.byId;
    if (kind === 'n') {
      const to = p[0];
      if (to === 'menu') { this.state = null; return this.edit(id, this.v.mainMenu(lang, this.user)); }
      if (to === 'lang') { this.b.setLang(this.uid, lang === 'uz' ? 'ru' : 'uz'); return this.edit(id, this.v.mainMenu(this.lang, this.user)); }
      if (to === 'search') { this.state = null; return this.edit(id, this.v.searchAsk(lang)); }
      if (to === 'loc') return this.edit(id, this.v.locAsk(lang, this.b.districts, this.user));
      if (to === 'my') return this.myList(id);
      if (to === 'alerts') {
        this.state = null;
        return this.edit(id, this.v.alertsList(lang, this.b.myAlerts(this.uid).map((a) => [a, this.b.byId[a.med_id]])));
      }
      if (to === 'pharm') return this.pharmHome(id);
      if (to === 'code') { this.b.pharmacyOf(this.uid); this.state = 'pharm_code'; return this.edit(id, this.v.ask(lang, 'pharm.code_ask')); }
      if (to === 'held') {
        const items = this.b.pharmReservations(this.uid).map((x) => [x, this.b.byId[x.med_id]]);
        return this.edit(id, this.v.pharmHeld(lang, items));
      }
      if (['csv_in', 'csv_out', 'admin', 'invite', 'addph'].includes(to)) throw new Refused('forbidden');
      return false;
    }
    if (kind === 'm' && isMed(p[0])) {
      if (this.user.lat === null) {
        this.data.pendingMed = p[0];
        return this.edit(id, this.v.locAsk(lang, this.b.districts, this.user));
      }
      return this.offers(id, p[0], 50, 0);
    }
    if (kind === 'd' && this.b.districts.some((d) => d.id === p[0])) {
      this.b.setDistrict(this.uid, p[0]);
      return this.afterLocation(id);
    }
    const [w, o] = [Number(p[1]), Number(p[2])];
    if (kind === 'o' && isMed(p[0]) && WEIGHTS.has(w) && (o === 0 || o === 1)) return this.offers(id, p[0], w, o);
    const [pid, pw, po] = [Number(p[1]), Number(p[2]), Number(p[3])];
    if (kind === 'p' && isMed(p[0]) && Number.isInteger(pid) && WEIGHTS.has(pw) && (po === 0 || po === 1)) {
      const u = this.user;
      if (u.lat === null) throw new Refused('no_location');
      const item = this.b.offerAt(p[0], pid, u.lat, u.lon);
      return this.edit(id, this.v.card(lang, item, this.b.byId[p[0]], pw, po, this.b.nowMs()));
    }
    const n = Number(p[2]);
    if (kind === 'q' && isMed(p[0]) && Number.isInteger(pid) && Number.isInteger(n) && n >= 0 && n <= 5) {
      const med = this.b.byId[p[0]];
      const ph = this.b.pharmacy(pid);
      if (n === 0) {
        if (med.rx) throw new Refused('rx');
        const item = this.b.offerAt(p[0], pid, this.user.lat ?? 0, this.user.lon ?? 0);
        if (item.available <= 0) throw new Refused('stock');
        return this.edit(id, this.v.qty(lang, med, ph, item.available));
      }
      const res = this.b.reserve(this.uid, pid, p[0], n);
      return this.edit(id, this.v.reserved(lang, res, med, ph));
    }
    if (kind === 'r' && /^\d+$/.test(p[0])) {
      this.b.cancel(this.uid, Number(p[0]));
      this.onAlert(strip(this.t(lang, 'res.cancelled')));
      return this.myList(id);
    }
    const km = Number(p[1]);
    if (kind === 'a' && isMed(p[0]) && (km === 0 || RADII_KM.includes(km))) {
      const med = this.b.byId[p[0]];
      if (km === 0) { this.state = null; return this.edit(id, this.v.alertRadius(lang, med)); }
      if (this.user.lat === null) throw new Refused('no_location');
      Object.assign(this.data, { alertMed: med.id, alertKm: km });
      this.state = 'alert_price';
      return this.edit(id, this.v.alertPrice(lang, med));
    }
    if (kind === 'y' && p[0] === '1' && this.state === 'alert_price') return this.saveAlert(id, null);
    if (kind === 'x' && /^\d+$/.test(p[0])) {
      this.b.deleteAlert(this.uid, Number(p[0]));
      return this.edit(id, this.v.alertsList(lang, this.b.myAlerts(this.uid).map((a) => [a, this.b.byId[a.med_id]])));
    }
    return false;
  }

  /** Something the bot sends on its own (backend event). Returns the new message. */
  deliver(ev) {
    const lang = this.lang;
    const label = (id) => medLabel(this.b.byId[id], lang);
    if (ev.type === 'new_res') {
      return this.push({ html: this.t(lang, 'pharm.new_res', { med: label(ev.res.med_id), qty: ev.res.qty, code: ev.res.code,
        until: clock(ev.res.expires_at) }) });
    }
    if (ev.type === 'picked') return this.push({ html: this.t(lang, 'res.picked', { med: label(ev.res.med_id), qty: ev.res.qty }) });
    if (ev.type === 'expired') {
      return this.push({ html: this.t(lang, 'res.expired', { med: label(ev.res.med_id), qty: ev.res.qty,
        pharmacy: this.b.pharmacy(ev.res.pharmacy_id).name }) });
    }
    if (ev.type === 'alert') {
      const a = ev.alert;
      const ph = this.b.pharmacy(a.pharmacy_id);
      return this.push({ html: this.t(lang, 'alert.fired', { med: label(a.med_id), price: price(a.price), pharmacy: ph.name,
        dist: dist(lang, a.dist) }), kb: [[{ text: this.t(lang, 'btn.view'), data: `p:${a.med_id}:${a.pharmacy_id}:50:0` }]] });
    }
    return null;
  }
}
