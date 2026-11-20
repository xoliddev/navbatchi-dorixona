// JS port of navbatchi/core/geo.py.
export const EARTH_M = 6_371_000;
export const TASHKENT = [41.3111, 69.2797];
const RAD = Math.PI / 180;

export function haversineM(lat1, lon1, lat2, lon2) {
  const p1 = lat1 * RAD;
  const p2 = lat2 * RAD;
  const dp = p2 - p1;
  const dl = (lon2 - lon1) * RAD;
  const s1 = Math.sin(dp / 2);
  const s2 = Math.sin(dl / 2);
  const a = s1 * s1 + Math.cos(p1) * Math.cos(p2) * s2 * s2;
  return Math.floor(2 * EARTH_M * Math.asin(Math.min(1, Math.sqrt(a))) + 0.5);
}

export function validPoint(lat, lon) {
  const la = Number(lat);
  const lo = Number(lon);
  return lat !== null && lon !== null && lat !== '' && lon !== '' && Number.isFinite(la) && Number.isFinite(lo)
    && la >= -90 && la <= 90 && lo >= -180 && lo <= 180;
}

export function nearestDistrict(lat, lon, districts) {
  let best = null;
  for (const d of districts) {
    const m = haversineM(lat, lon, d.lat, d.lon);
    if (!best || m < best[0] || (m === best[0] && d.id < best[1])) best = [m, d.id];
  }
  return best?.[1] ?? null;
}

export function fmtDistance(m, lang = 'uz') {
  if (m < 1000) return `${m} ${lang === 'ru' ? 'м' : 'm'}`;
  const tenths = Math.floor((m + 50) / 100);
  return `${Math.floor(tenths / 10)},${tenths % 10} ${lang === 'ru' ? 'км' : 'km'}`;
}
