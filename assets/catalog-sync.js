/* catalog-sync — the ledger keeps itself.
   pulls the live catalog from the store on page load and reconciles the
   page: holdings added in shopify appear here without a deploy, sizes
   that sell out are struck from the record, and a lot whose edition is
   gone is stamped gone. the static markup stays canonical for crawlers
   and no-js readers; on any failure the page stands as printed. */
(function () {
  'use strict';
  var STORE = 'https://bandersnatch-2.myshopify.com';
  var row = document.querySelector('[data-catalog-row]');
  var mounts = document.querySelector('[data-catalog-mounts]');
  if (!row && !mounts) return;

  function lotNum(title) {
    var m = /lot no\.\s*0*(\d+)/i.exec(title || '');
    return m ? parseInt(m[1], 10) : null;
  }
  function shortTitle(title) {
    return (title || '').replace(/^lot no\.\s*\d+\s*·\s*/i, '');
  }
  function stripHtml(html) {
    var div = document.createElement('div');
    div.innerHTML = (html || '').replace(/<br\s*\/?>/gi, '\n').replace(/<\/p>/gi, '\n');
    return (div.textContent || '').replace(/\n{2,}/g, '\n').trim();
  }
  function firstSentence(text) {
    var m = (text || '').split(/(?<=[.?])\s+/)[0] || '';
    return m.length > 160 ? m.slice(0, 157) + '…' : m;
  }
  function money(price) {
    var n = parseFloat(price);
    if (isNaN(n)) return '';
    return '$' + (n % 1 === 0 ? n.toFixed(0) : n.toFixed(2));
  }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  function normalize(products) {
    return products
      .map(function (p) {
        var sizes = (p.variants || []).map(function (v) {
          return { t: (v.title || '').toLowerCase(), ok: v.available !== false };
        });
        return {
          id: p.id,
          num: lotNum(p.title),
          title: (p.title || '').toLowerCase(),
          short: shortTitle(p.title || '').toLowerCase(),
          url: STORE + '/products/' + p.handle,
          handle: p.handle,
          image: p.images && p.images[0] ? p.images[0].src : null,
          price: p.variants && p.variants[0] ? p.variants[0].price : null,
          epigraph: firstSentence(stripHtml(p.body_html)).toLowerCase(),
          sizes: sizes,
          gone: sizes.length > 0 && sizes.every(function (s) { return !s.ok; }),
        };
      })
      .filter(function (p) { return p.image; })
      .sort(function (a, b) { return (a.num || 999) - (b.num || 999); });
  }

  /* "held: s · m · l" — sold sizes stay on the line, struck through */
  function sizesLine(p) {
    if (!p.sizes.length) return null;
    var line = el('p', 'sizes-held');
    line.appendChild(document.createTextNode('held: '));
    p.sizes.forEach(function (s, i) {
      if (i) line.appendChild(document.createTextNode(' · '));
      line.appendChild(el('span', s.ok ? null : 'size-gone', s.t));
    });
    return line;
  }

  /* the front room — rebuild the "now printing" row with every holding */
  function syncRow(products) {
    var frag = document.createDocumentFragment();
    products.forEach(function (p) {
      var a = el('a', p.gone ? 'plate-link gone' : 'plate-link');
      a.href = p.url;
      a.rel = 'noopener';
      var img = document.createElement('img');
      img.src = p.image + (p.image.indexOf('?') > -1 ? '&' : '?') + 'width=480';
      img.alt = p.title + ' — product photograph from the file';
      img.width = 480;
      img.height = 600;
      img.loading = 'lazy';
      a.appendChild(img);
      var cap = p.num !== null ? 'lot ' + String(p.num).padStart(3, '0') : p.title;
      var tail = p.gone ? ' · gone' : (p.price ? ' · ' + money(p.price) : '');
      a.appendChild(el('p', 'plate-cap', cap + ' · ' + p.short + tail));
      frag.appendChild(a);
    });
    row.textContent = '';
    row.appendChild(frag);
  }

  /* stamp an existing static card with what the store knows */
  function applyScarcity(card, p) {
    var file = card.querySelector('.mount-file');
    if (!file) return;
    if (!file.querySelector('.sizes-held')) {
      var line = sizesLine(p);
      if (line) {
        var link = file.querySelector('.holding-link');
        file.insertBefore(line, link || null);
      }
    }
    if (p.gone) {
      card.classList.add('mount--gone');
      var stamp = file.querySelector('.stamp');
      if (stamp) {
        stamp.textContent = 'gone';
        stamp.className = 'stamp stamp-gone';
      }
      var req = file.querySelector('.holding-link');
      if (req) req.replaceWith(el('p', 'gone-note', 'the edition is gone. the office does not restock.'));
    }
  }

  function buildMount(p) {
    var art = el('article', p.gone ? 'mount mount--gone reveal lit' : 'mount reveal lit');

    var plate = el('a', 'mount-plate');
    plate.href = p.url;
    plate.rel = 'noopener';
    plate.tabIndex = -1;
    plate.setAttribute('aria-hidden', 'true');
    var img = document.createElement('img');
    img.src = p.image + (p.image.indexOf('?') > -1 ? '&' : '?') + 'width=360';
    img.alt = '';
    img.width = 360;
    img.height = 450;
    img.loading = 'lazy';
    plate.appendChild(img);
    art.appendChild(plate);

    var meta = el('div', 'mount-meta');
    meta.appendChild(el('p', 'neg', 'neg. no. e-33-' + String(p.id).slice(-6) + '-m1'));
    meta.appendChild(el('p', 'classline', p.num !== null ? 'lot ' + String(p.num).padStart(3, '0') : 'lot —'));
    art.appendChild(meta);

    var body = el('div', 'mount-body');
    var h2 = el('h2', 'mount-title');
    var link = el('a', null, p.short);
    link.href = p.url;
    link.rel = 'noopener';
    h2.appendChild(link);
    body.appendChild(h2);
    if (p.epigraph) body.appendChild(el('p', 'mount-epigraph', p.epigraph));
    art.appendChild(body);

    var file = el('div', 'mount-file');
    file.appendChild(el('p', p.gone ? 'stamp stamp-gone' : 'stamp stamp-printed', p.gone ? 'gone' : 'printed'));
    file.appendChild(el('p', null, 'edition of 24 · numbered by hand'));
    if (p.price) file.appendChild(el('p', null, money(p.price)));
    var sizes = sizesLine(p);
    if (sizes) file.appendChild(sizes);
    if (p.gone) {
      file.appendChild(el('p', 'gone-note', 'the edition is gone. the office does not restock.'));
    } else {
      var req = el('a', 'holding-link', 'request the holding →');
      req.href = p.url;
      req.rel = 'noopener';
      file.appendChild(req);
    }
    art.appendChild(file);
    return art;
  }

  /* the file — stamp what is already mounted, and mount any holding the
     static ledger does not carry yet. a new lot takes over its "untitled"
     placeholder card when one waits under the same number; otherwise it
     is mounted ahead of the placeholders, so the untitled cards keep the
     end of the wall. */
  function syncMounts(products) {
    var byHandle = {};
    products.forEach(function (p) { byHandle[p.handle] = p; });

    var known = {};
    mounts.querySelectorAll('.mount').forEach(function (card) {
      var a = card.querySelector('a[href*="/products/"]');
      if (!a) return;
      var m = /\/products\/([a-z0-9-]+)/.exec(a.getAttribute('href') || '');
      if (!m) return;
      known[m[1]] = true;
      if (byHandle[m[1]]) applyScarcity(card, byHandle[m[1]]);
    });

    var placeholders = {};
    var firstPlaceholder = null;
    mounts.querySelectorAll('.mount--untitled').forEach(function (card) {
      if (!firstPlaceholder) firstPlaceholder = card;
      var line = card.querySelector('.classline');
      var m = /lot\s*0*(\d+)/i.exec(line ? line.textContent : '');
      if (m) placeholders[parseInt(m[1], 10)] = card;
    });

    products.forEach(function (p) {
      if (known[p.handle]) return;
      known[p.handle] = true;
      var art = buildMount(p);
      var placeholder = p.num !== null ? placeholders[p.num] : null;
      if (placeholder) {
        mounts.replaceChild(art, placeholder);
        if (placeholder === firstPlaceholder) {
          firstPlaceholder = mounts.querySelector('.mount--untitled');
        }
      } else if (firstPlaceholder) {
        mounts.insertBefore(art, firstPlaceholder);
      } else {
        mounts.appendChild(art);
      }
    });
  }

  fetch(STORE + '/products.json?limit=250')
    .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error(r.status)); })
    .then(function (data) {
      var products = normalize(data.products || []);
      if (!products.length) return;
      if (row) syncRow(products);
      if (mounts) syncMounts(products);
    })
    .catch(function () { /* the page stands as printed */ });
})();
