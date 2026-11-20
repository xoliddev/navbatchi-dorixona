// The JS port of the core must give exactly what the Python core gives (shared/test_vectors.json).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import * as alerts from '../shared/alerts.js';
import * as catalog from '../shared/catalog.js';
import * as csvio from '../shared/csvio.js';
import * as geo from '../shared/geo.js';
import * as hours from '../shared/hours.js';
import * as money from '../shared/money.js';
import * as rank from '../shared/rank.js';
import * as reserve from '../shared/reserve.js';
import * as seedgen from '../shared/seedgen.js';
import * as text from '../shared/text.js';

const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url), 'utf8'));
const V = read('../shared/test_vectors.json');
const meds = read('../shared/data/meds.json');
const pharmacies = read('../shared/data/pharmacies.json');
const districts = read('../shared/data/districts.json');

function result(fn) {
  try {
    return { ok: fn() };
  } catch (e) {
    if (e instanceof reserve.ReserveError || e instanceof csvio.CsvError) return { error: e.code };
    if (e instanceof money.PriceError || /^hours:/.test(e.message)) return { error: 'invalid' };
    throw e;
  }
}

test('text folding and edit distance', () => {
  for (const v of V.words) assert.deepEqual(text.words(v.in), v.out, v.in);
  for (const v of V.distance) assert.equal(text.distance(v.a, v.b, v.limit), v.out, `${v.a}/${v.b}/${v.limit}`);
});

test('search: Latin, Cyrillic, Russian, typos, brand <-> INN, dose digits', () => {
  for (const v of V.search) assert.deepEqual(catalog.search(meds, v.q), v.out, v.q);
  for (const v of V.analogs) assert.deepEqual(catalog.analogs(meds, v.id), v.out, v.id);
  for (const v of V.cheaper) assert.deepEqual(catalog.cheaperAnalogs(meds, v.id, v.min), v.out, v.id);
});

test('geo: haversine, districts, distance labels, point validation', () => {
  for (const v of V.haversine) assert.equal(geo.haversineM(...v.p), v.out, JSON.stringify(v.p));
  for (const v of V.fmt_distance) assert.equal(geo.fmtDistance(v.m, v.lang), v.out);
  for (const v of V.valid_point) assert.equal(geo.validPoint(...v.p), v.out, JSON.stringify(v.p));
  for (const v of V.districts) assert.equal(geo.nearestDistrict(...v.p, districts), v.out);
});

test('opening hours in Tashkent time, a whole week', () => {
  for (const v of V.hours) assert.deepEqual(hours.status(v.spec, v.off, v.now), v.out, `${v.spec} @ ${v.now}`);
  for (const v of V.hours_bad) assert.deepEqual(result(() => hours.parse(v.spec)), v.out, v.spec);
});

test('ranking: nearest, cheapest, best for every slider position and the navbatchi filter', () => {
  for (const v of V.rank) {
    const got = rank.rank(V.rank_offers[v.med], 41.3111, 69.2797, v.now,
      { weight: v.weight, openOnly: v.open_only, maxM: v.max_m });
    assert.deepEqual(got, v.out, `${v.med} w=${v.weight} open=${v.open_only}`);
  }
});

test('reservation rules', () => {
  for (const v of V.reserve_check) assert.deepEqual(result(() => reserve.check(...v.in) ?? null), v.out, JSON.stringify(v.in));
  for (const v of V.codes) assert.equal(reserve.makeCode(v.n), v.out);
  for (const v of V.clean_code) assert.equal(reserve.cleanCode(v.in), v.out, v.in);
  for (const v of V.minutes_left) assert.equal(reserve.minutesLeft(v.exp, v.now), v.out);
  for (const v of V.moves) assert.deepEqual(result(() => reserve.move(v.s, v.a)), v.out, `${v.s}/${v.a}`);
});

test('price alerts', () => {
  for (const v of V.alerts) assert.deepEqual(alerts.match(v.alert, v.offers), v.out, JSON.stringify(v.alert));
});

test("money: whole so'm only", () => {
  for (const v of V.money_fmt) assert.equal(money.fmt(v.n), v.out);
  for (const v of V.money_parse) assert.deepEqual(result(() => money.parsePrice(v.in)), v.out, String(v.in));
  for (const v of V.qty_parse) assert.deepEqual(result(() => money.parseQty(v.in)), v.out, String(v.in));
});

test('CSV import limits and formula-safe export', () => {
  for (const v of V.csv) assert.deepEqual(result(() => csvio.parseStock(v.in, meds)), v.out, v.name);
  for (const v of V.safe_cell) assert.equal(csvio.safeCell(v.in), v.out, v.in);
});

test('seed generator gives the same city as Python', () => {
  for (const v of V.h32) assert.equal(seedgen.h32(v.in), v.out, v.in);
  assert.deepEqual(seedgen.stockRows(pharmacies, meds, V.seed.now), V.seed.rows);
  assert.equal(seedgen.stockRows(pharmacies, meds, V.seed_other_day.now).length, V.seed_other_day.count);
});
