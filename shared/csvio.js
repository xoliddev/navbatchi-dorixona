// JS port of navbatchi/core/csvio.py: strict stock CSV import and formula-safe export.
import { parsePrice, parseQty } from './money.js';
import { words } from './text.js';

export const MAX_BYTES = 64 * 1024;
export const MAX_ROWS = 500;
const HEADERS = {
  med: ['med', 'id', 'dori', 'nomi', 'name', 'препарат', 'лекарство', 'название'],
  price: ['price', 'narx', 'narxi', 'цена'],
  qty: ['qty', 'soni', 'miqdor', 'miqdori', 'количество', 'кол-во', 'остаток'],
};
const DANGER = ['=', '+', '-', '@', '\t', '\r', '\n'];
const UNITS = new Set(['mg', 'mkg', 'mcg', 'g', 'ml']);
const isDigits = (w) => /^\d+$/.test(w);
const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

export class CsvError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

export function splitRows(text, sep) {
  const rows = [];
  let row = [];
  let cell = '';
  let started = false;
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i += 1; } else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"' && cell === '') {
      quoted = true;
      started = true;
    } else if (ch === sep) {
      row.push(cell);
      cell = '';
      started = true;
    } else if (ch === '\r' || ch === '\n') {
      if (ch === '\r' && text[i + 1] === '\n') i += 1;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
      started = false;
    } else {
      cell += ch;
      started = true;
    }
  }
  if (cell !== '' || row.length || started) {
    row.push(cell);
    rows.push(row);
  }
  return rows.filter((r) => r.some((c) => c.trim()));
}

export function resolveMed(meds, text) {
  const t = text.trim();
  if (meds.some((m) => m.id === t)) return t;
  const all = words(t);
  const key = all.filter((w) => !isDigits(w) && !UNITS.has(w));
  if (!key.length) return null;
  let found = meds.filter((m) => same(key, words(m.name.uz)) || same(key, words(m.name.ru)));
  const digits = all.filter(isDigits);
  if (digits.length) found = found.filter((m) => digits.every((d) => words(m.strength).includes(d)));
  return found.length === 1 ? found[0].id : null;
}

export function parseStock(raw, meds) {
  if (new TextEncoder().encode(raw).length > MAX_BYTES) throw new CsvError('too_big');
  const text = raw.replace(/^\ufeff+/, '');
  const first = text.split('\n', 1)[0];
  const sep = (first.split(';').length > first.split(',').length) ? ';' : ',';
  const rows = splitRows(text, sep);
  if (!rows.length) throw new CsvError('empty');
  const head = rows[0].map((c) => c.trim().toLowerCase());
  const cols = {};
  for (const [name, options] of Object.entries(HEADERS)) {
    const idx = head.flatMap((c, i) => (options.includes(c) ? [i] : []));
    if (idx.length !== 1) throw new CsvError('header');
    cols[name] = idx[0];
  }
  const body = rows.slice(1);
  if (body.length > MAX_ROWS) throw new CsvError('too_many_rows');
  const out = new Map();
  const errors = [];
  const maxCol = Math.max(...Object.values(cols));
  body.forEach((row, k) => {
    const line = k + 2;
    if (row.length <= maxCol) { errors.push({ line, code: 'columns' }); return; }
    const med = resolveMed(meds, row[cols.med].slice(0, 80));
    if (med === null) { errors.push({ line, code: 'med' }); return; }
    let price;
    let qty;
    try { price = parsePrice(row[cols.price].slice(0, 20)); } catch { errors.push({ line, code: 'price' }); return; }
    try { qty = parseQty(row[cols.qty].slice(0, 10)); } catch { errors.push({ line, code: 'qty' }); return; }
    if (out.has(med)) { errors.push({ line, code: 'dup' }); return; }
    out.set(med, { med, price, qty });
  });
  return { rows: [...out.values()], errors };
}

export function safeCell(value) {
  let s = String(value);
  if (DANGER.some((d) => s.startsWith(d))) s = `'${s}`;
  if (/[,;"\n\r]/.test(s)) s = `"${s.replace(/"/g, '""')}"`;
  return s;
}

export const toCsv = (rows) => rows.map((row) => `${row.map(safeCell).join(',')}\r\n`).join('');
