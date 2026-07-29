/* record-roll — the record keeps filing.
   one new dispatch enters the record every other day, on the office's
   clock, with no deploy: entries below reveal on a fixed 48-hour cadence
   from a fixed epoch. do not change the epoch or the numbering shifts.
   when the queue runs dry the office writes more (append only — never
   reorder, or already-filed entries change numbers). */
(function () {
  'use strict';
  var section = document.querySelector('section[aria-label="dispatches"]');
  if (!section) return;

  var EPOCH = Date.UTC(2026, 6, 29);       // fixed start; do not change
  var WINDOW_MS = 48 * 3600 * 1000;        // one entry every other day
  var FIRST_NO = 44;                        // continues from entry 90-043

  /* the queue. each string is one dispatch; links use [text](href). */
  var QUEUE = [
    'the canister marked vii was moved from the counter to the safe. no one moved it. the safe was locked before and after. filed.',
    'a wedding dress was found hanging in the burned house on the creek road, clean, pressed, facing the door. the house has been burned since 1962. see [the record of the county](history.html).',
    'the flood mark was measured. it had not moved. this is entered because it is the first year it has not.',
    'three photographs came back from the county line with the horizon at a different height in each. the camera was on a tripod. the tripod is in the file.',
    'the cardinal was counted early this year. one. it sat on the office sill through the counting and left when the ledger closed. see [the bestiary, plate ii](bestiary.html).',
    'damage, class .0100: the fence at the east quarter again, opened from the inside again. the office notes that the fence has never once been closed from the outside. the animal is not in the file.',
    'a visitor signed [the ledger](ledger.html) with a name the ledger already held, in the same hand, dated 1951. the visitor was asked no question. the office keeps what it is given.',
    'the porch light on delilah road went dark on tuesday. it was relit by thursday. no one lives there. no one relit it. see [lot 005](file.html).',
    'the chapel was photographed for the annual record. in the print there is a light in the window. the chapel has no glass. the negative agrees with the print. filed.',
    'virginia filed eleven negatives and a note reading "the county is further away than it was." the note is in the file. the negatives are ordinary. see [the succession](virginia.html).',
    'a second trap was found at the county line, sprung, empty, rusted as if years old. it was new-set in september. the canary was not seen. filed under: patience.',
    'the office received a letter addressed to the archivist by name. the envelope is in the file. the letter is not entered. the archivist has no name in the file.',
  ];

  var idx = Math.floor((Date.now() - EPOCH) / WINDOW_MS);
  if (idx < 0) return;
  var count = Math.min(idx + 1, QUEUE.length);
  if (count <= 0) return;

  /* the newest entry takes the "latest" flag from the static record */
  var dates = section.querySelectorAll('.entry-date');
  var lastStatic = dates.length ? dates[dates.length - 1] : null;
  if (lastStatic) lastStatic.textContent = lastStatic.textContent.replace(/\s*·\s*latest\s*$/, '');

  function render(text) {
    var p = document.createElement('p');
    var re = /\[([^\]]+)\]\(([^)]+)\)/g;
    var i = 0;
    var m;
    while ((m = re.exec(text))) {
      p.appendChild(document.createTextNode(text.slice(i, m.index)));
      var a = document.createElement('a');
      a.href = m[2];
      a.textContent = m[1];
      p.appendChild(a);
      i = m.index + m[0].length;
    }
    p.appendChild(document.createTextNode(text.slice(i)));
    return p;
  }

  for (var n = 0; n < count; n++) {
    var art = document.createElement('article');
    art.className = 'dispatch reveal lit';
    var date = document.createElement('p');
    date.className = 'entry-date';
    date.textContent = 'year ninety · entry 90-0' + (FIRST_NO + n) + (n === count - 1 ? ' · latest' : '');
    art.appendChild(date);
    art.appendChild(render(QUEUE[n]));
    section.appendChild(art);
  }
})();
