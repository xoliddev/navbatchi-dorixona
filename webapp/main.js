// Mini App entry inside Telegram: validate nothing here (the server does), just pass initData along.
import { normLang } from '../shared/i18n.js';
import { httpApi } from './api.js';
import { mountApp } from './ui.js';
import { h, loadShared } from './util.js';

const tg = window.Telegram?.WebApp;
const root = document.getElementById('app');
const shared = await loadShared();

if (!tg?.initData) {
  root.replaceChildren(h('p', { class: 'nd-outside' }, shared.catalogs.uz['app.open_in_telegram']),
    h('p', { class: 'nd-outside' }, shared.catalogs.ru['app.open_in_telegram']));
} else {
  tg.ready();
  tg.expand();
  const api = httpApi(tg.initData);
  const me = await api.me().catch(() => null);
  const lang = me?.lang ?? normLang(tg.initDataUnsafe?.user?.language_code);
  mountApp(root, { api, ...shared, lang, tg });
}
