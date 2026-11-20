// The Mini App: mountApp(root, opts) renders into `root` and keeps all state per instance, so the browser demo can
// run two of them (the customer's and the pharmacist's phones) side by side.
import { clock, makeT, medLabel } from '../shared/i18n.js';
import { renderMap } from './screens-map.js';
import { renderMy } from './screens-my.js';
import { renderPharm } from './screens-pharm.js';
import { applyTheme, h, haptic, plain } from './util.js';

export function mountApp(root, { api, catalogs, meds, districts, lang = 'uz', tg = null, geo = null, onLang = null,
  start = null }) {
  const t = makeT(catalogs);
  const ctx = {
    root, api, tg, lang, meds, districts, geo, me: null, now: Date.now(), tab: start,
    byId: Object.fromEntries(meds.map((m) => [m.id, m])),
    state: { map: { q: '', med: null, w: 50, open: false, res: null } },
    T: (key, params) => t(ctx.lang, key, params),
    P: (key, params) => plain(t(ctx.lang, key, params)),
    label: (id) => (ctx.byId[id] ? medLabel(ctx.byId[id], ctx.lang) : id),
    time: (ms) => clock(ms),
    toast, sheet, fail, refresh, go,
  };
  root.classList.add('nd');
  applyTheme(root, tg);
  const head = h('header', { class: 'nd-head' });
  const tabs = h('nav', { class: 'nd-tabs', role: 'tablist' });
  const body = h('main', { class: 'nd-body' });
  const toasts = h('div', { class: 'nd-toasts', 'aria-live': 'polite' });
  root.replaceChildren(head, tabs, body, toasts);
  const screens = { map: renderMap, my: renderMy, pharm: renderPharm };

  function toast(html, kind = 'ok') {
    const el = h('div', { class: `nd-toast ${kind}`, html, role: 'status' });
    toasts.append(el);
    setTimeout(() => el.classList.add('out'), 2600);
    setTimeout(() => el.remove(), 3000);
  }

  function fail(err) {
    haptic(tg, 'error');
    const code = err?.code ?? 'generic';
    toast(ctx.T(catalogs[ctx.lang][`err.${code}`] ? `err.${code}` : 'err.generic'), 'bad');
  }

  /** Bottom sheet inside this app instance. `build(close)` returns the sheet's content nodes. */
  function sheet(title, build) {
    root.querySelector('.nd-backdrop')?.remove();
    const close = () => {
      wrap.classList.add('out');
      setTimeout(() => wrap.remove(), 160);
    };
    const panel = h('section', { class: 'nd-sheet', role: 'dialog', 'aria-label': plain(title) },
      h('div', { class: 'nd-sheet-head' }, h('h3', { html: title }),
        h('button', { class: 'nd-x', type: 'button', 'aria-label': ctx.P('app.close'), onclick: close }, '×')));
    const wrap = h('div', { class: 'nd-backdrop', onclick: (e) => { if (e.target === wrap) close(); } }, panel);
    panel.append(...[build(close)].flat());
    root.append(wrap);
    return close;
  }

  function paintHead() {
    head.replaceChildren(h('div', { class: 'nd-brand' }, h('span', { class: 'nd-logo', 'aria-hidden': 'true' }, '+'),
      h('b', {}, ctx.T('app.title'))),
    h('button', { class: 'nd-lang', type: 'button', 'data-testid': 'app-lang', onclick: switchLang }, ctx.T('app.lang')));
    const list = [['map', 'app.tab_map'], ['my', 'app.tab_my']];
    if (ctx.me?.pharmacy) list.push(['pharm', 'app.tab_pharm']);
    tabs.replaceChildren(...list.map(([id, key]) => h('button', {
      class: `nd-tab${ctx.tab === id ? ' on' : ''}`, type: 'button', role: 'tab', 'aria-selected': String(ctx.tab === id),
      'data-testid': `tab-${id}`, onclick: () => go(id),
    }, ctx.T(key))));
  }

  async function switchLang() {
    const next = ctx.lang === 'uz' ? 'ru' : 'uz';
    try {
      await api.setLang(next);
    } catch (err) {
      fail(err);
      return;
    }
    ctx.lang = next;
    root.lang = next;
    onLang?.(next);
    refresh();
  }

  function go(tab) {
    ctx.tab = tab;
    root.dataset.screen = tab;
    refresh();
  }

  let painting = Promise.resolve();
  function refresh() {
    painting = painting.then(async () => {
      try {
        ctx.me = await api.me();
        ctx.now = ctx.me.now ?? Date.now();
        if (!ctx.tab) ctx.tab = ctx.me.pharmacy ? 'pharm' : 'map';
        if (ctx.tab === 'pharm' && !ctx.me.pharmacy) ctx.tab = 'map';
        root.dataset.screen = ctx.tab;
        paintHead();
        await screens[ctx.tab](ctx, body);
      } catch (err) {
        fail(err);
      }
    });
    return painting;
  }

  refresh();
  return { refresh, go, ctx, get tab() { return ctx.tab; } };
}
