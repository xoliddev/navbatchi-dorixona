// JS port of navbatchi/core/reserve.py: reservation (bron) rules.
export const HOLD_MINUTES = 120;
export const MAX_QTY = 5;
export const MAX_ACTIVE_PER_USER = 3;
const MOVES = { 'held:confirm': 'picked', 'held:cancel': 'cancelled', 'held:expire': 'expired' };

export class ReserveError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

export function check(rx, qty, available, active = 0) {
  if (rx) throw new ReserveError('rx');
  if (!Number.isInteger(qty) || qty < 1 || qty > MAX_QTY) throw new ReserveError('qty');
  if (active >= MAX_ACTIVE_PER_USER) throw new ReserveError('too_many');
  if (available < qty) throw new ReserveError('stock');
}

export const makeCode = (n) => String(((n % 1_000_000) + 1_000_000) % 1_000_000).padStart(6, '0');

export function cleanCode(text) {
  const s = String(text ?? '').replace(/[\s-]/g, '').slice(0, 12);
  return /^\d{6}$/.test(s) ? s : null;
}

export const expiresAt = (createdMs) => createdMs + HOLD_MINUTES * 60_000;

export function minutesLeft(expiresMs, nowMs) {
  const left = expiresMs - nowMs;
  return left <= 0 ? 0 : Math.ceil(left / 60_000);
}

export function move(status, action) {
  const next = MOVES[`${status}:${action}`];
  if (!next) throw new ReserveError('state');
  return next;
}
