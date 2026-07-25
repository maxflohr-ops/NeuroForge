#!/usr/bin/env node
/**
 * the seo bot — bandersnatch office, standing patrol · v2
 * --------------------------------------------------------
 * every INTERVAL_HOURS:
 *   - patrols bandersnatch.world: page health, titles, meta, canonicals,
 *     page weight, response time, robots.txt, store-link reachability
 *   - detects content changes per page and submits changed URLs to
 *     IndexNow when the key file is live
 *   - pulls the live catalog from the store's public products.json and
 *     regenerates marketplace listing packs (poshmark/depop/grailed/
 *     ebay/etsy) — served over http for copy-paste listing
 *   - runs the social tick: posts queued lore to bluesky/discord when
 *     keys are present (see social.js)
 *
 * http endpoints (railway domain):
 *   /            the counter
 *   /health      liveness json
 *   /report      last patrol report (text)
 *   /packs       listing packs (json)
 *   /packs.md    listing packs (markdown, human-ready)
 */

const crypto = require('crypto');
const http = require('http');
const { fetchCatalog } = require('./catalog');
const { buildPacks, packsMarkdown } = require('./packs');
const { socialTick } = require('./social');

const SITE = (process.env.SITE_URL || 'https://bandersnatch.world').replace(/\/$/, '');
const INTERVAL_H = parseFloat(process.env.INTERVAL_HOURS || '6');
const INDEXNOW_KEY = process.env.INDEXNOW_KEY || '';
const RUN_ONCE = process.env.RUN_ONCE === '1';
const PORT = parseInt(process.env.PORT || '8080', 10);

const state = new Map(); // url -> content hash
let lastReport = 'no patrol has run yet. the office is waking.';
let packs = [];
let packsMd = '# packs not yet generated';

const log = (msg) => console.log(`[${new Date().toISOString()}] ${msg}`);

async function get(url, method = 'GET') {
  const t0 = Date.now();
  try {
    const res = await fetch(url, { method, redirect: 'manual', headers: { 'user-agent': 'bandersnatch-office-bot/2.0 (+https://bandersnatch.world)' } });
    const body = method === 'GET' ? await res.text() : '';
    return { status: res.status, ms: Date.now() - t0, body };
  } catch (e) {
    return { status: 0, ms: Date.now() - t0, body: '', error: e.message };
  }
}

function audit(url, body) {
  const issues = [];
  const title = (body.match(/<title>([^<]*)<\/title>/i) || [])[1];
  if (!title) issues.push('no <title>');
  if (!/<meta\s+name=["']description["']/i.test(body)) issues.push('no meta description');
  const canon = (body.match(/<link\s+rel=["']canonical["']\s+href=["']([^"']+)["']/i) || [])[1];
  if (!canon) issues.push('no canonical');
  else if (canon !== url) issues.push(`canonical mismatch: ${canon}`);
  if (body.length > 200 * 1024) issues.push(`page weight ${(body.length / 1024).toFixed(0)}KB > 200KB`);
  return issues;
}

async function indexNowSubmit(urls, report) {
  if (!INDEXNOW_KEY || urls.length === 0) return;
  const keyUrl = `${SITE}/${INDEXNOW_KEY}.txt`;
  const keyCheck = await get(keyUrl, 'HEAD');
  if (keyCheck.status !== 200) {
    report.push(`indexnow: key file not live at ${keyUrl} (HTTP ${keyCheck.status}) — submission held`);
    return;
  }
  try {
    const res = await fetch('https://api.indexnow.org/indexnow', {
      method: 'POST',
      headers: { 'content-type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ host: new URL(SITE).host, key: INDEXNOW_KEY, keyLocation: keyUrl, urlList: urls }),
    });
    report.push(`indexnow: submitted ${urls.length} url(s) — HTTP ${res.status}`);
  } catch (e) {
    report.push(`indexnow: submission failed — ${e.message}`);
  }
}

async function patrol() {
  const report = [];
  const say = (m) => { report.push(m); log(m); };
  say(`patrol begins — ${SITE}`);

  const robots = await get(`${SITE}/robots.txt`);
  if (robots.status !== 200) say(`DEFECT robots.txt — HTTP ${robots.status}`);

  const sm = await get(`${SITE}/sitemap.xml`);
  if (sm.status !== 200) {
    say(`SITEMAP DOWN: HTTP ${sm.status} ${sm.error || ''} — patrol abandoned`);
    lastReport = report.join('\n');
    return;
  }
  const urls = [...sm.body.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
  say(`sitemap lists ${urls.length} pages`);

  const changed = [];
  let defects = 0;
  const productLinks = new Set();

  for (const url of urls) {
    const page = await get(url);
    if (page.status !== 200) { defects++; say(`  DEFECT ${url} — HTTP ${page.status} ${page.error || ''}`); continue; }
    const issues = audit(url, page.body);
    if (issues.length) { defects += issues.length; say(`  DEFECT ${url} — ${issues.join(' · ')}`); }
    const hash = crypto.createHash('sha256').update(page.body).digest('hex');
    if (state.has(url) && state.get(url) !== hash) { changed.push(url); say(`  changed: ${url}`); }
    state.set(url, hash);
    for (const m of page.body.matchAll(/href="(https:\/\/[a-z0-9-]+\.myshopify\.com\/[^"]*)"/g)) productLinks.add(m[1]);
    if (page.ms > 3000) say(`  slow: ${url} took ${page.ms}ms`);
  }

  try {
    const catalog = await fetchCatalog();
    packs = buildPacks(catalog);
    packsMd = packsMarkdown(packs);
    say(`listing packs regenerated: ${packs.length} holdings × 5 marketplaces`);
  } catch (e) {
    say(`catalog pull failed: ${e.message} — packs kept from last run`);
  }

  for (const link of productLinks) {
    await new Promise((r) => setTimeout(r, 2000)); // shopify rate-limits bursts
    const res = await get(link, 'HEAD');
    if (res.status === 0 || (res.status >= 400 && res.status !== 429 && res.status !== 430)) {
      defects++;
      say(`  DEFECT store link ${link} — HTTP ${res.status} ${res.error || ''}`);
    }
  }
  say(`store links checked: ${productLinks.size}`);

  await indexNowSubmit(changed, report);

  await socialTick();

  say(defects === 0 ? `patrol complete. no defects. the file is in order.` : `patrol complete. ${defects} defect(s) filed above.`);
  lastReport = report.join('\n');
}

function serve() {
  const server = http.createServer((req, res) => {
    const path = (req.url || '/').split('?')[0];
    const send = (code, type, body) => { res.writeHead(code, { 'content-type': type }); res.end(body); };
    if (path === '/health') return send(200, 'application/json', JSON.stringify({ ok: true, site: SITE, intervalHours: INTERVAL_H }));
    if (path === '/report') return send(200, 'text/plain; charset=utf-8', lastReport);
    if (path === '/packs') return send(200, 'application/json', JSON.stringify(packs, null, 2));
    if (path === '/packs.md') return send(200, 'text/markdown; charset=utf-8', packsMd);
    if (path === '/') return send(200, 'text/plain; charset=utf-8',
      'the office is open.\n\n/report   — last patrol\n/packs.md — listing packs, ready to paste\n/packs    — listing packs, json\n/health   — liveness\n\nthe file is not closed.\n');
    return send(404, 'text/plain; charset=utf-8', 'not in the file.\n');
  });
  server.listen(PORT, () => log(`counter open on :${PORT}`));
}

(async () => {
  if (!RUN_ONCE) serve();
  await patrol();
  if (RUN_ONCE) return;
  log(`standing patrol: every ${INTERVAL_H}h`);
  setInterval(() => patrol().catch((e) => log(`patrol error: ${e.message}`)), INTERVAL_H * 3600 * 1000);
})();
