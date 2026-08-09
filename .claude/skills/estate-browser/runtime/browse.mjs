#!/usr/bin/env node
/* estate-browser — a zero-dependency browser runtime for agent sessions.
 *
 * Inspired by ego-lite's ego-browser (MIT, citrolabs) — the heredoc-driven
 * helper runtime and snapshot-ref interaction model — reworked from scratch
 * for headless Linux: raw CDP over Node's native WebSocket against the
 * pre-installed Chromium. No app, no npm dependencies.
 *
 * Usage:  node browse.mjs <<'EOF'
 *           await open('https://example.com')
 *           log(await snapshotText())
 *         EOF
 *
 * The browser runs as a persistent daemon between heredoc rounds (profile +
 * state under ~/.estate-browser), so logins and tabs survive across rounds.
 * Call shutdown() in your final round to close it.
 */

import { execSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';

const BASE = process.env.ESTATE_BROWSER_DIR || path.join(os.homedir(), '.estate-browser');
const PROFILE = path.join(BASE, 'profile');
const STATE = path.join(BASE, 'state.json');
const PORT = Number(process.env.ESTATE_BROWSER_PORT || 9777);
const SHOTS = process.env.ESTATE_SHOT_DIR || BASE;
fs.mkdirSync(PROFILE, { recursive: true });

// ---------- chromium discovery ----------
function findChromium() {
  if (process.env.ESTATE_CHROMIUM) return process.env.ESTATE_CHROMIUM;
  const roots = [process.env.PLAYWRIGHT_BROWSERS_PATH || '/opt/pw-browsers'];
  for (const root of roots) {
    try {
      for (const entry of fs.readdirSync(root)) {
        if (!entry.startsWith('chromium')) continue;
        for (const candidate of [
          path.join(root, entry, 'chrome-linux', 'chrome'),
          path.join(root, entry, 'chrome-linux', 'headless_shell'),
          path.join(root, entry),
        ]) {
          try {
            if (fs.statSync(candidate).isFile() && (fs.statSync(candidate).mode & 0o111)) return candidate;
          } catch {}
        }
      }
    } catch {}
  }
  try { return execSync('which chromium || which chromium-browser || which google-chrome', { shell: '/bin/bash' }).toString().trim(); } catch {}
  throw new Error('no chromium found — set ESTATE_CHROMIUM to a browser binary');
}

// ---------- daemon lifecycle ----------
function httpJson(pathname) {
  return new Promise((resolve, reject) => {
    const request = http.get({ host: '127.0.0.1', port: PORT, path: pathname, timeout: 2000 }, (response) => {
      let body = '';
      response.on('data', (chunk) => (body += chunk));
      response.on('end', () => { try { resolve(JSON.parse(body)); } catch (error) { reject(error); } });
    });
    request.on('error', reject);
    request.on('timeout', () => request.destroy(new Error('timeout')));
  });
}

async function browserAlive() {
  try { return (await httpJson('/json/version')).webSocketDebuggerUrl; } catch { return null; }
}

async function ensureBrowser() {
  let ws = await browserAlive();
  if (ws) return ws;
  const bin = findChromium();
  const args = [
    '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${PROFILE}`,
    '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--hide-scrollbars',
    '--window-size=1280,900',
  ];
  // honor the environment's outbound proxy (CA for it is already in the NSS store)
  const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
  if (proxy) {
    // keep the bypass list minimal: chromium silently drops the whole proxy
    // config when it can't parse an entry (e.g. bare '::' from NO_PROXY)
    args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=localhost;127.0.0.1');
  }
  args.push('about:blank');
  const child = spawn(bin, args, { detached: true, stdio: 'ignore' });
  child.unref();
  fs.writeFileSync(STATE, JSON.stringify({ pid: child.pid, port: PORT, started: Date.now() }));
  for (let i = 0; i < 50; i++) {
    await new Promise((r) => setTimeout(r, 250));
    ws = await browserAlive();
    if (ws) return ws;
  }
  throw new Error('chromium did not come up on the debug port');
}

// ---------- CDP client ----------
class Cdp {
  constructor(url) { this.url = url; this.id = 0; this.pending = new Map(); this.handlers = []; }
  connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);
      this.ws.onopen = () => resolve(this);
      this.ws.onerror = (event) => reject(new Error(`cdp connect failed: ${event.message || this.url}`));
      this.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.id && this.pending.has(msg.id)) {
          const { resolve: res, reject: rej } = this.pending.get(msg.id);
          this.pending.delete(msg.id);
          msg.error ? rej(new Error(`${msg.error.message}${msg.error.data ? ': ' + msg.error.data : ''}`)) : res(msg.result);
        } else if (msg.method) {
          for (const h of this.handlers) h(msg);
        }
      };
    });
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    this.ws.send(JSON.stringify(payload));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }
  on(handler) { this.handlers.push(handler); }
  close() { try { this.ws.close(); } catch {} }
}

// ---------- session state ----------
let cdp, session = null, targetId = null;

async function attach(target) {
  const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: target, flatten: true });
  session = sessionId; targetId = target;
  await cdp.send('Page.enable', {}, session);
  await cdp.send('Runtime.enable', {}, session);
  return sessionId;
}

async function pageTargets() {
  const { targetInfos } = await cdp.send('Target.getTargets');
  return targetInfos.filter((t) => t.type === 'page' && !t.url.startsWith('devtools'));
}

function requireSession() { if (!session) throw new Error('no tab attached — call open(url) first'); }

// ---------- helpers exposed to the script ----------
const helpers = {
  log: (...parts) => console.log(...parts.map((p) => (typeof p === 'string' ? p : JSON.stringify(p, null, 2)))),

  async open(url, { newTab = false, timeout = 25000 } = {}) {
    const existing = await pageTargets();
    if (!newTab && existing.length && !session) await attach(existing[0].targetId);
    if (!session || newTab) {
      const { targetId: created } = await cdp.send('Target.createTarget', { url: 'about:blank' });
      await attach(created);
    }
    const loaded = new Promise((resolve) => {
      const done = setTimeout(resolve, timeout);
      cdp.on((msg) => { if (msg.method === 'Page.loadEventFired' && msg.sessionId === session) { clearTimeout(done); resolve(); } });
    });
    await cdp.send('Page.navigate', { url }, session);
    await loaded;
    await new Promise((r) => setTimeout(r, 400)); // settle
    return helpers.pageInfo();
  },

  async pageInfo() {
    requireSession();
    const { result } = await cdp.send('Runtime.evaluate', {
      expression: 'JSON.stringify({url: location.href, title: document.title, h: document.body ? document.body.scrollHeight : 0, y: scrollY})',
      returnByValue: true,
    }, session);
    return JSON.parse(result.value);
  },

  async tabs() {
    return (await pageTargets()).map((t) => ({ id: t.targetId, url: t.url, title: t.title, current: t.targetId === targetId }));
  },

  async switchTab(id) { await attach(id); return helpers.pageInfo(); },

  async closeTab(id) { await cdp.send('Target.closeTarget', { targetId: id || targetId }); if (!id || id === targetId) { session = null; targetId = null; } },

  async js(expression) {
    requireSession();
    const { result, exceptionDetails } = await cdp.send('Runtime.evaluate', {
      expression, returnByValue: true, awaitPromise: true,
    }, session);
    if (exceptionDetails) throw new Error(exceptionDetails.exception?.description || 'page script threw');
    return result.value;
  },

  // Text-first observation: page text plus numbered refs for everything
  // interactive. Click/fill accept '@N' from this listing.
  async snapshotText({ maxChars = 6000 } = {}) {
    requireSession();
    return helpers.js(`(() => {
      const interactive = Array.from(document.querySelectorAll(
        'a[href], button, input, textarea, select, [role="button"], [role="link"], [onclick]'));
      window.__estRefs = interactive;
      const refLines = interactive.slice(0, 120).map((el, i) => {
        const tag = el.tagName.toLowerCase();
        const label = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || el.getAttribute('title') || el.href || '')
          .trim().replace(/\\s+/g, ' ').slice(0, 80);
        const extra = tag === 'input' ? ' type=' + (el.type || 'text') : '';
        return '[@' + i + '] <' + tag + extra + '> ' + label;
      });
      const text = (document.body?.innerText || '').replace(/\\n{3,}/g, '\\n\\n').slice(0, ${maxChars});
      return '== ' + document.title + ' · ' + location.href + ' ==\\n\\n-- interactive --\\n'
        + refLines.join('\\n') + '\\n\\n-- page text --\\n' + text;
    })()`);
  },

  async click(target) {
    requireSession();
    if (Array.isArray(target)) {
      const [x, y] = target;
      for (const type of ['mousePressed', 'mouseReleased'])
        await cdp.send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1 }, session);
      return;
    }
    const expr = String(target).startsWith('@')
      ? `window.__estRefs[${Number(String(target).slice(1))}]`
      : `document.querySelector(${JSON.stringify(target)})`;
    await helpers.js(`(() => { const el = ${expr}; if (!el) throw new Error('no element: ${String(target).replace(/'/g, '')}');
      el.scrollIntoView({block: 'center'}); el.click(); return true; })()`);
    await new Promise((r) => setTimeout(r, 300));
  },

  async fill(target, text) {
    requireSession();
    const expr = String(target).startsWith('@')
      ? `window.__estRefs[${Number(String(target).slice(1))}]`
      : `document.querySelector(${JSON.stringify(target)})`;
    await helpers.js(`(() => { const el = ${expr}; if (!el) throw new Error('no element');
      el.focus();
      const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
      setter ? setter.call(el, ${JSON.stringify(text)}) : (el.value = ${JSON.stringify(text)});
      el.dispatchEvent(new Event('input', {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true})); return true; })()`);
  },

  async press(key = 'Enter') {
    requireSession();
    const codes = { Enter: 13, Tab: 9, Escape: 27, ArrowDown: 40, ArrowUp: 38 };
    const vk = codes[key] || key.charCodeAt(0);
    for (const type of ['keyDown', 'keyUp'])
      await cdp.send('Input.dispatchKeyEvent', {
        type, key, code: key, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk,
        ...(type === 'keyDown' && key === 'Enter' ? { text: '\r' } : {}),
      }, session);
    await new Promise((r) => setTimeout(r, 300));
  },

  async scroll(dy = 800) { await helpers.js(`window.scrollBy(0, ${Number(dy)})`); await new Promise((r) => setTimeout(r, 200)); },

  async waitFor(selectorOrMs, { timeout = 15000 } = {}) {
    if (typeof selectorOrMs === 'number') return new Promise((r) => setTimeout(r, selectorOrMs));
    const started = Date.now();
    while (Date.now() - started < timeout) {
      if (await helpers.js(`!!document.querySelector(${JSON.stringify(selectorOrMs)})`)) return true;
      await new Promise((r) => setTimeout(r, 300));
    }
    throw new Error(`waitFor timed out: ${selectorOrMs}`);
  },

  async shot(name = `shot-${Date.now()}.png`) {
    requireSession();
    const { data } = await cdp.send('Page.captureScreenshot', { format: 'png' }, session);
    const file = path.isAbsolute(name) ? name : path.join(SHOTS, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, Buffer.from(data, 'base64'));
    console.log(`screenshot: ${file}`);
    return file;
  },

  // serverFetch — an HTTP GET/POST from Node, honoring the environment proxy.
  // Works even where full browser TLS is blocked; returns {status, body}.
  // No JS rendering — for static HTML, JSON APIs, and health checks.
  async fetch(url, { method = 'GET', headers = {}, body = null, maxBytes = 200000 } = {}) {
    const args = ['-sS', '-L', '--max-time', '40', '-X', method,
      '-w', '\\n__ESTATE_STATUS__%{http_code}'];
    for (const [k, v] of Object.entries(headers)) args.push('-H', `${k}: ${v}`);
    if (body != null) args.push('--data-binary', typeof body === 'string' ? body : JSON.stringify(body));
    args.push(url);
    const out = execSync(`curl ${args.map((a) => `'${String(a).replace(/'/g, "'\\''")}'`).join(' ')}`,
      { maxBuffer: maxBytes * 2, shell: '/bin/bash' }).toString();
    const cut = out.lastIndexOf('__ESTATE_STATUS__');
    const status = cut >= 0 ? Number(out.slice(cut + 17).trim()) : 0;
    return { status, body: (cut >= 0 ? out.slice(0, cut) : out).slice(0, maxBytes) };
  },

  // strip a fetched HTML document to readable text (crude but dependency-free)
  textOf(html) {
    return String(html)
      .replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<style[\s\S]*?<\/style>/gi, ' ')
      .replace(/<[^>]+>/g, ' ').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#39;|&apos;/g, "'").replace(/&quot;/g, '"')
      .replace(/[ \t]+/g, ' ').replace(/\n\s*\n\s*\n+/g, '\n\n').trim();
  },

  async shutdown() {
    try { await cdp.send('Browser.close'); } catch {}
    try { fs.rmSync(STATE, { force: true }); } catch {}
    console.log('browser closed.');
  },
};

// ---------- main ----------
const script = fs.readFileSync(0, 'utf-8');
if (!script.trim()) { console.error('no script on stdin'); process.exit(1); }

// Only spin up Chromium when the script actually drives a page. Scripts that
// only fetch/parse skip the browser entirely (and work where its TLS can't).
const needsBrowser = /\b(open|snapshotText|click|fill|press|scroll|waitFor|js|shot|tabs|switchTab|closeTab|pageInfo|shutdown)\s*\(/.test(script);

if (needsBrowser) {
  const wsUrl = await ensureBrowser();
  cdp = await new Cdp(wsUrl).connect();
}

try {
  const run = new (Object.getPrototypeOf(async function () {}).constructor)(...Object.keys(helpers), script);
  await run(...Object.values(helpers));
} catch (error) {
  console.error('script error:', error.message);
  process.exitCode = 1;
} finally {
  if (cdp) cdp.close(); // the browser daemon stays up between rounds
}
