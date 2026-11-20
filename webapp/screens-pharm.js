// Pharmacist tab: give out by pickup code, waiting reservations, stock and price editing, CSV import/export.
// The server decides which pharmacy this is; nothing here can name another one.
import { price } from '../shared/i18n.js';
import { download, h, haptic } from './util.js';

export async function renderPharm(ctx, body) {
  const data = await ctx.api.pharm();
  const held = data.reservations.filter((r) => r.status === 'held');
  const code = h('input', { class: 'nd-input code', inputmode: 'numeric', maxlength: 7, autocomplete: 'off',
    placeholder: '000 000', 'aria-label': ctx.P('app.code_input'), 'data-testid': 'pharm-code' });
  const give = h('button', { class: 'nd-btn', type: 'button', 'data-testid': 'pharm-give', onclick: async () => {
    give.disabled = true;
    try {
      const res = await ctx.api.pharmConfirm(code.value);
      haptic(ctx.tg, 'success');
      ctx.toast(ctx.T('app.given', { med: ctx.label(res.med_id), qty: res.qty }));
      code.value = '';
      ctx.refresh();
    } catch (err) {
      ctx.fail(err);
    }
    give.disabled = false;
  } }, ctx.T('app.give'));
  code.addEventListener('keydown', (e) => { if (e.key === 'Enter') give.click(); });

  const heldList = held.length ? held.map((r) => h('div', { class: 'nd-held', 'data-testid': `held-${r.code}` },
    h('span', { class: 'nd-code small' }, `${r.code.slice(0, 3)} ${r.code.slice(3)}`),
    h('span', {}, `${ctx.label(r.med_id)} × ${r.qty}`),
    h('span', { class: 'nd-muted' }, ctx.T('app.hold', { until: ctx.time(r.expires_at) }))))
    : h('p', { class: 'nd-hint' }, ctx.T('pharm.held_empty'));

  const rows = data.stock.map((s) => {
    const p = h('input', { class: 'nd-input num', inputmode: 'numeric', value: String(s.price), maxlength: 9,
      'aria-label': ctx.P('app.price'), 'data-testid': `price-${s.med_id}` });
    const q = h('input', { class: 'nd-input num', inputmode: 'numeric', value: String(s.qty), maxlength: 6,
      'aria-label': ctx.P('app.count'), 'data-testid': `qty-${s.med_id}` });
    const save = h('button', { class: 'nd-btn small', type: 'button', 'data-testid': `save-${s.med_id}`, onclick: async () => {
      try {
        await ctx.api.pharmStock({ med: s.med_id, price: p.value, qty: q.value });
        ctx.toast(ctx.T('app.saved'));
        ctx.refresh();
      } catch (err) { ctx.fail(err); }
    } }, ctx.T('app.save'));
    return h('div', { class: `nd-stock${s.qty - s.reserved <= 0 ? ' out' : ''}`, 'data-testid': `stock-${s.med_id}` },
      h('div', { class: 'nd-stock-name' }, h('b', {}, ctx.label(s.med_id)),
        h('span', { class: 'nd-muted' }, `${price(s.price)} · ${s.qty}${s.reserved ? ` (${s.reserved} bron)` : ''}`)),
      p, q, save);
  });

  const file = h('input', { type: 'file', accept: '.csv,text/csv', hidden: true, 'data-testid': 'csv-file',
    onchange: async () => {
      const f = file.files?.[0];
      if (!f) return;
      try {
        if (f.size > 64 * 1024) throw Object.assign(new Error('big'), { code: 'csv_too_big' });
        const res = await ctx.api.pharmImport(await f.text());
        ctx.toast(ctx.T('app.import_done', { n: res.updated, e: res.errors.length }));
        ctx.refresh();
      } catch (err) { ctx.fail(err); }
      file.value = '';
    } });
  const csv = h('div', { class: 'nd-row' },
    h('button', { class: 'nd-btn ghost small', type: 'button', onclick: () => file.click() }, ctx.T('app.import')),
    h('button', { class: 'nd-btn ghost small', type: 'button', 'data-testid': 'csv-export', onclick: async () => {
      try {
        download('stock.csv', await ctx.api.pharmExport());
      } catch (err) { ctx.fail(err); }
    } }, ctx.T('app.export')), file);

  body.replaceChildren(h('section', { class: 'nd-pad' },
    h('h3', { class: 'nd-ph-name', 'data-testid': 'pharm-name' }, data.pharmacy.name),
    h('div', { class: 'nd-give' }, code, give),
    h('h4', {}, `${ctx.T('app.held')} (${held.length})`), heldList,
    h('h4', {}, ctx.T('app.stock')), h('div', { class: 'nd-stock-head' }, h('span'), h('span', {}, ctx.T('app.price')),
      h('span', {}, ctx.T('app.count')), h('span')), rows, csv));
}
