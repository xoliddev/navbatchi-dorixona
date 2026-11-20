// JS port of navbatchi/i18n.py (+ data.med_label): locale templates with escaped params and the small formatters.
// Used by the Mini App and by the browser demo's bot simulator, so every screen reads the same locale JSON.
import { fmtDistance } from './geo.js';
import { hhmm, TZ_OFFSET_MS } from './hours.js';
import { fmt } from './money.js';

const UNITS_RU = { mg: 'мг', mcg: 'мкг', g: 'г', ml: 'мл' };

export class Raw {
  constructor(html) {
    this.html = String(html);
  }

  toString() {
    return this.html;
  }
}

export const escapeHtml = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export function render(template, params = {}) {
  return template.replace(/\{(\w+)\}/g, (m, k) => {
    if (!(k in params)) return m;
    const v = params[k];
    return v instanceof Raw ? v.html : escapeHtml(v);
  });
}

export const normLang = (code) => (code && String(code).slice(0, 2).toLowerCase() === 'ru' ? 'ru' : 'uz');

/** t(lang, key, params) over {uz, ru} catalogs, falling back to Uzbek, then to the key. */
export function makeT(catalogs) {
  return (lang, key, params) => {
    const l = normLang(lang);
    const template = catalogs[l]?.[key] ?? catalogs.uz?.[key] ?? key;
    return render(template, params);
  };
}

export function strength(med, lang) {
  let s = med.strength.replace(/\./g, ',');
  if (lang === 'ru') {
    const [num, unit] = s.split(' ');
    if (unit in UNITS_RU) s = `${num} ${UNITS_RU[unit]}`;
  }
  return s;
}

export const medLabel = (med, lang) => `${med.name[lang] ?? med.name.uz} ${strength(med, lang)}`;
export const price = (n) => fmt(n);
export const dist = (lang, m) => fmtDistance(m, lang);
export const clock = (ms) => hhmm(Math.floor((ms + TZ_OFFSET_MS) / 60_000) % 1440);

export function openText(t, lang, st) {
  if (st.open) return st.h24 ? t(lang, 'open.h24') : t(lang, 'open.until', { time: st.until });
  if (st.day === 0) return t(lang, 'open.opens_today', { time: st.opens });
  if (st.day === 1) return t(lang, 'open.opens_tomorrow', { time: st.opens });
  return t(lang, 'open.opens_later', { n: st.day, time: st.opens });
}

export function ago(t, lang, thenMs, nowMs) {
  const minutes = Math.max(0, Math.floor((nowMs - thenMs) / 60_000));
  if (minutes < 1) return t(lang, 'ago.now');
  if (minutes < 60) return t(lang, 'ago.min', { n: minutes });
  if (minutes < 1440) return t(lang, 'ago.hour', { n: Math.floor(minutes / 60) });
  return t(lang, 'ago.day', { n: Math.floor(minutes / 1440) });
}

export function stockLevel(t, lang, n) {
  if (n <= 0) return t(lang, 'stock.none');
  if (n <= 3) return t(lang, 'stock.few', { n });
  return t(lang, n < 20 ? 'stock.some' : 'stock.many', { n });
}

export const hoursText = (t, lang, spec) => (spec === '24/7' ? t(lang, 'open.h24') : spec);
