// JS port of navbatchi/core/alerts.py: does a stock change satisfy a price alert?
import { haversineM } from './geo.js';

export const RADII_KM = [1, 3, 5, 10];
export const MAX_ALERTS_PER_USER = 5;

export function match(alert, offers) {
  let best = null;
  for (const o of offers) {
    if (o.available <= 0) continue;
    if (alert.max_price !== null && alert.max_price !== undefined && o.price > alert.max_price) continue;
    const dist = haversineM(alert.lat, alert.lon, o.lat, o.lon);
    if (dist > alert.radius_m) continue;
    const key = [o.price, dist, o.pharmacy_id];
    if (!best || key[0] < best[0][0] || (key[0] === best[0][0] && (key[1] < best[0][1]
      || (key[1] === best[0][1] && key[2] < best[0][2])))) {
      best = [key, { pharmacy_id: o.pharmacy_id, price: o.price, dist }];
    }
  }
  return best ? best[1] : null;
}
