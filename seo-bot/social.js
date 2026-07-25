// social.js — the office speaks, on a schedule, where it has been given keys.
// bluesky: set BLUESKY_HANDLE + BLUESKY_APP_PASSWORD (settings > app passwords)
// discord: set DISCORD_WEBHOOK_URL (channel > integrations > webhooks)
// cadence: SOCIAL_CADENCE_HOURS (default 48). no keys = the office stays quiet.
//
// posts rotate through the queue below; dedupe is done against the account's
// own latest posts so restarts never double-post.

const SITE = 'https://bandersnatch.world';

const QUEUE = [
  `the office is open. one county, photographed since 1935. the animal is never shown — only what it took.\n\n${SITE}`,
  `entry 90-042: a trap was found at the county line, new-set and unsprung. a blue canary sat over it and sang, and did not move off. the trap is in the file.\n\n${SITE}/record.html`,
  `the cardinal was counted at the county line. one. it is always one.\n\n${SITE}/bestiary.html`,
  `every holding is screen printed in an edition of 24, numbered by hand, sealed in wax. when the edition is gone it is gone. the office does not restock.\n\n${SITE}/file.html`,
  `1943: this office received its order of dissolution, filed it, and remained. the order is in the file, stamped received. nothing further was done with it.\n\n${SITE}/history.html`,
  `every field photographer of record is named virginia. the office does not explain this. the numbers accumulate. no one is replaced.\n\n${SITE}/virginia.html`,
  `entry 90-043: the trap was collected. nothing was caught in it, and nothing has been since. filed under: prayer.\n\n${SITE}/record.html`,
  `a canister of film was left on the counter overnight. no one was seen. it is marked vii. it has not been developed.\n\n${SITE}/record.html`,
  `what is not known is not in the file.\n\n${SITE}`,
  `the chapel bells rang at four in the morning. the chapel has no bells. filed.\n\n${SITE}/record.html`,
];

const log = (msg) => console.log(`[${new Date().toISOString()}] ${msg}`);

function nextPost() {
  // deterministic rotation: one queue item per cadence window since a fixed epoch
  const cadenceH = parseFloat(process.env.SOCIAL_CADENCE_HOURS || '48');
  const epoch = Date.UTC(2026, 6, 25); // fixed start; do not change or rotation shifts
  const windowIdx = Math.floor((Date.now() - epoch) / (cadenceH * 3600 * 1000));
  return QUEUE[((windowIdx % QUEUE.length) + QUEUE.length) % QUEUE.length];
}

async function blueskyTick() {
  const handle = process.env.BLUESKY_HANDLE;
  const pass = process.env.BLUESKY_APP_PASSWORD;
  if (!handle || !pass) return 'bluesky: no keys — the office stays quiet';
  const text = nextPost();
  try {
    const sess = await fetch('https://bsky.social/xrpc/com.atproto.server.createSession', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ identifier: handle, password: pass }),
    }).then((r) => r.json());
    if (!sess.accessJwt) return `bluesky: auth failed (${sess.error || 'unknown'})`;

    // dedupe: skip if the latest post in this account already is this text
    const feed = await fetch(
      `https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed?actor=${encodeURIComponent(sess.did)}&limit=5`,
      { headers: { authorization: `Bearer ${sess.accessJwt}` } }
    ).then((r) => r.json());
    const recent = (feed.feed || []).map((f) => f.post && f.post.record && f.post.record.text);
    if (recent.includes(text)) return 'bluesky: current window already posted';

    const facets = [];
    const urlMatch = text.match(/https:\/\/\S+/);
    if (urlMatch) {
      const enc = new TextEncoder();
      const byteStart = enc.encode(text.slice(0, urlMatch.index)).length;
      facets.push({
        index: { byteStart, byteEnd: byteStart + enc.encode(urlMatch[0]).length },
        features: [{ $type: 'app.bsky.richtext.facet#link', uri: urlMatch[0] }],
      });
    }
    const res = await fetch('https://bsky.social/xrpc/com.atproto.repo.createRecord', {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${sess.accessJwt}` },
      body: JSON.stringify({
        repo: sess.did,
        collection: 'app.bsky.feed.post',
        record: { $type: 'app.bsky.feed.post', text, facets, createdAt: new Date().toISOString() },
      }),
    });
    return res.ok ? `bluesky: posted (${text.slice(0, 40)}…)` : `bluesky: post failed HTTP ${res.status}`;
  } catch (e) {
    return `bluesky: error ${e.message}`;
  }
}

let lastDiscordWindow = -1;
async function discordTick() {
  const hook = process.env.DISCORD_WEBHOOK_URL;
  if (!hook) return 'discord: no webhook — the office stays quiet';
  const cadenceH = parseFloat(process.env.SOCIAL_CADENCE_HOURS || '48');
  const windowIdx = Math.floor((Date.now() - Date.UTC(2026, 6, 25)) / (cadenceH * 3600 * 1000));
  if (windowIdx === lastDiscordWindow) return 'discord: current window already posted';
  try {
    const res = await fetch(hook, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ content: nextPost(), username: 'the office' }),
    });
    if (res.ok || res.status === 204) { lastDiscordWindow = windowIdx; return 'discord: posted'; }
    return `discord: failed HTTP ${res.status}`;
  } catch (e) {
    return `discord: error ${e.message}`;
  }
}

async function socialTick() {
  log(await blueskyTick());
  log(await discordTick());
}

module.exports = { socialTick, QUEUE };
