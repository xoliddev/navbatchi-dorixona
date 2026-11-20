// The Mini App's API, answered by the in-browser backend instead of HTTP (same shapes as navbatchi/web.py).
// Errors carry the same codes the server would send, so the Mini App code is identical in both places.
const ITEM_FIELDS = ['pharmacy_id', 'name', 'phone', 'address_uz', 'address_ru', 'lat', 'lon', 'hours', 'off', 'district',
  'price', 'available', 'updated_at', 'dist', 'status', 'score'];
const pick = (o, keys) => Object.fromEntries(keys.map((k) => [k, o[k]]));

export function apiFor(backend, uid) {
  const b = backend;
  const run = async (fn) => {
    try {
      return structuredClone(fn());
    } catch (e) {
      throw Object.assign(new Error(e.code ?? 'generic'), { code: e.code ?? 'generic' });
    }
  };
  const mut = (fn) => run(fn).then((r) => {
    b.emit({ type: 'changed', by: uid });
    return r;
  });
  return {
    me: () => run(() => {
      const u = b.user(uid);
      const ph = u.role === 'pharmacist' ? b.pharmacy(u.pharmacy_id) : null;
      return { id: uid, name: u.name, lang: u.lang, role: u.role, admin: false, now: b.nowMs(),
        pharmacy: ph ? { id: ph.id, name: ph.name } : null,
        location: u.lat === null ? null : { lat: u.lat, lon: u.lon, district: u.district } };
    }),
    setLang: (lang) => run(() => { b.setLang(uid, lang); return { lang }; }),
    setLocation: (body) => mut(() => {
      if ('district' in body) {
        const d = b.setDistrict(uid, body.district);
        return { lat: d.lat, lon: d.lon, district: d.id };
      }
      return { lat: body.lat, lon: body.lon, district: b.setLocation(uid, body.lat, body.lon) };
    }),
    offers: ({ med, lat, lon, w, open }) => run(() => {
      const res = b.offers(med, Number(lat), Number(lon), { weight: Number(w), openOnly: Boolean(open) });
      return { med, items: res.items.map((i) => pick(i, ITEM_FIELDS)), nearest: res.nearest, cheapest: res.cheapest,
        best: res.best, analogs: res.analogs, now: res.now };
    }),
    reserve: ({ pharmacy, med, qty }) => mut(() => b.reserve(uid, pharmacy, med, qty)),
    reservations: () => run(() => ({
      now: b.nowMs(),
      items: b.myReservations(uid).map((r) => {
        const p = b.pharmacy(r.pharmacy_id);
        return { ...r, pharmacy: { name: p.name, phone: p.phone, address_uz: p.address.uz, address_ru: p.address.ru,
          lat: p.lat, lon: p.lon } };
      }),
    })),
    cancel: (id) => mut(() => b.cancel(uid, Number(id))),
    alerts: () => run(() => ({ items: b.myAlerts(uid) })),
    addAlert: ({ med, km, max_price: maxPrice }) => mut(() => b.addAlert(uid, med, km, maxPrice)),
    delAlert: (id) => mut(() => { b.deleteAlert(uid, Number(id)); return { ok: true }; }),
    pharm: () => run(() => {
      const pid = b.pharmacyOf(uid);
      return { pharmacy: { id: pid, name: b.pharmacy(pid).name }, stock: b.stockList(uid),
        reservations: b.pharmReservations(uid), now: b.nowMs() };
    }),
    pharmStock: ({ med, qty, price }) => mut(() => b.setStock(uid, med, qty, price)),
    pharmConfirm: (code) => mut(() => b.confirmCode(uid, code)),
    pharmImport: (text) => mut(() => b.importCsv(uid, text)),
    pharmExport: () => run(() => b.exportCsv(uid)),
  };
}
