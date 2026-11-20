// Map tab: search (Latin/Cyrillic/typos, on the device), the slider between "nearer" and "cheaper", the
// "navbatchi" (open now) filter, the map with nearest / cheapest / best pins, the list and the pharmacy sheet.
import { search } from '../shared/catalog.js';
import { ago, dist, hoursText, openText, price, Raw, stockLevel } from '../shared/i18n.js';
import { createMap } from './map.js';
import { debounce, h, haptic } from './util.js';

const TASHKENT = [41.3111, 69.2797];
const tf = (ctx) => (_lang, key, params) => ctx.T(key, params);
const som = (ctx, n) => `${price(n)} ${ctx.T('app.som')}`;

function mapFor(ctx) {
  if (!ctx.mapView) {
    const el = h('div', { class: 'nd-map', 'data-testid': 'map' });
    const view = createMap(el, { center: TASHKENT, attribution: ctx.T('map.attrib'), onPick: (pid) => openCard(ctx, pid) });
    ctx.mapView = { el, view };
  }
  return ctx.mapView;
}

function locationPanel(ctx) {
  const select = h('select', { 'aria-label': ctx.P('app.district'), 'data-testid': 'district',
    onchange: async () => {
      try {
        await ctx.api.setLocation({ district: select.value });
        ctx.refresh();
      } catch (err) { ctx.fail(err); }
    } }, h('option', { value: '' }, ctx.T('app.district')),
  ctx.districts.map((d) => h('option', { value: d.id, selected: ctx.me.location?.district === d.id }, d.name[ctx.lang])));
  const locate = h('button', { class: 'nd-chip', type: 'button', 'data-testid': 'locate', onclick: async () => {
    try {
      const pos = ctx.geo ? await ctx.geo() : await new Promise((ok, no) => navigator.geolocation.getCurrentPosition(
        (p) => ok({ lat: p.coords.latitude, lon: p.coords.longitude }), no, { timeout: 8000 }));
      await ctx.api.setLocation(pos);
      ctx.refresh();
    } catch (err) {
      if (err?.code && typeof err.code === 'string') ctx.fail(err);
      else ctx.toast(ctx.T('app.geo_denied'), 'bad');
    }
  } }, ctx.T('app.locate'));
  return h('div', { class: 'nd-loc' }, locate, select);
}

export async function renderMap(ctx, body) {
  const st = ctx.state.map;
  const { el, view } = mapFor(ctx);
  const input = h('input', { class: 'nd-search', type: 'search', value: st.q, maxlength: 64, autocomplete: 'off',
    placeholder: ctx.P('app.search_ph'), 'aria-label': ctx.P('app.search_ph'), 'data-testid': 'search' });
  const suggest = h('div', { class: 'nd-suggest', role: 'listbox', 'data-testid': 'suggest' });
  const showSuggest = () => {
    const hits = search(ctx.meds, input.value);
    suggest.replaceChildren(...hits.map(({ id }) => h('button', { type: 'button', role: 'option', class: 'nd-sug',
      'data-testid': `med-${id}`, onclick: () => pick(id) },
    h('b', {}, ctx.label(id)), ctx.byId[id].rx ? h('span', { class: 'nd-rx' }, 'Rx') : null)));
    suggest.hidden = !hits.length || !input.value.trim();
  };
  input.addEventListener('input', debounce(showSuggest, 120));
  input.addEventListener('focus', showSuggest);
  const slider = h('input', { type: 'range', min: 0, max: 100, step: 10, value: st.w, 'data-testid': 'weight',
    'aria-label': ctx.P('app.weight') });
  slider.addEventListener('input', debounce(() => { st.w = Number(slider.value); update(); }, 150));
  const night = h('input', { type: 'checkbox', checked: st.open, 'data-testid': 'night' });
  night.addEventListener('change', () => { st.open = night.checked; haptic(ctx.tg); update(); });
  const list = h('section', { class: 'nd-list', 'data-testid': 'results' });
  const top = h('div', { class: 'nd-top' });

  function pick(id) {
    st.med = id;
    st.q = ctx.label(id);
    input.value = st.q;
    suggest.hidden = true;
    input.blur();
    update();
  }

  async function update() {
    const loc = ctx.me.location;
    if (loc) view.setUser(loc.lat, loc.lon, ctx.P('app.you'));
    if (!st.med || !loc) {
      list.replaceChildren(h('p', { class: 'nd-hint' }, ctx.T('app.hint')), h('p', { class: 'nd-disc', html: ctx.T('disclaimer') }));
      top.replaceChildren();
      view.setOffers([], {}, null);
      if (loc) view.center(loc.lat, loc.lon);
      return;
    }
    try {
      st.res = await ctx.api.offers({ med: st.med, lat: loc.lat, lon: loc.lon, w: st.w, open: st.open });
    } catch (err) {
      ctx.fail(err);
      return;
    }
    paint(st.res, loc);
  }

  function paint(res, loc) {
    const med = ctx.byId[st.med];
    const tagOf = (pid) => ['best', 'nearest', 'cheapest'].filter((k) => res[k] === pid);
    view.setOffers(res.items.map((i) => ({ ...i, priceText: price(i.price), open: i.status.open, title: i.name })), res,
      loc);
    top.replaceChildren(
      h('div', { class: 'nd-med' }, h('b', {}, ctx.label(st.med)), h('span', {}, med.pack[ctx.lang]),
        med.rx ? h('span', { class: 'nd-rx' }, ctx.T('card.rx')) : null,
        h('button', { class: 'nd-chip', type: 'button', 'data-testid': 'alert-open', onclick: () => alertSheet(ctx, st.med) },
          ctx.T('btn.alert'))),
      h('div', { class: 'nd-legend' }, ['nearest', 'cheapest', 'best'].map((k) => h('span', { class: `nd-key is-${k}` },
        ctx.T(`offers.tag_${k}`)))));
    const cards = res.items.map((i) => {
      const tags = tagOf(i.pharmacy_id);
      return h('button', { type: 'button', class: `nd-card${tags.length ? ' tagged' : ''}`, 'data-testid': `ph-${i.pharmacy_id}`,
        onclick: () => openCard(ctx, i.pharmacy_id) },
      h('div', { class: 'nd-card-top' }, h('b', {}, i.name), h('span', { class: 'nd-price' }, som(ctx, i.price))),
      h('div', { class: 'nd-tags' }, tags.map((k) => h('span', { class: `nd-tag is-${k}`, 'data-testid': `tag-${k}` },
        ctx.T(`offers.tag_${k}`)))),
      h('div', { class: 'nd-meta' }, h('span', {}, dist(ctx.lang, i.dist)),
        h('span', { class: i.status.open ? 'open' : 'closed', html: openText(tf(ctx), ctx.lang, i.status) }),
        h('span', {}, stockLevel(tf(ctx), ctx.lang, i.available))));
    });
    const analogs = res.analogs.slice(0, 1).map((a) => h('button', { type: 'button', class: 'nd-analog',
      'data-testid': 'analog', onclick: () => pick(a.id) }, h('span', { class: 'nd-tag is-cheapest' }, ctx.T('btn.analog',
      { name: ctx.label(a.id) })), h('span', { html: ctx.T('offers.analog', { name: ctx.label(a.id), price: price(a.price) }) })));
    const empty = res.items.length ? null : h('p', { class: 'nd-hint' }, ctx.T(st.open ? 'offers.none_open' : 'offers.none'));
    list.replaceChildren(h('p', { class: 'nd-count' }, ctx.T('app.found', { n: res.items.length })), ...analogs, empty,
      ...cards, h('p', { class: 'nd-disc', html: ctx.T('disclaimer') }));
  }

  const controls = h('div', { class: 'nd-controls' },
    h('label', { class: 'nd-slider' }, h('span', {}, ctx.T('btn.near')), slider, h('span', {}, ctx.T('btn.cheap'))),
    h('label', { class: 'nd-switch' }, night, h('i', { 'aria-hidden': 'true' }), h('span', {}, ctx.T('app.night'))));
  body.replaceChildren(h('div', { class: 'nd-searchbox' }, input, suggest), ctx.me.location ? null : locationPanel(ctx),
    controls, top, el, list, ctx.me.location ? locationPanel(ctx) : null);
  suggest.hidden = true;
  requestAnimationFrame(() => view.invalidate());
  view.invalidate();
  await update();
}

export async function openCard(ctx, pid) {
  const st = ctx.state.map;
  const item = st.res?.items.find((i) => i.pharmacy_id === pid);
  if (!item) return;
  const med = ctx.byId[st.med];
  const T = tf(ctx);
  ctx.mapView?.view.focus(pid);
  ctx.sheet(item.name, (close) => {
    const rows = [
      [ctx.T('app.l_address'), item[`address_${ctx.lang}`]],
      [ctx.T('app.l_phone'), item.phone],
      [ctx.T('app.l_hours'), new Raw(`${hoursText(T, ctx.lang, item.hours)} — ${openText(T, ctx.lang, item.status)}`)],
      [ctx.T('app.l_dist'), dist(ctx.lang, item.dist)],
      [ctx.label(st.med), new Raw(`<b>${som(ctx, item.price)}</b>`)],
      [ctx.T('app.l_stock'), stockLevel(T, ctx.lang, item.available)],
      [ctx.T('app.l_updated'), ago(T, ctx.lang, item.updated_at, st.res.now)],
    ];
    const info = h('dl', { class: 'nd-info', 'data-testid': 'card' }, rows.map(([k, v]) => [h('dt', {}, k),
      h('dd', v instanceof Raw ? { html: v.html } : {}, v instanceof Raw ? null : v)]));
    if (med.rx) return [info, h('p', { class: 'nd-rx-note', html: ctx.T('offers.rx') })];
    let qty = 1;
    const max = Math.min(5, item.available);
    const out = h('output', {}, '1');
    const step = (d) => { qty = Math.max(1, Math.min(max, qty + d)); out.textContent = String(qty); };
    const go = h('button', { class: 'nd-btn', type: 'button', 'data-testid': 'reserve', onclick: async () => {
      go.disabled = true;
      try {
        const res = await ctx.api.reserve({ pharmacy: pid, med: st.med, qty });
        haptic(ctx.tg, 'success');
        close();
        showCode(ctx, res, item);
        ctx.refresh();
      } catch (err) {
        go.disabled = false;
        ctx.fail(err);
      }
    } }, ctx.T('btn.reserve'));
    return [info, h('div', { class: 'nd-qty' }, h('span', {}, ctx.T('app.qty')),
      h('button', { type: 'button', 'aria-label': '-', onclick: () => step(-1) }, '−'), out,
      h('button', { type: 'button', 'aria-label': '+', 'data-testid': 'qty-plus', onclick: () => step(1) }, '+')), go,
    h('p', { class: 'nd-disc', html: ctx.T('disclaimer') })];
  });
}

export function showCode(ctx, res, item) {
  ctx.sheet(ctx.T('app.code'), (close) => [
    h('p', { class: 'nd-code', 'data-testid': 'code' }, `${res.code.slice(0, 3)} ${res.code.slice(3)}`),
    h('p', { class: 'nd-center' }, `${ctx.label(res.med_id)} × ${res.qty} — ${som(ctx, res.qty * res.price)}`),
    h('p', { class: 'nd-center' }, item?.name ?? ''),
    h('p', { class: 'nd-center nd-muted' }, ctx.T('app.hold', { until: ctx.time(res.expires_at) })),
    h('button', { class: 'nd-btn ghost', type: 'button', onclick: close }, ctx.T('app.close'))]);
}

function alertSheet(ctx, medId) {
  ctx.sheet(ctx.T('btn.alert'), (close) => {
    let km = 3;
    const chips = [1, 3, 5, 10].map((n) => h('button', { type: 'button', class: `nd-chip${n === km ? ' on' : ''}`,
      onclick: (e) => { km = n; for (const c of chips) c.classList.toggle('on', c === e.currentTarget); } }, `${n} km`));
    const max = h('input', { class: 'nd-input', inputmode: 'numeric', maxlength: 12, placeholder: ctx.P('btn.any_price') });
    const save = h('button', { class: 'nd-btn', type: 'button', onclick: async () => {
      try {
        await ctx.api.addAlert({ med: medId, km, max_price: max.value.trim() || null });
        close();
        ctx.toast(ctx.T('app.alert_set'));
      } catch (err) { ctx.fail(err); }
    } }, ctx.T('app.save'));
    return [h('p', { html: ctx.T('alert.radius', { med: ctx.label(medId) }) }), h('div', { class: 'nd-chips' }, chips),
      h('p', { html: ctx.T('alert.price') }), max, save];
  });
}
