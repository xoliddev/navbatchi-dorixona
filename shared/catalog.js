// JS port of navbatchi/core/catalog.py: medicine search and brand <-> generic analogs.
import { MAX_QUERY, wordScore, words } from './text.js';

export const LIMIT = 8;
const INN_PENALTY = 3;
const keyCache = new WeakMap();

export function medKeys(med) {
  if (keyCache.has(med)) return keyCache.get(med);
  const own = [words(med.name.uz), words(med.name.ru), ...(med.aliases ?? []).map(words)];
  const inn = [words(med.inn)];
  const out = med.brand ? [own, inn] : [[...own, ...inn], []];
  keyCache.set(med, out);
  return out;
}

export function nameScore(query, name) {
  let total = 0;
  const used = new Set();
  for (const q of query) {
    let best = null;
    name.forEach((w, i) => {
      if (used.has(i)) return;
      const s = wordScore(q, w);
      if (s !== null && (best === null || s < best[0])) best = [s, i];
    });
    if (best === null) return null;
    total += best[0];
    used.add(best[1]);
  }
  return total;
}

export function medScore(query, med) {
  const [own, inn] = medKeys(med);
  const scores = [];
  for (const n of own) { const s = nameScore(query, n); if (s !== null) scores.push(s); }
  for (const n of inn) { const s = nameScore(query, n); if (s !== null) scores.push(s + INN_PENALTY); }
  return scores.length ? Math.min(...scores) : null;
}

const isDigits = (w) => /^\d+$/.test(w);

export function search(meds, text, limit = LIMIT) {
  const clipped = Array.from(String(text ?? '')).slice(0, MAX_QUERY).join('');
  const all = words(clipped);
  const query = all.filter((w) => !isDigits(w));
  const digits = all.filter(isDigits);
  if (!query.length || query.reduce((n, q) => n + q.length, 0) < 2) return [];
  const hits = [];
  for (const med of meds) {
    if (digits.length && !digits.every((d) => words(med.strength).includes(d))) continue;
    const score = medScore(query, med);
    if (score !== null) hits.push({ id: med.id, score, brand: med.brand ? 1 : 0 });
  }
  hits.sort((a, b) => a.score - b.score || a.brand - b.brand || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return hits.slice(0, limit).map(({ id, score }) => ({ id, score }));
}

export function analogs(meds, medId) {
  const base = meds.find((m) => m.id === medId);
  if (!base) return [];
  return meds.filter((m) => m.id !== medId && m.inn === base.inn && m.strength === base.strength && m.form === base.form)
    .map((m) => m.id);
}

export function cheaperAnalogs(meds, medId, minPrice) {
  const own = minPrice[medId];
  const out = [];
  for (const id of analogs(meds, medId)) {
    const p = minPrice[id];
    if (p !== undefined && p !== null && (own === undefined || own === null || p < own)) {
      out.push({ id, price: p, saving: own === undefined || own === null ? 0 : own - p });
    }
  }
  out.sort((a, b) => a.price - b.price || (a.id < b.id ? -1 : 1));
  return out;
}
