// Demo people and history, always relative to "now", so the demo works on any date and at any hour
// (also across New Year and month ends). Stock and prices come from the shared seed generator.
import { DemoBackend } from './backend.js';

export const ALI = 1001; // the customer, standing near Amir Temur square
export const SARDOR = 1003; // another customer with a reservation already waiting
export const DILNOZA = 2002; // pharmacist at "Sokin Tun 24" (24/7)
export const PHARMACY = 2;
export const HERE = [41.3111, 69.2797];
const MIN = 60_000;

export function seed(b, lang = 'uz') {
  b.addUser(ALI, 'Ali', lang, { lat: HERE[0], lon: HERE[1], district: 'mirobod' });
  b.addUser(SARDOR, 'Sardor', lang, { lat: 41.2900, lon: 69.2600, district: 'yakkasaroy' });
  b.addUser(DILNOZA, 'Dilnoza', lang, { role: 'pharmacist', pharmacy_id: PHARMACY });
  const now = b.nowMs();
  // Sardor reserved two packs of ibuprofen 40 minutes ago; it waits at the pharmacist's counter.
  const held = b.reserve(SARDOR, PHARMACY, 'ibuprofen-200', 2);
  Object.assign(b.reservations.find((r) => r.id === held.id), { created_at: now - 40 * MIN, expires_at: now + 80 * MIN });
  // Yesterday he also picked up a cardio aspirin there (history).
  const old = b.reserve(SARDOR, PHARMACY, 'acetylsalicylic-100', 1);
  const res = b.reservations.find((r) => r.id === old.id);
  b.release(res, 'picked', DILNOZA);
  Object.assign(res, { created_at: now - 26 * 60 * MIN, expires_at: now - 24 * 60 * MIN, done_at: now - 25 * 60 * MIN });
  return b;
}

export function createDemo({ now, meds, pharmacies, districts, lang = 'uz', rng } = {}) {
  return seed(new DemoBackend({ now, meds, pharmacies, districts, rng }), lang);
}
