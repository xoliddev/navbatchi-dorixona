// README media from the real demo: desktop + phone screenshots (JPEG), a GIF of the night-time reservation, and an
// 800x500 thumbnail. JPEG is encoded by the browser (canvas), the GIF by gifenc. Map tiles are real OSM tiles.
//   PW_CHANNEL=chrome node scripts/shots.mjs [outDir]       (needs playwright + gifenc)
import { mkdirSync, writeFileSync } from 'node:fs';
import gifenc from 'gifenc';
import { chromium } from 'playwright';
import { startServer } from './serve.mjs';

const { GIFEncoder, quantize, applyPalette } = gifenc;
const OUT = process.argv[2] ?? 'docs/media';
const PORT = Number(process.env.SHOTS_PORT ?? 4197);
mkdirSync(OUT, { recursive: true });
const server = await startServer(PORT);
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || undefined });

async function open(width, height) {
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, timezoneId: 'Asia/Tashkent' });
  const page = await ctx.newPage();
  await page.goto(`http://127.0.0.1:${PORT}/`);
  await page.waitForSelector('body[data-ready="1"]');
  return page;
}

/** PNG -> resized JPEG through the page's canvas. */
async function jpeg(page, png, name, w, h, crop = null) {
  const b64 = await page.evaluate(async ([src, W, H, c]) => {
    const img = new Image();
    img.src = `data:image/png;base64,${src}`;
    await img.decode();
    const cv = document.createElement('canvas');
    cv.width = W;
    cv.height = H;
    const g = cv.getContext('2d');
    g.imageSmoothingQuality = 'high';
    const [sx, sy, sw, sh] = c ?? [0, 0, img.width, img.height];
    g.drawImage(img, sx, sy, sw, sh, 0, 0, W, H);
    return cv.toDataURL('image/jpeg', 0.86).split(',')[1];
  }, [png.toString('base64'), w, h, crop]);
  writeFileSync(`${OUT}/${name}`, Buffer.from(b64, 'base64'));
  console.log('wrote', name); // eslint-disable-line no-console
}

const step = async (page, n) => {
  await page.getByTestId(`story-${n}`).click();
  await page.waitForFunction((k) => document.querySelector(`[data-testid=story-${k}]`).classList.contains('done'), n);
};
const tiles = (page) => page.waitForFunction(() => {
  const imgs = [...document.querySelectorAll('.leaflet-tile')].filter((i) => i.offsetParent);
  return imgs.length && imgs.every((i) => i.complete);
}, null, { timeout: 15_000 }).catch(() => {});

// desktop: the customer's map with nearest, cheapest and best; the pharmacist's panel next to it
let page = await open(1440, 900);
await step(page, 1);
await step(page, 2);
await page.getByTestId('dilnoza-tab-app').click();
await page.getByTestId('ali-tab-app').click();
await tiles(page);
await page.waitForTimeout(800);
const desk = await page.screenshot();
await jpeg(page, desk, 'demo-desktop.jpg', 1440, 900);
// thumbnail: both Mini Apps (map + pharmacist panel), cut from the same real screenshot
const a = await page.getByTestId('ali-phone').boundingBox();
const d = await page.getByTestId('dilnoza-phone').boundingBox();
const tw = Math.min(1440, d.x + d.width - a.x);
await jpeg(page, desk, 'thumb.jpg', 800, 500, [a.x, Math.min(900 - tw * 0.625, a.y + 100), tw, tw * 0.625]);
await page.context().close();

// phone: the Mini App map at night with the navbatchi filter on
page = await open(390, 844);
await step(page, 1);
await step(page, 2);
await step(page, 3);
await page.getByTestId('ali-tab-app').click();
await tiles(page);
await page.waitForTimeout(800);
await jpeg(page, await page.screenshot(), 'demo-mobile.jpg', 390, 844);
await page.context().close();

// GIF: 03:00 -> navbatchi filter -> reserve -> the pharmacist types the code -> stock goes down
page = await open(1280, 800);
const W = 840;
const H = 525;
const gif = GIFEncoder();
async function frame(delay = 160) {
  const png = await page.screenshot({ clip: { x: 160, y: 150, width: 960, height: 600 } });
  const rgba = await page.evaluate(async ([src, w, h]) => {
    const img = new Image();
    img.src = `data:image/png;base64,${src}`;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = w;
    c.height = h;
    const g = c.getContext('2d');
    g.imageSmoothingQuality = 'high';
    g.drawImage(img, 0, 0, w, h);
    return Array.from(g.getImageData(0, 0, w, h).data);
  }, [png.toString('base64'), W, H]);
  const data = Uint8Array.from(rgba);
  const palette = quantize(data, 128);
  gif.writeFrame(applyPalette(data, palette), W, H, { palette, delay });
}
await page.evaluate(() => window.scrollTo(0, 120));
await step(page, 1);
await step(page, 2);
await tiles(page);
await frame(1600);
for (const n of [3, 4, 5]) {
  await page.getByTestId(`story-${n}`).click();
  for (let k = 0; k < 14; k++) {
    await page.waitForTimeout(450);
    await frame(260);
    const finished = await page.evaluate((s) => document.querySelector(`[data-testid=story-${s}]`).classList.contains('done'), n);
    if (finished && k > 3) break;
  }
  if (n === 3) await tiles(page);
  await frame(1300);
}
await page.waitForTimeout(700);
await frame(2600);
gif.finish();
writeFileSync(`${OUT}/reserve-flow.gif`, gif.bytes());
console.log('wrote reserve-flow.gif'); // eslint-disable-line no-console
await browser.close();
server.close();
