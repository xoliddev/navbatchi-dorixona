// JS port of navbatchi/core/hours.py: opening hours in Tashkent time (UTC+5, no DST).
export const TZ_OFFSET_MS = 5 * 3_600_000;
export const DAY_MS = 86_400_000;
const SPAN = /^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-4]):([0-5]\d)$/;
const mod = (a, m) => ((a % m) + m) % m;

export function parse(spec) {
  const s = String(spec ?? '').trim();
  if (s === '24/7') return null;
  const m = SPAN.exec(s);
  if (!m) throw new Error(`hours: ${s}`);
  const start = Number(m[1]) * 60 + Number(m[2]);
  const end = Number(m[3]) * 60 + Number(m[4]);
  if (end > 1440 || (start === end % 1440 && end !== 1440)) throw new Error(`hours: ${s}`);
  return [start, end];
}

export function localParts(nowMs) {
  const local = nowMs + TZ_OFFSET_MS;
  const day = Math.floor(local / DAY_MS);
  const minute = Math.floor(mod(local, DAY_MS) / 60_000);
  return [day, mod(day + 3, 7), minute];
}

export const hhmm = (minute) => {
  const m = mod(minute, 1440);
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
};

function openAt([start, end], off, weekday, minute) {
  if (end > start) return !off.includes(weekday) && start <= minute && minute < end;
  const yesterday = (weekday + 6) % 7;
  return (!off.includes(weekday) && minute >= start) || (!off.includes(yesterday) && minute < end);
}

export function status(spec, off, nowMs) {
  const days = [...(off ?? [])];
  const span = parse(spec);
  if (span === null) return { open: true, h24: true };
  const [, weekday, minute] = localParts(nowMs);
  const [start, end] = span;
  if (openAt(span, days, weekday, minute)) return { open: true, h24: false, until: end === 1440 ? '24:00' : hhmm(end) };
  for (let ahead = 0; ahead < 8; ahead++) {
    const wd = (weekday + ahead) % 7;
    if (days.includes(wd)) continue;
    if (ahead > 0 || minute < start) return { open: false, h24: false, opens: hhmm(start), day: ahead };
  }
  return { open: false, h24: false, opens: hhmm(start), day: 7 };
}

export const openNow = (spec, off, nowMs) => status(spec, off, nowMs).open;
