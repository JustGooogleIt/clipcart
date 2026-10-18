const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const BASE = process.env.CLIPCART_BASE || 'http://127.0.0.1:8012';
const S = process.env.VERIFY_DIR;
const STATE = S + '/browser-state.json';
const log = [];
function step(name, ok, detail) { log.push({ step: name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail !== undefined ? ' :: ' + JSON.stringify(detail) : ''}`); }
async function open(useState) {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, ...(useState ? { storageState: STATE } : {}) });
  const p = await ctx.newPage();
  p.on('pageerror', e => step('no page errors', false, e.message));
  return { b, ctx, p };
}
async function cards(p) {
  return p.$$eval('.card-title', ts => ts.map(t => {
    let el = t; while (el && !el.querySelector('.btn-save')) el = el.parentElement;
    const reason = el && el.querySelector('.card-personal');
    const save = el && el.querySelector('.btn-save');
    return { title: t.innerText.trim(), personalization: reason ? reason.innerText.replace(/\s+/g, ' ').trim() : null, save: save ? save.innerText.trim() : null };
  }));
}
async function waitResults(p) {
  await p.waitForFunction(() => document.querySelectorAll('.card-title').length > 0 || /No qualifying results/.test(document.body.innerText), null, { timeout: 30000 });
  await p.waitForTimeout(500);
}
async function search(p) {
  const before = await p.$$eval('.card-title', x => x.length);
  await p.getByRole('button', { name: /^Find this/ }).click();
  await p.waitForTimeout(1500);
  await waitResults(p);
  return cards(p);
}
async function api(p, path) { const r = await p.request.get(BASE + path); return r.json(); }
async function openPanel(p) {
  if (!(await p.locator('#style-title').isVisible().catch(() => false))) await p.getByRole('button', { name: /Your style/ }).first().click();
  await p.locator('#style-title').waitFor();
  await p.waitForTimeout(600);
}
async function closePanel(p) { await p.getByRole('button', { name: 'Close Your style' }).click(); await p.waitForTimeout(300); }
async function panelText(p) { return (await p.locator('.style-panel').innerText()).replace(/\s+/g, ' '); }
function save(name) { fs.writeFileSync(`${S}/log-${name}.json`, JSON.stringify(log, null, 2)); return log.every(x => x.ok); }
module.exports = { open, cards, search, waitResults, api, openPanel, closePanel, panelText, step, save, STATE, S, BASE };
