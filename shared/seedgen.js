// JS port of navbatchi/core/seedgen.py: the same demo stock and prices, relative to "now".
const PINNED = { '2:paracetamol-500': [4, 112], '1:paracetamol-500': [12, 124] };
const enc = new TextEncoder();

export function h32(text) {
  let h = 0x811c9dc5;
  for (const b of enc.encode(text)) {
    h ^= b;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

export const round100 = (n) => Math.floor((n + 50) / 100) * 100;

export function stockRow(pharmacyId, med, nowMs) {
  const r = h32(`${pharmacyId}:${med.id}`);
  const bucket = r % 100;
  const pinned = PINNED[`${pharmacyId}:${med.id}`];
  if (!pinned && bucket < 15) return null;
  let qty = bucket < 22 ? 0 : 1 + ((r >>> 8) % 30);
  let pct = 85 + ((r >>> 16) % 41);
  if (pinned) [qty, pct] = pinned;
  const minutes = 5 + ((r >>> 3) % 300);
  const updated = (Math.floor(nowMs / 60_000) - minutes) * 60_000;
  return { pharmacy_id: pharmacyId, med_id: med.id, qty, price: round100(Math.floor((med.price * pct) / 100)), updated_ms: updated };
}

export function stockRows(pharmacies, meds, nowMs) {
  const rows = [];
  for (const ph of pharmacies) {
    for (const med of meds) {
      const row = stockRow(ph.id, med, nowMs);
      if (row) rows.push(row);
    }
  }
  return rows;
}
