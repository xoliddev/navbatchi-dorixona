// "My reservations" tab: pickup codes with the time left, cancel, and active price alerts.
import { minutesLeft } from '../shared/reserve.js';
import { price } from '../shared/i18n.js';
import { h } from './util.js';

export async function renderMy(ctx, body) {
  const [{ items, now }, alerts] = await Promise.all([ctx.api.reservations(), ctx.api.alerts()]);
  const cards = items.map((r) => {
    const held = r.status === 'held';
    const cancel = held ? h('button', { class: 'nd-btn ghost small', type: 'button', 'data-testid': `cancel-${r.id}`,
      onclick: async () => {
        try {
          await ctx.api.cancel(r.id);
          ctx.toast(ctx.T('res.cancelled'));
          ctx.refresh();
        } catch (err) { ctx.fail(err); }
      } }, ctx.T('app.cancel')) : null;
    return h('article', { class: `nd-res ${r.status}`, 'data-testid': `res-${r.id}` },
      h('div', { class: 'nd-card-top' }, h('b', {}, `${ctx.label(r.med_id)} × ${r.qty}`),
        h('span', { class: `nd-status ${r.status}` }, ctx.T(`status.${r.status}`))),
      h('div', { class: 'nd-meta' }, h('span', {}, r.pharmacy.name), h('span', {}, `${price(r.qty * r.price)} ${ctx.T('app.som')}`)),
      held ? h('div', { class: 'nd-res-code' }, h('span', { class: 'nd-code small', 'data-testid': 'my-code' },
        `${r.code.slice(0, 3)} ${r.code.slice(3)}`), h('span', { class: 'nd-muted' },
        `${ctx.T('app.hold', { until: ctx.time(r.expires_at) })} · ${ctx.T('app.left', { n: minutesLeft(r.expires_at, now) })}`))
        : null,
      held ? h('div', { class: 'nd-muted' }, `${r.pharmacy[`address_${ctx.lang}`]} · ${r.pharmacy.phone}`) : null,
      cancel);
  });
  const alertRows = alerts.items.map((a) => h('div', { class: 'nd-alert-row' },
    h('span', {}, `${ctx.label(a.med_id)} · ${a.radius_m / 1000} km${a.max_price ? ` · ≤ ${price(a.max_price)}` : ''}`),
    h('button', { class: 'nd-x', type: 'button', 'aria-label': ctx.P('btn.delete'), onclick: async () => {
      try {
        await ctx.api.delAlert(a.id);
        ctx.refresh();
      } catch (err) { ctx.fail(err); }
    } }, '×')));
  body.replaceChildren(h('section', { class: 'nd-pad' },
    items.length ? cards : h('p', { class: 'nd-hint' }, ctx.T('app.my_empty')),
    alertRows.length ? [h('h4', {}, ctx.T('app.alerts')), alertRows] : null,
    h('p', { class: 'nd-disc', html: ctx.T('disclaimer') })));
}
