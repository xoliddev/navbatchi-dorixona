// The guided scenario. Each step presses the same buttons a person would, through the simulated bot and the
// Mini App. Used by the demo page (with pauses, so you can watch) and by js-tests/demo.test.mjs (without pauses).
import { ALI, DILNOZA, PHARMACY } from './seed.js';

const MED = 'paracetamol-500';

/** Press the newest button whose callback data matches `re`. */
export function tap(bot, re) {
  for (let i = bot.messages.length - 1; i >= 0; i--) {
    const msg = bot.messages[i];
    for (const row of msg.kb) {
      for (const b of row) {
        if (b.data && re.test(b.data)) {
          bot.press(msg.id, b.data);
          return b.data;
        }
      }
    }
  }
  throw new Error(`no button ${re} in ${bot.uid}'s chat`);
}

export const STEPS = ['step1', 'step2', 'step3', 'step4', 'step5'];

export async function runStep(n, { backend, bots, wait = async () => {}, focus = () => {}, openMap = async () => {} }) {
  const ali = bots[ALI];
  const dilnoza = bots[DILNOZA];
  const pause = (ms = 700) => wait(ms);
  if (n === 1) {
    focus(ALI, 'chat');
    await pause(300);
    ali.type(ali.lang === 'ru' ? 'парацетамол' : 'paratsetamol');
    await pause();
    tap(ali, new RegExp(`^m:${MED}$`));
  } else if (n === 2) {
    focus(ALI, 'app');
    await openMap(ALI, { med: MED, open: false, w: 50 });
  } else if (n === 3) {
    backend.setLocal(3, 0);
    focus(ALI, 'chat');
    await pause(400);
    tap(ali, new RegExp(`^o:${MED}:50:1$`));
    await pause(900);
    focus(ALI, 'app');
    await openMap(ALI, { med: MED, open: true, w: 50 });
  } else if (n === 4) {
    focus(ALI, 'chat');
    await pause(300);
    tap(ali, new RegExp(`^p:${MED}:${PHARMACY}:\\d+:\\d$`));
    await pause();
    tap(ali, new RegExp(`^q:${MED}:${PHARMACY}:0$`));
    await pause();
    tap(ali, new RegExp(`^q:${MED}:${PHARMACY}:2$`));
    await pause(600);
    focus(DILNOZA, 'chat');
  } else if (n === 5) {
    const res = backend.reservations.filter((r) => r.user_id === ALI && r.status === 'held').at(-1);
    focus(DILNOZA, 'chat');
    dilnoza.start();
    await pause(400);
    tap(dilnoza, /^n:pharm$/);
    await pause();
    tap(dilnoza, /^n:code$/);
    await pause();
    dilnoza.type(`${res.code.slice(0, 3)} ${res.code.slice(3)}`);
    await pause(900);
    focus(DILNOZA, 'app');
    return res.code;
  }
  return null;
}
