// catalog.js — pulls the live holdings from the store's public products.json
const STORE = (process.env.STORE_URL || 'https://bandersnatch-2.myshopify.com').replace(/\/$/, '');

function stripHtml(html) {
  return (html || '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&#39;|&rsquo;/g, "'").replace(/&quot;|&ldquo;|&rdquo;/g, '"')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

async function fetchCatalog() {
  let res;
  for (let attempt = 1; attempt <= 3; attempt++) {
    res = await fetch(`${STORE}/products.json?limit=250`, {
      headers: { 'user-agent': 'bandersnatch-office-bot/2.0 (+https://bandersnatch.world)' },
    });
    if (res.ok) break;
    if (res.status === 429 || res.status === 430) {
      await new Promise((r) => setTimeout(r, attempt * 20000)); // back off, shopify
      continue;
    }
    break;
  }
  if (!res.ok) throw new Error(`catalog fetch failed: HTTP ${res.status}`);
  const data = await res.json();
  return (data.products || []).map((p) => ({
    title: p.title,
    handle: p.handle,
    url: `${STORE}/products/${p.handle}`,
    type: p.product_type || 'screen printed tee',
    tags: p.tags || [],
    description: stripHtml(p.body_html),
    price: p.variants && p.variants[0] ? p.variants[0].price : null,
    sizes: (p.variants || []).map((v) => v.title),
    images: (p.images || []).map((i) => i.src),
    updatedAt: p.updated_at,
  }));
}

module.exports = { fetchCatalog, STORE };
