#!/usr/bin/env node
/**
 * Deterministic headless screenshot + runtime inspection for the viewer.
 * Usage: node tools/shot.mjs <url> <outfile> [timeoutSec]
 * Requires Chrome at /Applications/Google Chrome.app/Contents/MacOS/Google Chrome.
 */
import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const url = process.argv[2] || 'http://127.0.0.1:8771/web/index.html?backend=webgl&auto=0&level=L1';
const out = process.argv[3] || 'reports/shot.png';
const timeoutSec = Number(process.argv[4] || 300);
const evalAfter = process.argv[5] || '';
const vw = Number(process.env.SHOT_W || 1440);
const vh = Number(process.env.SHOT_H || 1000);
const port = 9300 + Math.floor(Math.random() * 300);
const profile = path.resolve(`.chrome-cdp-${Date.now()}`);
const args = [
  '--headless=new', '--no-sandbox', '--remote-debugging-port=' + port,
  '--user-data-dir=' + profile, '--no-first-run', '--no-default-browser-check',
  '--force-device-scale-factor=1', '--enable-unsafe-swiftshader',
  '--use-gl=angle', '--use-angle=swiftshader', '--hide-scrollbars',
  '--window-size=1440,1000', 'about:blank',
];
const chrome = spawn(CHROME, args, { stdio: ['ignore', 'ignore', 'ignore'] });
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const getJson = (p) => new Promise((resolve, reject) => {
  http.get({ host: '127.0.0.1', port, path: p }, (res) => {
    let data = '';
    res.on('data', d => data += d);
    res.on('end', () => { try { resolve(JSON.parse(data)); } catch (e) { reject(e); } });
  }).on('error', reject);
});
async function waitJson(p, deadline) {
  while (Date.now() < deadline) {
    try { return await getJson(p); } catch {}
    await sleep(250);
  }
  throw new Error('DevTools endpoint timeout');
}
let ws;
let nextId = 1;
const pending = new Map();
function cdp(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
}
async function evaluate(expression, awaitPromise = true) {
  const r = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));
  return r.result?.value;
}
try {
  const deadline = Date.now() + timeoutSec * 1000;
  const list = await waitJson('/json/list', deadline);
  const page = list.find(x => x.type === 'page');
  if (!page) throw new Error('No page target');
  ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) {
      const { resolve, reject } = pending.get(m.id);
      pending.delete(m.id);
      if (m.error) reject(new Error(JSON.stringify(m.error))); else resolve(m.result);
    }
  };
  await cdp('Runtime.enable');
  await cdp('Page.enable');
  await cdp('Emulation.setDeviceMetricsOverride', { width: vw, height: vh, deviceScaleFactor: 1, mobile: vw < 600 });
  await cdp('Page.navigate', { url });
  let ready = false;
  let lastStage = '';
  while (Date.now() < deadline) {
    await sleep(1500);
    try {
      const stage = await evaluate('window.__LOAD_STAGE__ || ""');
      if (stage !== lastStage) { console.log('stage:', stage); lastStage = stage; }
      ready = await evaluate('window.__TOWER_READY__ === true');
      const err = await evaluate('window.__TOWER_ERROR__ || window.__BOOT_ERR__ || null');
      if (err) throw new Error('Page error: ' + err);
      if (ready) break;
    } catch (e) {
      if (/Page error/.test(e.message)) throw e;
    }
  }
  if (!ready) throw new Error('Timed out waiting for __TOWER_READY__; stage=' + lastStage);
  if (evalAfter) {
    await sleep(2600);
    console.log('EVAL', evalAfter);
    const r = await evaluate(evalAfter);
    console.log('EVAL RESULT', JSON.stringify(r));
    await sleep(7000);
  }
  await sleep(5200);
  const info = await evaluate(`(() => {
    const r = window.__RENDER__;
    return r ? { backend:r.backend, level:r.level, config:r.config, fps:r.fps, postOK:r.postOK, state:r.state } : null;
  })()`);
  console.log('RUNTIME', JSON.stringify(info));
  const shot = await cdp('Page.captureScreenshot', { format: 'png', fromSurface: true });
  fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
  fs.writeFileSync(out, Buffer.from(shot.data, 'base64'));
  console.log('WROTE', out, fs.statSync(out).size);
} catch (e) {
  console.error('SHOT ERROR', e.stack || e);
  process.exitCode = 1;
} finally {
  try { if (ws) ws.close(); } catch {}
  try { chrome.kill('SIGKILL'); } catch {}
  await sleep(300);
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch {}
  setTimeout(() => process.exit(process.exitCode || 0), 100);
}
