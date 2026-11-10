#!/usr/bin/env python3
"""Horde Hunt server: port 8908 beside the Orders of the Horde engine (8907).

  - tails WoWChatLog.txt for the addon's HUNT_DONE / HUNT_UNDO whispers (the proof)
  - reads Twitch chat anonymously for "!clue <answer>" (the solve)
  - pays solvers Desk Bucks through the Make It Back helper, retrying every 30 s
  - serves the case board overlay and the public slice florra.net can read

usage: python3 hunt_server.py [config.json]
"""
import json
import os
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hunt import Hunt  # noqa: E402

DEFAULTS = {
    "port": 8908,
    "guide": "hunt.json",
    "state": "hunt-state.json",
    "chat_log": "",            # .../WoW Forever/_classic_era_/Logs/WoWChatLog.txt
    "character": "",           # your character's name; leave blank to trust outgoing whispers only
    "twitch_channel": "makeitbackmax",
    "helper": "http://localhost:8765",
    "nights_root": "~/Documents/Florra Claude Work/Stream/WoW Forever/nights",
    "florra_export": "",       # optional path: writes florra-hunt.json on every change
    "cooldown_s": 5,
    "pay_every_s": 30,
}


def load_config(path):
    cfg = dict(DEFAULTS)
    if path and os.path.exists(path):
        with open(path) as f:
            cfg.update(json.load(f))
    for k in ("guide", "state", "chat_log", "nights_root", "florra_export"):
        if cfg[k]:
            p = os.path.expanduser(cfg[k])
            cfg[k] = p if os.path.isabs(p) else os.path.join(HERE, p)
    return cfg


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.hunt = Hunt(cfg["guide"], cfg["state"], character=cfg["character"] or None,
                         cooldown=cfg["cooldown_s"])
        self.watch = "no chat log configured" if not cfg["chat_log"] else "waiting for the chat log"
        self.twitch = "off" if not cfg["twitch_channel"] else "connecting"
        self.stop = threading.Event()

    def changed(self):
        if self.cfg["florra_export"]:
            tmp = self.cfg["florra_export"] + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.hunt.florra(), f)
            os.replace(tmp, self.cfg["florra_export"])

    # -- helper (Desk Bucks) --------------------------------------------------
    def send_bucks(self, e):
        q = urllib.parse.urlencode({"login": e["login"], "n": e["n"], "why": e["why"], "id": e["id"]})
        with urllib.request.urlopen(f"{self.cfg['helper']}/bucks/add?{q}", timeout=5) as r:
            body = r.read().decode(errors="replace").strip().lower()
        if r.status != 200:
            return False
        try:
            j = json.loads(body)
            return bool(j.get("ok")) if isinstance(j, dict) else False
        except ValueError:
            return body == "ok"

    def pay_loop(self):
        while not self.stop.wait(self.cfg["pay_every_s"]):
            self.hunt.pay(self.send_bucks)

    # -- chat log tail --------------------------------------------------------
    def tail_loop(self):
        path, f, ino, first = self.cfg["chat_log"], None, None, True
        if not path:
            return
        while not self.stop.is_set():
            try:
                st = os.stat(path)
                if f is None or st.st_ino != ino or st.st_size < f.tell():
                    if f:
                        f.close()
                    f = open(path, encoding="utf-8", errors="replace")
                    ino = st.st_ino
                    if first:
                        f.seek(0, 2)  # progress lives in the state file; don't replay old nights
                    first = False
                    self.watch = os.path.basename(path)
                for line in f.readlines():
                    r = self.hunt.feed(line)
                    if r and r.get("ok"):
                        self.changed()
            except FileNotFoundError:
                self.watch = "no WoW chat log yet: log in with the addon on, then /reload"
                first = False  # a log that appears later is read from its start
            except Exception as ex:  # keep tailing whatever happens
                self.watch = f"chat log error: {ex}"
            self.stop.wait(0.5)

    # -- Twitch chat (anonymous, read-only) -----------------------------------
    def chat_line(self, login, text):
        t = text.strip()
        if t.lower().startswith("!clue "):
            r = self.hunt.guess(login, t[6:])
            if r.get("ok"):
                self.changed()
            return r
        return None

    def twitch_loop(self):
        chan = self.cfg["twitch_channel"].lower().lstrip("#")
        if not chan:
            return
        wait = 2
        while not self.stop.is_set():
            try:
                s = socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=300)
                s.sendall(f"PASS SCHMOOPIIE\r\nNICK justinfan{int(time.time()) % 90000 + 10000}\r\nJOIN #{chan}\r\n".encode())
                self.twitch, wait, buf = f"reading #{chan}", 2, b""
                while not self.stop.is_set():
                    data = s.recv(4096)
                    if not data:
                        break
                    buf += data
                    while b"\r\n" in buf:
                        raw, buf = buf.split(b"\r\n", 1)
                        line = raw.decode(errors="replace")
                        if line.startswith("PING"):
                            s.sendall(b"PONG :tmi.twitch.tv\r\n")
                        elif " PRIVMSG " in line and line.startswith(":"):
                            login = line[1:].split("!", 1)[0]
                            text = line.split(" :", 1)[1] if " :" in line else ""
                            self.chat_line(login, text)
                s.close()
            except Exception as ex:
                self.twitch = f"twitch reconnecting ({ex.__class__.__name__})"
            self.stop.wait(wait)
            wait = min(wait * 2, 60)

    def start(self):
        for fn in (self.tail_loop, self.twitch_loop, self.pay_loop):
            threading.Thread(target=fn, daemon=True).start()


def handler(app):
    board = os.path.join(HERE, "hunt-board.html")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            b = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            h, p = app.hunt, u.path.rstrip("/")
            if p == "/hunt/state":
                st = h.state()
                st["watch"], st["twitch"] = app.watch, app.twitch
                return self.send(200, st)
            if p in ("/hunt/board", "/hunt"):
                with open(board, "rb") as f:
                    return self.send(200, f.read(), "text/html; charset=utf-8")
            if p == "/hunt/florra":
                return self.send(200, h.florra())
            if p == "/hunt/guess":   # same as a chat line "!clue <text>" from <login>
                r = h.guess(q.get("login", ""), q.get("text", ""))
            elif p == "/hunt/chat":  # inject a whole chat line
                r = app.chat_line(q.get("login", ""), q.get("text", "")) or {"ok": False, "why": "not a !clue line"}
            elif p == "/hunt/feed":  # inject a chat-log line
                r = h.feed(q.get("line", "")) or {"ok": False, "why": "not our HUNT line"}
            elif p == "/hunt/found":
                r = h.found(q.get("id", ""), "desk")
            elif p == "/hunt/undo":
                r = h.undo(q.get("id") or None, "desk")
            elif p == "/hunt/pay":
                r = h.pay(app.send_bucks)
            elif p == "/hunt/file":
                folder, rep = h.file_night(app.cfg["nights_root"])
                r = {"ok": True, "folder": folder, "report": rep}
            else:
                return self.send(404, {"ok": False, "why": "no such route"})
            if r.get("ok"):
                app.changed()
            return self.send(200, r)

    return H


def main(argv):
    cfg = load_config(argv[0] if argv else os.path.join(HERE, "config.json"))
    app = App(cfg)
    app.start()
    srv = ThreadingHTTPServer(("0.0.0.0", cfg["port"]), handler(app))
    print(f"horde hunt on :{cfg['port']}  board: http://localhost:{cfg['port']}/hunt/board")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop.set()


if __name__ == "__main__":
    main(sys.argv[1:])
