#!/usr/bin/env node
/**
 * the seo bot — bandersnatch office, standing patrol
 * ---------------------------------------------------
 * Watches bandersnatch.world on an interval:
 *   - fetches the sitemap, checks every page: HTTP status, response time,
 *     <title>, meta description, canonical tag, page weight
 *   - checks the Shopify product links found on the file page
 *   - detects content changes (per-page hash) and submits changed URLs
 *     to IndexNow (Bing/Yandex/etc.) when INDEXNOW_KEY is set and the
 *     key file is live on the site
 *   - prints a clerk-style report to the log every run
 *
 * Env:
 *   SITE_URL        default https://bandersnatch.world
 *   INTERVAL_HOURS  default 6
 *   INDEXNOW_KEY    optional; enables IndexNow submission
 *   RUN_ONCE        set to "1" to run a single patrol and exit
 */

const SITE = (process.env.SITE_URL || 'https://bandersnatch.world').replace(/\/$/, '');
const INTERVAL_H = parseFloat(process.env.INTERVAL_HOURS || '6');
const INDEXNOW_KEY = process.env.INDEXNOW_KEY || '';
const RUN_ONCE = process.env.RUN_ONCE === '1';

const crypto = require('crypto');
const state = new Map(); // url -> content hash

const log = (msg) => console.log(`[${new Date().toISOString()}] ${msg}`);

async function get(url, method = 'GET') {
  const t0 = Date.now();
  try {
    const res = await fetch(url, { method, redirect: 'manual', headers: { 'user-agent': 'bandersnatch-office-bot/1.0 (+https://bandersnatch.world)' } });
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
  const desc = /<meta\s+name=["']description["']/i.test(body);
  if (!desc) issues.push('no meta description');
  const canon = (body.match(/<link\s+rel=["']canonical["']\s+href=["']([^"']+)["']/i) || [])[1];
  if (!canon) issues.push('no canonical');
  else if (canon !== url) issues.push(`canonical mismatch: ${canon}`);
  if (body.length > 200 * 1024) issues.push(`page weight ${(body.length / 1024).toFixed(0)}KB > 200KB`);
  return issues;
}

async function indexNowSubmit(urls) {
  if (!INDEXNOW_KEY || urls.length === 0) return;
  const keyUrl = `${SITE}/${INDEXNOW_KEY}.txt`;
  const keyCheck = await get(keyUrl, 'HEAD');
  if (keyCheck.status !== 200) {
    log(`indexnow: key file not live at ${keyUrl} (HTTP ${keyCheck.status}) — submission held`);
    return;
  }
  try {
    const res = await fetch('https://api.indexnow.org/indexnow', {
      method: 'POST',
      headers: { 'content-type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ host: new URL(SITE).host, key: INDEXNOW_KEY, keyLocation: keyUrl, urlList: urls }),
    });
    log(`indexnow: submitted ${urls.length} url(s) — HTTP ${res.status}`);
  } catch (e) {
    log(`indexnow: submission failed — ${e.message}`);
  }
}

async function patrol() {
  log(`patrol begins — ${SITE}`);
  const sm = await get(`${SITE}/sitemap.xml`);
  if (sm.status !== 200) {
    log(`SITEMAP DOWN: HTTP ${sm.status} ${sm.error || ''} — patrol abandoned`);
    return;
  }
  const urls = [...sm.body.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
  log(`sitemap lists ${urls.length} pages`);

  const changed = [];
  let defects = 0;
  const productLinks = new Set();

  for (const url of urls) {
    const page = await get(url);
    if (page.status !== 200) {
      defects++;
      log(`  DEFECT ${url} — HTTP ${page.status} ${page.error || ''}`);
      continue;
    }
    const issues = audit(url, page.body);
    if (issues.length) {
      defects += issues.length;
      log(`  DEFECT ${url} — ${issues.join(' · ')}`);
    }
    const hash = crypto.createHash('sha256').update(page.body).digest('hex');
    if (state.has(url) && state.get(url) !== hash) {
      changed.push(url);
      log(`  changed: ${url}`);
    }
    state.set(url, hash);
    for (const m of page.body.matchAll(/href="(https:\/\/[a-z0-9-]+\.myshopify\.com\/[^"]*)"/g)) {
      productLinks.add(m[1]);
    }
    if (page.ms > 3000) log(`  slow: ${url} took ${page.ms}ms`);
  }

  for (const link of productLinks) {
    await new Promise((r) => setTimeout(r, 2000)); // shopify rate-limits bursts
    const res = await get(link, 'HEAD');
    // 301/302 = fine; 429/430 = shopify throttling our check, not a dead link
    if (res.status === 0 || (res.status >= 400 && res.status !== 429 && res.status !== 430)) {
      defects++;
      log(`  DEFECT store link ${link} — HTTP ${res.status} ${res.error || ''}`);
    }
  }
  log(`store links checked: ${productLinks.size}`);

  await indexNowSubmit(changed);

  log(defects === 0
    ? `patrol complete. no defects. the file is in order.`
    : `patrol complete. ${defects} defect(s) filed above.`);
}

(async () => {
  await patrol();
  if (RUN_ONCE) return;
  log(`standing patrol: every ${INTERVAL_H}h`);
  setInterval(() => patrol().catch((e) => log(`patrol error: ${e.message}`)), INTERVAL_H * 3600 * 1000);
})();
