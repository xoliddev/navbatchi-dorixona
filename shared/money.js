// JS port of navbatchi/core/money.py: whole so'm only.
export const MAX_PRICE = 10_000_000;

export class PriceError extends Error {}

export function fmt(n) {
  if (!Number.isInteger(n)) throw new PriceError('not an integer');
  const sign = n < 0 ? '-' : '';
  return sign + String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

export function parsePrice(text) {
  if (typeof text === 'boolean') throw new PriceError('bool');
  let value;
  if (typeof text === 'number') {
    if (!Number.isInteger(text)) throw new PriceError('format');
    value = text;
  } else {
    let s = String(text ?? '').trim().toLowerCase();
    for (const suffix of ["so'm", 'so‘m', 'сум', 'som', 'sum']) {
      if (s.endsWith(suffix)) s = s.slice(0, -suffix.length).trim();
    }
    s = s.replace(/[ \u00a0\u202f]/g, '');
    if (!/^\d{1,9}$/.test(s)) throw new PriceError('format');
    value = Number(s);
  }
  if (value < 100 || value > MAX_PRICE) throw new PriceError('range');
  return value;
}

export function parseQty(text, maxQty = 100_000) {
  if (typeof text === 'boolean') throw new PriceError('bool');
  let value;
  if (typeof text === 'number') {
    if (!Number.isInteger(text)) throw new PriceError('qty');
    value = text;
  } else {
    const s = String(text ?? '').trim().replace(/ /g, '');
    if (!/^\d{1,6}$/.test(s)) throw new PriceError('qty');
    value = Number(s);
  }
  if (value < 0 || value > maxQty) throw new PriceError('qty');
  return value;
}
