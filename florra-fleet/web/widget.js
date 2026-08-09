/* Hallmark · component: chat-widget · genre: editorial · theme: Bandersnatch (house brand)
 * states: default · hover · focus · active · disabled · loading · error · success
 * contrast: pass · pre-emit critique: P5 H4 E5 S4 R5 V5
 *
 * the estate — front desk chat widget.
 *
 * Embed on any page (Shopify theme.liquid, before </body>):
 *   <script src="https://YOUR-DEPLOYED-HOST/widget.js"></script>
 * or self-host and set the endpoint explicitly:
 *   <script>window.ESTATE_CHAT_URL = "https://YOUR-DEPLOYED-HOST/chat";</script>
 *   <script src=".../widget.js"></script>
 */
(function () {
  var script = document.currentScript;
  var ENDPOINT =
    window.ESTATE_CHAT_URL ||
    (script && script.src ? script.src.replace(/\/widget\.js.*$/, "/chat") : "/chat");

  var visitor = localStorage.getItem("estate_visitor");
  if (!visitor) {
    visitor = "v-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("estate_visitor", visitor);
  }

  // progressive enhancement: the estate faces, if the host CSP allows them.
  // everything degrades to Georgia + system mono when blocked.
  if (!document.getElementById("estate-fonts")) {
    var link = document.createElement("link");
    link.id = "estate-fonts";
    link.rel = "stylesheet";
    link.href =
      "https://fonts.googleapis.com/css2?family=IM+Fell+English:ital@0;1" +
      "&family=IBM+Plex+Mono:wght@400;500&display=swap";
    document.head.appendChild(link);
  }

  // tokens are scoped to #estate-desk so nothing leaks into the host theme.
  var css = [
    "#estate-desk{",
    "  --est-bg:#141210; --est-surface:#1b1815; --est-ink:#E6E0D3;",
    "  --est-ink-soft:#a89f8d; --est-rule:#2c2822;",
    "  --est-oxblood:#6E1F1F; --est-seal-lit:#a24a41;",
    "  --est-ease:cubic-bezier(0.16,1,0.3,1); --est-dur:220ms;",
    "  --est-fell:'IM Fell English',Georgia,serif;",
    "  --est-mono:'IBM Plex Mono',ui-monospace,'SFMono-Regular',Menlo,monospace;",
    "  position:fixed; bottom:24px; right:24px; z-index:99999;",
    "}",

    /* the wax seal — one per view, the only stamp */
    "#estate-seal{",
    "  width:60px; height:60px; padding:0; cursor:pointer; position:relative;",
    "  border-radius:50%; border:1px solid var(--est-seal-lit);",
    "  background:radial-gradient(circle at 38% 34%, #8a2a24 0%, #6e1f1f 46%, #571818 100%);",
    "  box-shadow:0 3px 14px rgba(0,0,0,.55), inset 0 1px 2px rgba(255,220,200,.22),",
    "    inset 0 -3px 6px rgba(0,0,0,.5);",
    "  color:#f0e5db; font-family:var(--est-fell); font-size:26px; line-height:1;",
    "  transition:transform var(--est-dur) var(--est-ease), filter var(--est-dur) var(--est-ease);",
    "}",
    "#estate-seal span{ display:block; text-shadow:0 1px 0 rgba(0,0,0,.5), 0 -1px 0 rgba(255,210,190,.25); transform:translateY(-1px); }",
    "#estate-seal::after{ content:''; position:absolute; inset:5px; border-radius:50%; border:1px solid rgba(0,0,0,.28); pointer-events:none; }",
    "#estate-seal:hover{ filter:brightness(1.08); transform:translateY(-1px); }",
    "#estate-seal:active{ transform:translateY(1px); filter:brightness(.96); }",
    "#estate-seal:focus-visible{ outline:2px solid var(--est-seal-lit); outline-offset:3px; }",

    /* the filing card */
    "#estate-panel{",
    "  display:none; position:fixed; bottom:96px; right:24px;",
    "  width:342px; max-width:92vw; height:452px; max-height:76vh;",
    "  flex-direction:column; overflow:hidden; background:var(--est-bg);",
    "  color:var(--est-ink); border:1px solid var(--est-rule); border-radius:2px;",
    "  box-shadow:0 10px 34px rgba(0,0,0,.62);",
    "  opacity:0; transform:translateY(8px);",
    "  transition:opacity var(--est-dur) var(--est-ease), transform var(--est-dur) var(--est-ease);",
    "}",
    "#estate-panel.is-open{ display:flex; }",
    "#estate-panel.is-shown{ opacity:1; transform:translateY(0); }",

    /* masthead reads like a caption card */
    "#estate-head{ padding:13px 15px 11px; border-bottom:1px solid var(--est-oxblood); position:relative; }",
    "#estate-head b{ display:block; font-family:var(--est-fell); font-weight:400;",
    "  font-size:17px; letter-spacing:.02em; color:var(--est-ink); }",
    "#estate-head small{ display:block; margin-top:3px; font-family:var(--est-mono);",
    "  font-size:10.5px; letter-spacing:.06em; color:var(--est-ink-soft); text-transform:lowercase; }",
    "#estate-close{ position:absolute; top:10px; right:11px; width:26px; height:26px;",
    "  background:transparent; border:0; cursor:pointer; color:var(--est-ink-soft);",
    "  font-family:var(--est-mono); font-size:15px; line-height:1; border-radius:2px;",
    "  transition:color var(--est-dur) var(--est-ease); }",
    "#estate-close:hover{ color:var(--est-ink); }",
    "#estate-close:focus-visible{ outline:2px solid var(--est-seal-lit); outline-offset:2px; }",

    /* the transcript */
    "#estate-log{ flex:1; overflow-y:auto; padding:14px 15px 4px; }",
    "#estate-log::-webkit-scrollbar{ width:8px; }",
    "#estate-log::-webkit-scrollbar-thumb{ background:var(--est-rule); border-radius:8px; }",
    ".estate-turn{ margin:0 0 13px; }",
    ".estate-who{ display:block; font-family:var(--est-mono); font-size:9.5px;",
    "  letter-spacing:.09em; text-transform:uppercase; margin-bottom:3px; }",
    ".estate-body{ font-family:var(--est-fell); font-size:15px; line-height:1.5; white-space:pre-wrap; }",
    ".estate-turn.desk .estate-who{ color:var(--est-seal-lit); }",
    ".estate-turn.desk .estate-body{ color:var(--est-ink); border-left:2px solid var(--est-oxblood); padding-left:10px; }",
    ".estate-turn.you .estate-who{ color:var(--est-ink-soft); }",
    ".estate-turn.you .estate-body{ color:var(--est-ink-soft); padding-left:10px; }",
    ".estate-turn.error .estate-body{ color:var(--est-seal-lit); border-left-color:var(--est-seal-lit); }",

    /* the writing state — a mono line, not chatbot dots */
    "#estate-typing{ font-family:var(--est-mono); font-size:11px; letter-spacing:.06em;",
    "  color:var(--est-ink-soft); padding:0 15px 12px; display:none; }",
    "#estate-typing.on{ display:block; }",
    "#estate-typing i{ font-style:normal; animation:estate-blink 1.4s var(--est-ease) infinite; }",
    "@keyframes estate-blink{ 0%,100%{opacity:.25} 50%{opacity:1} }",

    /* the counter form — a ruled line, not a box */
    "#estate-form{ display:flex; align-items:stretch; border-top:1px solid var(--est-rule); }",
    "#estate-input{ flex:1; min-width:0; background:transparent; color:var(--est-ink);",
    "  border:0; border-bottom:1px solid transparent; margin:0; padding:13px 4px 13px 15px;",
    "  font-family:var(--est-mono); font-size:13px; outline:none;",
    "  transition:border-color var(--est-dur) var(--est-ease); }",
    "#estate-input::placeholder{ color:var(--est-ink-soft); }",
    "#estate-input:hover{ border-bottom-color:var(--est-rule); }",
    "#estate-input:focus-visible{ border-bottom-color:var(--est-seal-lit); }",
    "#estate-form.err #estate-input{ border-bottom-color:var(--est-seal-lit); }",
    "#estate-send{ background:transparent; border:0; border-left:1px solid var(--est-rule);",
    "  cursor:pointer; padding:0 16px; color:var(--est-ink-soft);",
    "  font-family:var(--est-mono); font-size:12px; letter-spacing:.05em;",
    "  transition:color var(--est-dur) var(--est-ease); }",
    "#estate-send:hover:not(:disabled){ color:var(--est-ink); }",
    "#estate-send:active:not(:disabled){ color:var(--est-seal-lit); }",
    "#estate-send:focus-visible{ outline:2px solid var(--est-seal-lit); outline-offset:-2px; }",
    "#estate-send:disabled{ color:var(--est-rule); cursor:default; }",

    "@media (prefers-reduced-motion: reduce){",
    "  #estate-panel,#estate-seal,#estate-close,#estate-send,#estate-input{ transition-duration:120ms; }",
    "  #estate-seal:hover,#estate-seal:active{ transform:none; }",
    "  #estate-typing i{ animation:none; opacity:.7; }",
    "}",
  ].join("");

  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  var root = document.createElement("div");
  root.id = "estate-desk";
  root.innerHTML =
    '<div id="estate-panel" role="dialog" aria-label="the front desk of the estate" aria-modal="false">' +
    '<div id="estate-head"><b>the front desk</b><small>region e · the estate · 1935 —</small>' +
    '<button id="estate-close" type="button" aria-label="close the front desk">&#215;</button></div>' +
    '<div id="estate-log" aria-live="polite"></div>' +
    '<div id="estate-typing" aria-hidden="true">the desk is writing<i>…</i></div>' +
    '<form id="estate-form">' +
    '<input id="estate-input" autocomplete="off" aria-label="your message" ' +
    'placeholder="state your business…" maxlength="500">' +
    '<button id="estate-send" type="submit">send</button></form></div>' +
    '<button id="estate-seal" type="button" aria-label="open the front desk" aria-expanded="false">' +
    '<span aria-hidden="true">B</span></button>';
  document.body.appendChild(root);

  var seal = document.getElementById("estate-seal");
  var panel = document.getElementById("estate-panel");
  var log = document.getElementById("estate-log");
  var input = document.getElementById("estate-input");
  var send = document.getElementById("estate-send");
  var form = document.getElementById("estate-form");
  var typing = document.getElementById("estate-typing");
  var closeBtn = document.getElementById("estate-close");
  var greeted = false;
  var busy = false;

  function say(text, who) {
    var turn = document.createElement("div");
    turn.className = "estate-turn " + who;
    var label = document.createElement("span");
    label.className = "estate-who";
    label.textContent = who === "you" ? "you" : who === "error" ? "the office" : "the desk";
    var body = document.createElement("div");
    body.className = "estate-body";
    body.textContent = text;
    turn.appendChild(label);
    turn.appendChild(body);
    log.appendChild(turn);
    log.scrollTop = log.scrollHeight;
  }

  function setBusy(on) {
    busy = on;
    input.disabled = on;
    typing.classList.toggle("on", on);
    updateSend();
  }

  function updateSend() {
    send.disabled = busy || input.value.trim() === "";
  }

  function openPanel() {
    panel.classList.add("is-open");
    seal.setAttribute("aria-expanded", "true");
    // next frame so the display:flex lands before the opacity/transform transition
    requestAnimationFrame(function () { panel.classList.add("is-shown"); });
    if (!greeted) {
      greeted = true;
      say(
        "evening. you've reached the front desk of the estate. ask about the lots, the lore, or the office — the file is open.",
        "desk"
      );
    }
    setTimeout(function () { input.focus(); }, 60);
  }

  function closePanel() {
    panel.classList.remove("is-shown");
    seal.setAttribute("aria-expanded", "false");
    setTimeout(function () { panel.classList.remove("is-open"); }, 220);
    seal.focus();
  }

  seal.addEventListener("click", function () {
    if (panel.classList.contains("is-open")) closePanel();
    else openPanel();
  });
  closeBtn.addEventListener("click", closePanel);
  input.addEventListener("input", function () {
    form.classList.remove("err");
    updateSend();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && panel.classList.contains("is-open")) closePanel();
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || busy) return;
    input.value = "";
    say(text, "you");
    setBusy(true);
    fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, visitor: visitor }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        setBusy(false);
        say(d.reply || "the desk stepped away. try again shortly.", "desk");
        input.focus();
      })
      .catch(function () {
        setBusy(false);
        form.classList.add("err");
        say("the line to the office is down. try again shortly.", "error");
        input.focus();
      });
  });

  updateSend();
})();
