#!/usr/bin/env python3
"""Horde Hunt selftest. Plays a whole hunt in a temp folder: never touches the real
state file, the helper, OBS, Twitch or the WoW folder.

usage: python3 engine/selftest.py [--shot <png>]
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(PKG, "hunt"))

import compile as hc  # noqa: E402
import hunt as H  # noqa: E402
import hunt_server as S  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  -> {detail}"))


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


TEST_HUNT = """
hunt: Selftest Hunt
door: bounty-sounds
code: The Open Door
= c1 | Ash Mark
? riddle one
@ Durotar | 40 60 2
a burning tree | the ashen tree
b 100
w 1
s west from the ash
= c2 | Voice Mark
? riddle two
> Some Npc
a voice
b 150
w 2
= c3 | Hand Mark
? riddle three
! manual
w 1
"""


def main(argv):
    shot = argv[argv.index("--shot") + 1] if "--shot" in argv else None
    tmp = tempfile.mkdtemp(prefix="hordehunt-")
    try:
        run(tmp, shot)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} checks passed")
    return 1 if bad else 0


def run(tmp, shot):
    print("compile")
    try:
        hc.parse("hunt: x\n= a | t\n? r\n")
        check("rejects a clue with no verify line", False)
    except hc.HuntError as e:
        check("rejects a clue with no verify line", "exactly one verify" in str(e), e)
    try:
        hc.parse("hunt: x\n= a | t\n? r\n@ Durotar | 1 2\n= a | u\n? r\n! manual\n")
        check("rejects a clue with no answer and duplicate ids", False)
    except hc.HuntError as e:
        check("rejects a clue with no answer and duplicate ids", "duplicate" in str(e) and "needs an 'a'" in str(e), e)
    pkg = os.path.join(tmp, "pkg")
    src = os.path.join(tmp, "hunt.txt")
    open(src, "w").write(TEST_HUNT)
    check("compile exits clean", hc.main([src, "--out", pkg]) == 0)
    guide_path = os.path.join(pkg, "engine", "hunt.json")
    g = json.load(open(guide_path))
    lua = open(os.path.join(pkg, "addon", "HordeHunt", "HuntData.lua")).read()
    raw = json.dumps(g) + lua
    check("no plaintext answers or door code shipped", not any(w in raw.lower() for w in ("burning tree", "ashen", "open door")))
    check("lua data has every clue", all(f'id="{s}"' in lua for s in ("c1", "c2", "c3")))
    check("door hash matches pbkdf2 of the normalized code",
          g["door_hash"] == hc.door_hash(g["slug"], "open   DOOR!"))
    luac = shutil.which("luac5.1") or shutil.which("luac") or shutil.which("luac5.4")
    if luac:
        for f in ("HuntData.lua",):
            r = subprocess.run([luac, "-p", os.path.join(pkg, "addon", "HordeHunt", f)], capture_output=True)
            check(f"lua syntax: {f}", r.returncode == 0, r.stderr)
        r = subprocess.run([luac, "-p", os.path.join(PKG, "addon", "HordeHunt", "HordeHunt.lua")], capture_output=True)
        check("lua syntax: HordeHunt.lua", r.returncode == 0, r.stderr)
    else:
        print("  skip lua syntax (no luac on this machine)")

    print("solve + verify")
    clock = Clock(1762833600)  # 2025-11-11 04:00 UTC: 2025-11-10 20:00 PT
    state = os.path.join(tmp, "state.json")
    h = H.Hunt(guide_path, state, character="Grunt", cooldown=5, now=clock)
    check("first clue is active", h.active()["id"] == "c1")
    check("wrong guess", h.guess("viewer1", "wrong tree")["why"] == "wrong")
    clock.t += 1
    check("cooldown holds a spammer", h.guess("viewer1", "burning tree")["why"] == "cooldown")
    clock.t += 1
    r = h.guess("Viewer2", "  The BURNING tree!! ")
    check("normalized answer solves", r["ok"] and r["login"] == "viewer2", r)
    clock.t += 6
    check("second solver can't steal it", h.guess("viewer1", "burning tree")["why"] == "already solved")
    check("solve alone pays nothing", h.s["ledger"] == [])
    check("solving doesn't move the board", h.active()["id"] == "c1")

    check("viewer whisper ignored", h.feed("11/10 20:01:00.000  [Troll] whispers: HUNT_DONE c1 selftest-hunt") is None)
    check("smuggled outgoing text ignored",
          h.feed("11/10 20:01:00.000  [Troll] whispers: To Grunt: HUNT_DONE c1 selftest-hunt") is None)
    check("whisper to someone else ignored", h.feed("11/10 20:01:00.000  To Troll: HUNT_DONE c1 selftest-hunt") is None)
    check("other hunt's stamp ignored", h.feed("11/10 20:01:00.000  To Grunt: HUNT_DONE c1 other-hunt")["why"] == "other hunt")
    clock.t += 10
    r = h.feed("11/10 20:01:10.000  To Grunt-Forever: HUNT_DONE c1 selftest-hunt")
    check("own outgoing stamp verifies the find", r and r["ok"] and r["solver"] == "viewer2", r)
    check("self-whisper echo is a no-op", h.feed("11/10 20:01:10.000  [Grunt] whispers: HUNT_DONE c1 selftest-hunt")["why"] == "already found")
    check("verified find puts the solver in the ledger",
          [(e["login"], e["n"], e["status"]) for e in h.s["ledger"]] == [("viewer2", 100, "pending")])
    check("board moved on", h.active()["id"] == "c2")
    st = h.state()
    check("state hides sealed clues", st["cards"][2]["title"] is None and st["cards"][2]["riddle"] is None)
    check("state never carries answer hashes", "answers" not in json.dumps(st))
    check("heat rises with finds and guesses", 0 < st["heat"] <= 100, st["heat"])

    print("desk bucks")
    calls = []
    check("helper down keeps it pending", h.pay(lambda e: (_ for _ in ()).throw(OSError("down")))["pending"] == 1)
    r = h.pay(lambda e: calls.append(e["id"]) or True)
    check("helper up pays it", r["paid"] == 1 and h.bucks()["paid"] == 1, r)
    h.pay(lambda e: calls.append(e["id"]) or True)
    check("no double pay", calls == ["hunt:selftest-hunt:c1"], calls)

    print("undo")
    clock.t += 5
    h.guess("viewer3", "voice")
    clock.t += 5
    h.found("c2", "desk")
    check("unpaid entry exists for c2", any(e["id"].endswith(":c2") and e["status"] == "pending" for e in h.s["ledger"]))
    r = h.undo()
    check("undo voids the unpaid entry", r["ok"] and r["id"] == "c2" and
          [e["status"] for e in h.s["ledger"] if e["id"].endswith(":c2")] == ["void"])
    clock.t += 5
    h.found("c2", "game")
    check("re-find after undo pays once", [e["status"] for e in h.s["ledger"] if e["id"].endswith(":c2")] == ["pending"])
    check("undo of a paid find warns instead of clawing back", h.undo("c1")["note"] is not None)
    h.found("c1", "desk")
    check("manual clue has no chat answer", h.guess("viewer4", "anything")["why"] == "this clue has no chat answer")
    clock.t += 5
    h.found("c3", "game")
    st = h.state()
    check("door opens when every clue is found", st["door_open"] and st["active"] is None)
    check("florra slice is public-safe", set(h.florra()) == {"hunt", "door", "heat", "found", "total", "door_open", "solvers"})

    print("restart")
    h2 = H.Hunt(guide_path, state, character="Grunt", now=clock)
    check("progress survives a restart", len(h2.s["found"]) == 3 and h2.s["solved"]["c1"]["login"] == "viewer2")
    g2 = dict(g, slug="another-hunt")
    gp2 = os.path.join(tmp, "hunt2.json")
    json.dump(g2, open(gp2, "w"))
    h3 = H.Hunt(gp2, state, now=clock)
    check("a new hunt starts clean and backs up the old one",
          h3.s["found"] == {} and os.path.exists(state + ".bak-selftest-hunt"))

    print("filing")
    h = H.Hunt(guide_path, os.path.join(tmp, "s2.json"), character="Grunt", now=clock)
    h.guess("viewer2", "ashen tree")
    clock.t += 30
    h.found("c1", "game")
    nights = os.path.join(tmp, "nights")
    folder, rep = h.file_night(nights)
    check("files into today's PT folder", os.path.basename(folder) == "2025-11-10", folder)
    for f in ("hunt-report.json", "hunt-specs.md", "hunt-bounty-brief-DRAFT.md"):
        check(f"wrote {f}", os.path.exists(os.path.join(folder, f)))
    specs = open(os.path.join(folder, "hunt-specs.md")).read()
    check("find ranks first in clip specs", specs.index("CLIP H01") < specs.index("verified in game") < specs.index("CLIP H02"))
    check("specs use wall-clock PT", "20:00:" in specs, specs[:400])
    brief = open(os.path.join(folder, "hunt-bounty-brief-DRAFT.md")).read()
    check("brief leaves the money blank", "Purse: $____" in brief and "DRAFT" in brief)
    check("report numbers match", rep["found"] == 1 and rep["solved"] == 1 and rep["solvers"] == ["viewer2"] and rep["moments"] == 2, rep)
    os.makedirs(os.path.join(nights, "2025-11-10-2"))
    folder2, _ = h.file_night(nights)
    check("second stream files into the -2 folder", folder2.endswith("2025-11-10-2"))

    print("server")
    serve_test(tmp, pkg, guide_path, shot)


def serve_test(tmp, pkg, guide_path, shot):
    paid = []

    class Helper(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            paid.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

    hs = ThreadingHTTPServer(("127.0.0.1", 0), Helper)
    threading.Thread(target=hs.serve_forever, daemon=True).start()
    chat = os.path.join(tmp, "WoWChatLog.txt")
    open(chat, "w").write("11/10 19:00:00.000  To Grunt: HUNT_DONE c1 selftest-hunt\n")  # old night: must not replay
    cfg = dict(S.DEFAULTS, port=0, guide=guide_path, state=os.path.join(tmp, "srv-state.json"), chat_log=chat,
               character="Grunt", twitch_channel="", helper=f"http://127.0.0.1:{hs.server_port}",
               nights_root=os.path.join(tmp, "srv-nights"), florra_export=os.path.join(tmp, "florra-hunt.json"),
               cooldown_s=0, pay_every_s=0.3)
    app = S.App(cfg)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), S.handler(app))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    app.start()
    base = f"http://127.0.0.1:{srv.server_port}"

    def get(p):
        with urllib.request.urlopen(base + p, timeout=5) as r:
            return json.loads(r.read())

    time.sleep(0.8)
    check("tail skips the old night", get("/hunt/state")["found"] == 0)
    r = get("/hunt/chat?login=Viewer9&text=" + urllib.request.quote("!clue burning tree"))
    check("!clue from chat solves", r.get("ok"), r)
    with open(chat, "a") as f:
        f.write("11/10 20:05:00.000  To Grunt: HUNT_DONE c1 selftest-hunt\n")
    for _ in range(30):
        if get("/hunt/state")["found"] == 1:
            break
        time.sleep(0.1)
    check("chat log line verifies through the tail", get("/hunt/state")["found"] == 1)
    for _ in range(40):
        if paid:
            break
        time.sleep(0.1)
    check("helper got /bucks/add with the entry id", paid and "/bucks/add?" in paid[0] and "id=hunt%3Aselftest-hunt%3Ac1" in paid[0], paid)
    check("florra export written", json.load(open(cfg["florra_export"]))["found"] == 1)
    check("desk found + undo", get("/hunt/found?id=c2")["ok"] and get("/hunt/undo")["id"] == "c2")
    check("unknown route 404s", _status(base + "/hunt/nope") == 404)
    r = get("/hunt/file")
    check("file route writes the night", os.path.exists(os.path.join(r["folder"], "hunt-report.json")))
    st = get("/hunt/state")
    check("state reports the watched log", st["watch"] == "WoWChatLog.txt", st["watch"])
    render_test(base, shot)
    app.stop.set()
    srv.shutdown()
    hs.shutdown()


def _status(url):
    try:
        urllib.request.urlopen(url, timeout=5)
        return 200
    except urllib.error.HTTPError as e:
        return e.code


RENDER_JS = r"""
const {chromium}=require('playwright');
(async()=>{
  const b=await chromium.launch();const out={errors:[]};
  for(const mini of [0,1]){
    const p=await b.newPage({viewport:mini?{width:620,height:210}:{width:1920,height:1080}});
    p.on('pageerror',e=>out.errors.push(String(e)));
    p.on('console',m=>{if(m.type()==='error'&&!/fonts\.g/.test((m.location()||{}).url||''))out.errors.push(m.text())});
    await p.route(/fonts\.(googleapis|gstatic)\.com/,r=>r.abort());
    await p.goto(process.argv[2]+(mini?'?mini=1':''));
    await p.waitForSelector('body[data-ready="1"]',{timeout:8000});
    await p.waitForTimeout(400);
    const r=await p.evaluate(()=>({cards:document.querySelectorAll('.card').length,
      strings:document.querySelectorAll('#strings path').length,
      active:!!document.querySelector('.card.active'),found:document.querySelectorAll('.card.found').length,
      stamps:document.querySelectorAll('.stamp').length,heat:document.getElementById('deg').textContent}));
    out[mini?'mini':'full']=r;
    if(!mini&&process.argv[3])await p.screenshot({path:process.argv[3]});
  }
  console.log(JSON.stringify(out));await b.close();
})().catch(e=>{console.log(JSON.stringify({fatal:String(e)}));process.exit(0)});
"""


def render_test(base, shot):
    node = shutil.which("node")
    if not node or subprocess.run([node, "-e", "require('playwright')"], capture_output=True).returncode:
        print("  skip board render (no node playwright on this machine)")
        return
    js = os.path.join(tempfile.mkdtemp(), "render.js")
    open(js, "w").write(RENDER_JS)
    r = subprocess.run([node, js, base + "/hunt/board"] + ([shot] if shot else []),
                       capture_output=True, text=True, timeout=60)
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        check("board renders", False, r.stdout + r.stderr)
        return
    if "fatal" in out:
        check("board renders", False, out["fatal"])
        return
    f, m = out["full"], out["mini"]
    check("board renders every card", f["cards"] == 3, f)
    check("red string drawn from the found card", f["strings"] == 1, f)
    check("active card highlighted", f["active"] and f["found"] == 1, f)
    check("stamps show (solved + found)", f["stamps"] == 2, f)
    check("mini strip renders", m["active"], m)
    check("no page errors", not out["errors"], out["errors"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
