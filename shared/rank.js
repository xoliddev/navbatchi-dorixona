// JS port of navbatchi/core/rank.py: nearest, cheapest and the slider-weighted "best choice".
import { haversineM } from './geo.js';
import { status } from './hours.js';

export const DEFAULT_WEIGHT = 50;
export const MAX_RESULTS = 30;
const cmp = (...pairs) => {
  for (const [a, b] of pairs) if (a !== b) return a < b ? -1 : 1;
  return 0;
};

export function rank(offers, lat, lon, nowMs, { weight = DEFAULT_WEIGHT, openOnly = false, maxM = null, limit = MAX_RESULTS } = {}) {
  const w = Math.max(0, Math.min(100, Math.trunc(Number(weight) || 0)));
  const items = [];
  for (const o of offers) {
    if (o.available <= 0) continue;
    const st = status(o.hours, o.off, nowMs);
    if (openOnly && !st.open) continue;
    const dist = haversineM(lat, lon, o.lat, o.lon);
    if (maxM !== null && dist > maxM) continue;
    items.push({ ...o, dist, status: st });
  }
  if (!items.length) return { items: [], nearest: null, cheapest: null, best: null };
  const maxD = Math.max(...items.map((i) => i.dist));
  const minP = Math.min(...items.map((i) => i.price));
  const span = Math.max(...items.map((i) => i.price)) - minP;
  for (const i of items) {
    const d = maxD ? Math.floor((i.dist * 1000) / maxD) : 0;
    const p = span ? Math.floor(((i.price - minP) * 1000) / span) : 0;
    i.score = Math.floor(((100 - w) * d + w * p) / 100);
  }
  const pick = (key) => items.reduce((best, i) => (cmp(...key(i, best)) < 0 ? i : best));
  const nearest = pick((i, b) => [[i.dist, b.dist], [i.price, b.price], [i.pharmacy_id, b.pharmacy_id]]);
  const cheapest = pick((i, b) => [[i.price, b.price], [i.dist, b.dist], [i.pharmacy_id, b.pharmacy_id]]);
  items.sort((a, b) => cmp([a.score, b.score], [a.dist, b.dist], [a.price, b.price], [a.pharmacy_id, b.pharmacy_id]));
  return { items: items.slice(0, limit), nearest: nearest.pharmacy_id, cheapest: cheapest.pharmacy_id, best: items[0].pharmacy_id };
}
