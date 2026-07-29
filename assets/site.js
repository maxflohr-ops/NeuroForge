/* ------------------------------------------------------------------
   bandersnatch · site.js
   the clerk keeps the machinery. plain script, no dependencies.
   ------------------------------------------------------------------ */
(function () {
  'use strict';

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---- entrance title card — once per session, click or key skips ---- */
  try {
    if (!reduced && !sessionStorage.getItem('bs-entered')) {
      sessionStorage.setItem('bs-entered', '1');
      var card = document.createElement('div');
      card.className = 'titlecard';
      card.setAttribute('aria-hidden', 'true');
      card.innerHTML =
        '<div>' +
        '<p class="tc-office">federal photography project · field office e · southern region</p>' +
        '<p class="tc-name">bandersnatch</p>' +
        '<p class="tc-line">the office is open.</p>' +
        '</div>';
      document.body.appendChild(card);
      var gone = false;
      var out = function () {
        if (gone) return;
        gone = true;
        card.classList.add('is-out');
        setTimeout(function () { card.remove(); }, 950);
      };
      setTimeout(out, 2700);
      card.addEventListener('click', out);
      window.addEventListener('keydown', out, { once: true });
    }
  } catch (e) { /* sessionStorage unavailable — enter without ceremony */ }

  /* ---- slow fades as the visitor walks the rooms ---- */
  var revs = document.querySelectorAll('.reveal');
  if (revs.length && 'IntersectionObserver' in window && !reduced) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.add('lit');
          io.unobserve(en.target);
        }
      });
    }, { threshold: 0.12 });
    revs.forEach(function (el) { io.observe(el); });
  } else {
    revs.forEach(function (el) { el.classList.add('lit'); });
  }

  /* ---- lamplight — file.html; mouse follows, touch drifts ---- */
  var lampField = document.querySelector('[data-lamp]');
  if (lampField && !reduced) {
    var lamp = document.createElement('div');
    lamp.className = 'lamp';
    lamp.setAttribute('aria-hidden', 'true');
    document.body.appendChild(lamp);

    var lx = window.innerWidth / 2;
    var ly = window.innerHeight * 0.4;
    var drifting = true;

    var paint = function () {
      lamp.style.setProperty('--lx', lx + 'px');
      lamp.style.setProperty('--ly', ly + 'px');
    };
    paint();

    window.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'mouse') {
        drifting = false;
        lx = e.clientX;
        ly = e.clientY;
        paint();
      }
    });

    var drift = function (ts) {
      if (drifting) {
        var t = ts / 1000;
        lx = window.innerWidth * (0.5 + 0.33 * Math.sin(t * 0.13));
        ly = window.innerHeight * (0.45 + 0.28 * Math.sin(t * 0.09 + 2));
        paint();
      }
      window.requestAnimationFrame(drift);
    };
    window.requestAnimationFrame(drift);
  }

  /* ---- WHAT WAS TAKEN — types and erases the answers on a loop ---- */
  var taken = document.getElementById('taken');
  if (taken) {
    var ANSWERS = ['the family.', 'the topsoil.', 'the mine, then the town.'];
    var BLANK = '————';
    if (reduced) {
      var ri = 0;
      taken.textContent = ANSWERS[0];
      setInterval(function () {
        ri = (ri + 1) % ANSWERS.length;
        taken.textContent = ANSWERS[ri];
      }, 5000);
    } else {
      var ai = 0;
      var typeNext = function () {
        var s = ANSWERS[ai];
        var n = 0;
        var t = setInterval(function () {
          n++;
          taken.textContent = s.slice(0, n);
          if (n >= s.length) {
            clearInterval(t);
            setTimeout(erase, 2400);
          }
        }, 70);
        var erase = function () {
          var t2 = setInterval(function () {
            n--;
            taken.textContent = n > 0 ? s.slice(0, n) : BLANK;
            if (n <= 0) {
              clearInterval(t2);
              ai = (ai + 1) % ANSWERS.length;
              setTimeout(typeNext, 1100);
            }
          }, 32);
        };
      };
      setTimeout(typeNext, 1400);
    }
  }

  /* ---- the clerk — counter.html; answers what the file permits ---- */
  var clerkForm = document.getElementById('clerk-form');
  if (clerkForm) {
    var log = document.getElementById('clerk-log');
    var input = document.getElementById('clerk-input');

    var RULES = [
      [/restock|re-?stock|sold\s*out|back\s*in\s*stock|available\s*again|another\s*run|reprint/i,
        'the office does not restock. the office keeps things; that is different.'],
      [/bandersnatch|animal|beast|creature|monster|greed/i,
        'the office has no photograph of that.'],
      [/cardinal|red\s?bird|\blove\b/i, 'it stayed.'],
      [/virginia|photographer|\bdied?\b|\bdeath\b|\bdead\b|\balive\b/i,
        'the date stays open.'],
      [/canary|\bblue\b/i,
        'it went into the dark and it came back. the file says no more than that.'],
      [/\bclosed?\b|\bhours\b|\bopen\b/i, 'the file is not closed.'],
      [/hello|\bhi\b|\bhey\b|howdy|good\s+(morning|afternoon|evening|day)/i,
        'state your business.']
    ];

    var answer = function (q) {
      for (var i = 0; i < RULES.length; i++) {
        if (RULES[i][0].test(q)) return RULES[i][1];
      }
      return 'not in the file.';
    };

    var typeInto = function (p, prefix, text) {
      var n = 0;
      var t = setInterval(function () {
        n++;
        p.textContent = prefix + text.slice(0, n);
        if (n >= text.length) clearInterval(t);
      }, 28);
    };

    var addLine = function (who, text, typed) {
      var p = document.createElement('p');
      p.className = who === 'you' ? 'log-you' : 'log-office';
      var prefix = who === 'you' ? 'you — ' : 'the office — ';
      if (typed && !reduced) {
        p.textContent = prefix;
        log.appendChild(p);
        typeInto(p, prefix, text);
      } else {
        p.textContent = prefix + text;
        log.appendChild(p);
      }
    };

    var pending = false;
    clerkForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var q = input.value.trim();
      if (!q || pending) return;
      addLine('you', q);
      input.value = '';
      pending = true;
      var localAnswer = answer(q);
      var settle = function (a) { pending = false; addLine('office', a, true); };
      /* the attended counter — the real clerk answers when the office
         holds a key; any failure falls back to the rules above. */
      fetch('/api/clerk', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ q: q }),
      })
        .then(function (r) {
          return r.json().then(function (d) { return { ok: r.ok, d: d }; });
        })
        .then(function (out) {
          settle(out.ok && out.d && out.d.answer ? out.d.answer : localAnswer);
        })
        .catch(function () {
          setTimeout(function () { settle(localAnswer); }, 400);
        });
    });

    addLine('office', 'state your business.', true);
  }

  /* ---- the ledger — signatures are filed with the office ---- */
  var ledgerForm = document.getElementById('ledger-form');
  if (ledgerForm) {
    ledgerForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var name = (document.getElementById('lg-name') || {}).value || '';
      var email = (document.getElementById('lg-email') || {}).value || '';
      if (!email) return;
      /* simple-request body so no cors preflight; the office door accepts it */
      fetch(ledgerForm.action, {
        method: 'POST',
        mode: 'no-cors',
        body: new URLSearchParams({ kind: 'ledger', name: name, email: email }),
      }).catch(function () { /* the page keeps its manners either way */ });
      var note = document.getElementById('ledger-note');
      if (note) note.textContent = 'signed. the ledger keeps what it is given.';
      ledgerForm.reset();
    });
  }
})();
