# Changelog

## 1.0.0 — 2026-11-21

First release (day 2 of the 30-day portfolio challenge).

- Medicine search that forgives Latin/Cyrillic, Uzbek/Russian spellings and typos (phonetic keys + edit distance);
  brands found by their ingredient, cheaper generics shown as "arzonroq analog".
- Ranking by haversine distance and price with a slider; nearest, cheapest and best choice shown together;
  "navbatchi" filter for pharmacies open right now in Asia/Tashkent time (past midnight and days off included).
- Pickup reservations: 2-hour hold, 6-digit code, atomic stock hold in `BEGIN IMMEDIATE` plus `CHECK` constraints,
  automatic release on expiry, prescription medicines cannot be reserved.
- Pharmacist panel (bot + Mini App) for their own pharmacy only: stock and price, CSV import/export with limits and
  formula-safe export, give out by code. Admin: add pharmacies, single-use pharmacist invites.
- Price alerts with an idempotent scheduler loop.
- aiogram 3 bot (buttons only, Uzbek and Russian), aiohttp Mini App API with initData HMAC + freshness checks, role
  checks on every route, rate limits, CSP; plain HTML/CSS/JS Mini App with a vendored Leaflet 1.9.4 map.
- JS port of the core with shared test vectors (pytest + `node --test`), Playwright demo test, Docker (non-root), CI.
- GitHub Pages demo: customer and pharmacist phones, guided story, Tashkent clock with "+1 soat" / "+6 soat".
