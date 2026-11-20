// HTTP client for the Mini App API. Every request carries Telegram's signed initData; the server checks it.
// The browser demo provides an object with the same methods that runs in the page instead.
export function httpApi(initData) {
  async function call(method, path, body, raw = false) {
    let res;
    try {
      res = await fetch(path, {
        method,
        headers: { Authorization: `tma ${initData}`, 'Content-Type': raw ? 'text/csv' : 'application/json' },
        body: body === undefined ? undefined : raw ? body : JSON.stringify(body),
      });
    } catch {
      throw Object.assign(new Error('offline'), { code: 'offline' });
    }
    if (res.ok && res.headers.get('Content-Type')?.startsWith('text/csv')) return res.text();
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(data.error ?? 'generic'), { code: data.error ?? 'generic' });
    return data;
  }
  const q = (params) => new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();
  return {
    me: () => call('GET', '/api/me'),
    setLang: (lang) => call('POST', '/api/lang', { lang }),
    setLocation: (body) => call('POST', '/api/location', body),
    offers: ({ med, lat, lon, w, open }) => call('GET', `/api/offers?${q({ med, lat, lon, w, open: open ? 1 : 0 })}`),
    reserve: (body) => call('POST', '/api/reserve', body),
    reservations: () => call('GET', '/api/reservations'),
    cancel: (id) => call('POST', `/api/reservations/${Number(id)}/cancel`),
    alerts: () => call('GET', '/api/alerts'),
    addAlert: (body) => call('POST', '/api/alerts', body),
    delAlert: (id) => call('DELETE', `/api/alerts/${Number(id)}`),
    pharm: () => call('GET', '/api/pharm'),
    pharmStock: (body) => call('POST', '/api/pharm/stock', body),
    pharmConfirm: (code) => call('POST', '/api/pharm/confirm', { code }),
    pharmImport: (text) => call('POST', '/api/pharm/import', text, true),
    pharmExport: () => call('GET', '/api/pharm/export'),
  };
}
