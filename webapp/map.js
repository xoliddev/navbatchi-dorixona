// Leaflet wrapper: OpenStreetMap tiles, a "you are here" dot and price pins coloured by role
// (nearest = blue, cheapest = green, best choice = amber). Leaflet 1.9.4 is vendored in ./vendor/leaflet.
const TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

export function createMap(el, { center, attribution, onPick }) {
  const L = window.L;
  const map = L.map(el, { zoomControl: false, attributionControl: true, tapTolerance: 20 }).setView(center, 13);
  L.tileLayer(TILES, { maxZoom: 19, minZoom: 10, attribution, crossOrigin: true }).addTo(map);
  map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  const pins = L.layerGroup().addTo(map);
  const byId = new Map();
  let you = null;

  function setUser(lat, lon, label) {
    if (you) you.remove();
    you = L.marker([lat, lon], {
      icon: L.divIcon({ className: 'nd-you', html: '<i></i>', iconSize: [22, 22], iconAnchor: [11, 11] }),
      keyboard: false, zIndexOffset: 1000, title: label,
    }).addTo(map);
  }

  /** items: [{pharmacy_id, lat, lon, priceText, open}], roles: {nearest, cheapest, best}. */
  function setOffers(items, roles, user) {
    pins.clearLayers();
    byId.clear();
    for (const it of items) {
      const kinds = ['best', 'nearest', 'cheapest'].filter((k) => roles[k] === it.pharmacy_id);
      const cls = ['nd-pin', ...kinds.map((k) => `is-${k}`), it.open ? '' : 'is-closed'].filter(Boolean).join(' ');
      const marker = L.marker([it.lat, it.lon], {
        icon: L.divIcon({ className: cls, html: `<span>${it.priceText}</span>`, iconSize: null, iconAnchor: [0, 0] }),
        zIndexOffset: kinds.length ? 500 : 0, riseOnHover: true, title: it.title,
      });
      marker.on('click', () => onPick?.(it.pharmacy_id));
      marker.addTo(pins);
      marker.getElement()?.setAttribute('data-pid', String(it.pharmacy_id));
      byId.set(it.pharmacy_id, marker);
    }
    const focus = items.filter((i) => [roles.nearest, roles.cheapest, roles.best].includes(i.pharmacy_id));
    const pts = (focus.length ? focus : items).map((i) => [i.lat, i.lon]);
    if (user) pts.push([user.lat, user.lon]);
    if (pts.length > 1) map.fitBounds(L.latLngBounds(pts), { padding: [36, 36], maxZoom: 15, animate: false });
    else if (pts.length === 1) map.setView(pts[0], 14, { animate: false });
  }

  function focusOn(pid) {
    const m = byId.get(pid);
    if (m) map.panTo(m.getLatLng(), { animate: true });
  }

  return {
    setUser, setOffers, focus: focusOn,
    center: (lat, lon) => map.setView([lat, lon], 13, { animate: false }),
    invalidate: () => map.invalidateSize({ animate: false }),
    destroy: () => map.remove(),
  };
}
