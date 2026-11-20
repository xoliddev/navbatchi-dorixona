// Demo page: the customer's and the pharmacist's phones, the guided story, the Tashkent clock and the language.
import { clock, makeT } from '../shared/i18n.js';
import { mountApp } from '../webapp/ui.js';
import { h, loadShared, plain } from '../webapp/util.js';
import { apiFor } from './api.js';
import { BotSim } from './bot.js';
import { makeViews } from './bot-views.js';
import { createPhone } from './phone.js';
import { ALI, createDemo, DILNOZA, HERE } from './seed.js';
import { runStep, STEPS } from './story.js';

const { pharmacies, ...shared } = await loadShared(new URL('../shared/', import.meta.url), true);
const t = makeT(shared.catalogs);
const views = makeViews(t);
const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};
let lang = store.get('dorixona.demo.lang') === 'ru' ? 'ru' : 'uz';
const texts = { P: (key, params) => plain(t(lang, key, params)) };
const backend = createDemo({ ...shared, pharmacies, lang });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const UIDS = [ALI, DILNOZA];
const people = {
  [ALI]: { who: 'ali', label: 'demo.customer', role: 'demo.role_customer' },
  [DILNOZA]: { who: 'dilnoza', label: 'demo.pharmacist', role: 'demo.role_pharm' },
};
const phones = {};
const bots = {};
const apps = {};
let shown = ALI;

function mount(uid) {
  apps[uid] = mountApp(phones[uid].appRoot, { api: apiFor(backend, uid), ...shared, lang, tg: { colorScheme: 'light' },
    geo: async () => ({ lat: HERE[0], lon: HERE[1] }), onLang: (l) => setLang(l) });
}

function refreshApp(uid, force = false) {
  const root = phones[uid].appRoot;
  if (!force && (root.querySelector('.nd-backdrop') || root.contains(document.activeElement))) return null;
  return apps[uid]?.refresh();
}

for (const uid of UIDS) {
  bots[uid] = new BotSim(backend, uid, t, views, {
    onChange: () => phones[uid]?.renderChat(),
    onAlert: (text) => phones[uid].alert(text),
  });
  phones[uid] = createPhone({
    who: people[uid].who, label: '', role: people[uid].role, bot: bots[uid], texts: { P: (k) => texts.P(k) },
    now: () => backend.nowMs(),
    onOpenApp: () => focus(uid, 'app'),
    onShowApp: () => refreshApp(uid, true),
    onLocation: uid === ALI ? () => bots[ALI].shareLocation(...HERE) : null,
  });
}

function deliver(to, ev) {
  if (!bots[to]) return;
  const msg = bots[to].deliver(ev);
  if (msg) phones[to].ping(msg.html);
}

backend.on((ev) => {
  if (ev.type === 'clock') {
    timeEl.textContent = texts.P('demo.time', { time: clock(ev.now) });
    for (const uid of UIDS) phones[uid].tick();
  }
  if (ev.type === 'new_res') for (const to of ev.to) deliver(to, ev);
  if (['picked', 'expired', 'alert'].includes(ev.type)) deliver(ev.to, ev);
  for (const uid of UIDS) if (ev.type !== 'changed' || ev.by !== uid) refreshApp(uid);
});

function focus(uid, pane) {
  phones[uid].show(pane);
  if (pane === 'app') refreshApp(uid, true);
  if (window.matchMedia('(max-width: 600px)').matches) pick(uid);
}

async function openMap(uid, { med, open, w }) {
  const app = apps[uid];
  Object.assign(app.ctx.state.map, { med, open, w, q: app.ctx.label(med) });
  app.ctx.tab = 'map';
  await app.refresh();
}

// ── page ──
const timeEl = h('span', { class: 'demo-date', 'data-testid': 'demo-time' });
const badgeText = h('span');
const langBtn = h('button', { class: 'demo-btn', type: 'button', 'data-testid': 'demo-lang', onclick: () => setLang(lang === 'uz' ? 'ru' : 'uz') });
const plus1 = h('button', { class: 'demo-btn solid', type: 'button', 'data-testid': 'plus-1', onclick: () => backend.skipHours(1) });
const plus6 = h('button', { class: 'demo-btn', type: 'button', 'data-testid': 'plus-6', onclick: () => backend.skipHours(6) });
const resetBtn = h('button', { class: 'demo-btn', type: 'button', onclick: () => window.location.reload() });
const bar = h('header', { class: 'demo-bar' },
  h('a', { class: 'demo-logo', href: './' }, h('span', { class: 'demo-mark' }, '+'), 'Navbatchi Dorixona'),
  h('span', { class: 'demo-badge', 'data-testid': 'demo-badge' }, h('span', { class: 'dot' }), badgeText),
  h('span', { class: 'demo-time' }, timeEl, plus1, plus6),
  h('div', { class: 'demo-tools' }, langBtn, resetBtn,
    h('a', { class: 'demo-btn gh', href: 'https://github.com/xoliddev/navbatchi-dorixona', target: '_blank', rel: 'noopener' }, 'GitHub')));
const title = h('h1');
const lead = h('p');
const foot = h('p', { class: 'demo-foot' });
let done = 0;
let running = false;
const storyBtns = STEPS.map((key, i) => h('button', { class: 'story-btn', type: 'button', 'data-testid': `story-${i + 1}`,
  onclick: async () => {
    if (running || i !== done) return;
    running = true;
    paintStory();
    try {
      await runStep(i + 1, { backend, bots, wait, focus, openMap });
      done = i + 1;
    } catch (err) {
      console.error(err); // eslint-disable-line no-console
      phones[shown].alert(texts.P('err.generic'));
    }
    running = false;
    paintStory();
  } }, h('b', {}, String(i + 1)), h('span')));
function paintStory() {
  storyBtns.forEach((b, i) => {
    b.lastChild.textContent = texts.P(`demo.${STEPS[i]}`);
    b.classList.toggle('done', i < done);
    b.classList.toggle('next', i === done && !running);
    b.disabled = running || i !== done;
  });
}
const whoBtns = UIDS.map((uid) => h('button', { type: 'button', 'data-testid': `switch-${people[uid].who}`, onclick: () => pick(uid) }));
function pick(uid) {
  shown = uid;
  whoBtns.forEach((b, i) => b.classList.toggle('on', UIDS[i] === uid));
  for (const id of UIDS) phones[id].side.classList.toggle('show', id === uid);
  if (phones[uid].pane === 'app') refreshApp(uid, true);
}

function paintTexts() {
  document.documentElement.lang = lang;
  badgeText.textContent = texts.P('demo.badge');
  timeEl.textContent = texts.P('demo.time', { time: clock(backend.nowMs()) });
  langBtn.textContent = lang === 'uz' ? 'RU' : 'UZ';
  plus1.textContent = texts.P('demo.plus1');
  plus6.textContent = texts.P('demo.plus6');
  resetBtn.textContent = texts.P('demo.reset');
  title.textContent = texts.P('demo.title');
  lead.textContent = texts.P('demo.lead');
  foot.textContent = texts.P('demo.no_bot');
  whoBtns.forEach((b, i) => { b.textContent = texts.P(people[UIDS[i]].label); });
  paintStory();
  for (const uid of UIDS) {
    phones[uid].renderLabels();
    phones[uid].side.querySelector('.side-label b').textContent = texts.P(people[uid].label);
  }
}

function setLang(next) {
  if (next === lang) return;
  lang = next;
  store.set('dorixona.demo.lang', lang);
  for (const uid of UIDS) {
    backend.setLang(uid, lang);
    apps[uid].ctx.lang = lang;
    refreshApp(uid, true);
  }
  paintTexts();
}

document.body.append(bar, h('section', { class: 'demo-intro' }, title, lead), h('nav', { class: 'story', 'aria-label': 'story' }, storyBtns),
  h('div', { class: 'who-switch', role: 'tablist' }, whoBtns),
  h('main', { class: 'demo-stage' }, phones[ALI].side, phones[DILNOZA].side), foot);
for (const uid of UIDS) {
  mount(uid);
  bots[uid].start();
}
pick(ALI);
paintTexts();
document.body.dataset.ready = '1';
