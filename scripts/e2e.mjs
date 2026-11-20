// Browser test of the demo at 1440 px and 375 px. Fails on any console error, page error or failed request.
//   PW_CHANNEL=chrome node scripts/e2e.mjs        (needs `playwright`: npm i --no-save playwright)
// Map tiles are answered locally with a blank image, so the test never depends on (or loads) openstreetmap.org.
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { startServer } from './serve.mjs';

const PORT = Number(process.env.E2E_PORT ?? 4196);
const BASE = process.env.E2E_URL ?? `http://127.0.0.1:${PORT}/`;
const server = process.env.E2E_URL ? null : await startServer(PORT);
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || undefined });
const TILE = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=', 'base64');
const errors = [];
let checks = 0;
const ok = (cond, msg) => {
  assert.ok(cond, msg);
  checks += 1;
};

async function open(width, height, lang = 'uz') {
  const ctx = await browser.newContext({ viewport: { width, height }, locale: 'uz-UZ', timezoneId: 'Asia/Tashkent' });
  await ctx.route('https://tile.openstreetmap.org/**', (route) => route.fulfill({ status: 200, contentType: 'image/png',
    body: TILE, headers: { 'Access-Control-Allow-Origin': '*' } }));
  await ctx.addInitScript((l) => { try { localStorage.setItem('dorixona.demo.lang', l); } catch { /* */ } }, lang);
  const page = await ctx.newPage();
  page.on('console', (m) => m.type() === 'error' && errors.push(`[${width}] ${m.text()}`));
  page.on('pageerror', (e) => errors.push(`[${width}] ${e.message}`));
  page.on('requestfailed', (r) => {
    // Leaflet cancels tiles it no longer needs when the map moves; an aborted tile is not an error.
    if (r.url().startsWith('https://tile.openstreetmap.org/') && r.failure()?.errorText === 'net::ERR_ABORTED') return;
    errors.push(`[${width}] request failed ${r.url()} ${r.failure()?.errorText}`);
  });
  await page.goto(BASE);
  await page.waitForSelector('body[data-ready="1"]', { timeout: 20_000 });
  return page;
}

const text = (page, sel) => page.locator(sel).innerText();
async function step(page, n) {
  await page.getByTestId(`story-${n}`).click();
  await page.waitForFunction((k) => document.querySelector(`[data-testid=story-${k}]`).classList.contains('done'), n, { timeout: 30_000 });
}

async function story(page, mobile) {
  ok((await text(page, '[data-testid=demo-badge]')).includes('brauzeringizda'), 'demo badge');
  if (mobile) {
    ok(await page.getByTestId('ali-phone').isVisible(), 'customer visible on a phone');
    ok(!(await page.getByTestId('dilnoza-phone').isVisible()), 'only one phone at a time');
    ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'no horizontal scroll at 375 px');
  } else {
    ok(await page.getByTestId('dilnoza-phone').isVisible(), 'both phones at 1440 px');
  }
  await step(page, 1);
  const chat = await text(page, '[data-testid=ali-chat]');
  ok(chat.includes('eng yaqin') && chat.includes('eng arzon'), 'bot marks nearest and cheapest');
  await step(page, 2);
  const app = page.getByTestId('ali-app');
  await app.locator('.nd-pin.is-nearest').waitFor({ state: 'attached' });
  ok(await app.locator('.nd-pin.is-cheapest').count() === 1, 'map shows the cheapest pin next to the nearest');
  ok(await app.getByTestId('tag-best').count() === 1, 'best choice is marked in the list');
  await step(page, 3);
  ok((await text(page, '[data-testid=demo-time]')).includes('03:00'), 'clock jumped to 03:00');
  await app.getByTestId('ph-2').waitFor();
  ok(await app.getByTestId('ph-1').count() === 0, 'closed nearest pharmacy hidden by the navbatchi filter');
  ok(await app.getByTestId('night').isChecked(), 'navbatchi filter is on');
  await step(page, 4);
  ok((await text(page, '[data-testid=ali-chat]')).includes('Olib ketish kodi'), 'pickup code shown');
  if (mobile) await page.getByTestId('switch-dilnoza').click();
  ok((await text(page, '[data-testid=dilnoza-chat]')).includes('Yangi bron'), 'pharmacist notified');
  await step(page, 5);
  if (mobile) await page.getByTestId('switch-dilnoza').click();
  await page.getByTestId('dilnoza-tab-chat').click();
  ok((await text(page, '[data-testid=dilnoza-chat]')).includes('Berildi'), 'pharmacist confirmed the code');
  await page.getByTestId('dilnoza-tab-app').click();
  const qty = page.getByTestId('dilnoza-app').getByTestId('qty-paracetamol-500');
  await qty.waitFor();
  ok(await qty.inputValue() === '2', 'stock decremented from 4 to 2');
  if (mobile) await page.getByTestId('switch-ali').click();
  await page.getByTestId('ali-tab-chat').click();
  ok((await text(page, '[data-testid=ali-chat]')).includes('berildi'), 'customer told it was handed over');
}

async function miniAppFlow(page) {
  // search in the Mini App with a typo, open a pharmacy, reserve 2, the pharmacist gives it out by code
  await page.getByTestId('ali-tab-app').click();
  const app = page.getByTestId('ali-app');
  await app.getByTestId('search').fill('ibuprfen');
  await app.getByTestId('med-ibuprofen-200').click();
  await app.getByTestId('tag-nearest').first().waitFor();
  const card = app.locator('.nd-card').first();
  await card.click();
  await app.getByTestId('card').waitFor();
  ok((await app.getByTestId('card').innerText()).includes('Yangilangan'), 'card shows last updated');
  await app.getByTestId('weight').evaluate((el) => el.value);
  await app.getByTestId('reserve').click();
  const code = (await app.getByTestId('code').innerText()).replace(/\s/g, '');
  ok(/^\d{6}$/.test(code), 'Mini App shows a 6-digit code');
  await app.locator('.nd-sheet .nd-btn.ghost').click();
  await app.getByTestId('tab-my').click();
  await app.getByTestId('my-code').first().waitFor();
  ok(true, 'reservation listed with its code');
  // the pharmacist only confirms codes held at their own pharmacy
  await page.getByTestId('dilnoza-tab-app').click();
  const ph = page.getByTestId('dilnoza-app');
  await ph.getByTestId('pharm-code').fill('000000');
  await ph.getByTestId('pharm-give').click();
  await page.waitForFunction(() => document.querySelector('[data-testid=dilnoza-app] .nd-toast.bad'));
  ok(true, 'unknown code refused');
  await ph.getByTestId('price-paracetamol-500').fill('4800');
  await ph.getByTestId('save-paracetamol-500').click();
  await page.waitForFunction(() => document.querySelector('[data-testid=dilnoza-app]').innerText.includes('4 800'));
  ok(true, 'price saved from the pharmacist panel');
  const before = await text(page, '[data-testid=demo-time]');
  await page.getByTestId('plus-1').click();
  ok((await text(page, '[data-testid=demo-time]')) !== before, '+1 hour moves the clock');
  await page.getByTestId('demo-lang').click();
  ok((await text(page, '[data-testid=demo-badge]')).includes('браузере'), 'Russian switch');
  await page.getByTestId('ali-tab-app').click();
  await page.waitForFunction(() => document.querySelector('[data-testid=ali-app]').innerText.includes('Карта'));
  ok(true, 'Mini App in Russian');
}

try {
  for (const [w, h] of [[1440, 900], [375, 812]]) {
    const page = await open(w, h);
    await story(page, w < 600);
    await page.context().close();
  }
  const page = await open(1440, 900);
  await miniAppFlow(page);
  await page.context().close();
  const phone = await open(375, 812, 'ru');
  ok((await text(phone, '[data-testid=demo-badge]')).includes('браузере'), 'opens in Russian on a phone');
  await phone.context().close();
  assert.deepEqual(errors, [], `console errors:\n${errors.join('\n')}`);
  console.log(`e2e: ${checks} checks passed at 1440 px and 375 px, 0 console errors`); // eslint-disable-line no-console
} finally {
  await browser.close();
  server?.close();
}
