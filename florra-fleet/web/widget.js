/* the estate — front desk chat widget.
 *
 * Embed on any page (Shopify theme.liquid, before </body>):
 *   <script src="https://YOUR-DEPLOYED-HOST/widget.js"></script>
 * or self-host this file and set the endpoint explicitly:
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

  var css = [
    "#estate-desk{position:fixed;bottom:24px;right:24px;z-index:99999;font-family:Georgia,'IM Fell English',serif}",
    "#estate-bell{width:56px;height:56px;border-radius:50%;background:#141210;color:#E6E0D3;border:1px solid #4a443a;cursor:pointer;font-size:24px;line-height:1;box-shadow:0 4px 18px rgba(0,0,0,.5)}",
    "#estate-bell:hover{background:#1d1a16}",
    "#estate-panel{display:none;position:fixed;bottom:92px;right:24px;width:320px;max-width:92vw;height:420px;background:#141210;color:#E6E0D3;border:1px solid #4a443a;border-radius:6px;flex-direction:column;overflow:hidden;box-shadow:0 8px 30px rgba(0,0,0,.6)}",
    "#estate-head{padding:10px 14px;border-bottom:1px solid #2c2822;font-size:13px;letter-spacing:.08em}",
    "#estate-log{flex:1;overflow-y:auto;padding:12px;font-size:14px;line-height:1.5}",
    ".estate-msg{margin:0 0 10px;white-space:pre-wrap}",
    ".estate-msg.you{color:#a89f8d}",
    ".estate-msg.desk{color:#E6E0D3}",
    "#estate-form{display:flex;border-top:1px solid #2c2822}",
    "#estate-input{flex:1;background:#0e0c0a;color:#E6E0D3;border:0;padding:10px 12px;font:inherit;font-size:14px;outline:none}",
    "#estate-send{background:#0e0c0a;color:#a89f8d;border:0;border-left:1px solid #2c2822;padding:0 14px;cursor:pointer;font:inherit}",
    "#estate-send:hover{color:#E6E0D3}",
  ].join("");

  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  var root = document.createElement("div");
  root.id = "estate-desk";
  root.innerHTML =
    '<div id="estate-panel">' +
    '<div id="estate-head">the front desk · est. 1935 —</div>' +
    '<div id="estate-log"></div>' +
    '<form id="estate-form"><input id="estate-input" autocomplete="off" ' +
    'placeholder="ring the bell…" maxlength="500">' +
    '<button id="estate-send" type="submit">send</button></form></div>' +
    '<button id="estate-bell" title="the front desk">🕯️</button>';
  document.body.appendChild(root);

  var panel = document.getElementById("estate-panel");
  var log = document.getElementById("estate-log");
  var input = document.getElementById("estate-input");
  var opened = false;

  function say(text, who) {
    var p = document.createElement("p");
    p.className = "estate-msg " + who;
    p.textContent = (who === "you" ? "you — " : "") + text;
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
  }

  document.getElementById("estate-bell").addEventListener("click", function () {
    var open = panel.style.display === "flex";
    panel.style.display = open ? "none" : "flex";
    if (!open && !opened) {
      opened = true;
      say("evening. you've reached the front desk of the estate. ask about the lots, the lore, or the office — the file is open.", "desk");
    }
    if (!open) input.focus();
  });

  document.getElementById("estate-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    input.value = "";
    say(text, "you");
    fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, visitor: visitor }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) { say(d.reply || "the desk stepped away. try again shortly.", "desk"); })
      .catch(function () { say("the line to the office is down. try again shortly.", "desk"); });
  });
})();
