"""Horde Hunt engine core: clues, chat guesses, in-game verification, Desk Bucks ledger, night filing.

Pure logic, no network. hunt_server.py wraps it with HTTP, the chat-log tail and Twitch chat.

The rule the whole thing hangs on: don't pay for clues, pay for proof.
  - a viewer solves a clue in chat (!clue <answer>), and that only *names* them
  - the game verifies the find (the addon's HUNT_DONE line in the chat log)
  - only then does the solver's payout enter the ledger
"""
import datetime
import hashlib
import json
import os
import re
import secrets
import threading
import time
import unicodedata

try:
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    PT = None

GUESS_WINDOW = 300  # seconds of chat guesses that count toward heat

# Reward codes, redeemed at bountysounds.com/redeem. Mirrors the site's
# src/lib/hunt-code.ts exactly (shared test vector in both test suites).
CODE_ALPHA = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32: no I L O U
CODE_SALT = "florra-hunt-redeem\n"


def mint_code():
    c = "".join(secrets.choice(CODE_ALPHA) for _ in range(10))
    return f"HUNT-{c[:5]}-{c[5:]}"


def norm_code(s):
    s = re.sub(r"[^0-9A-Z]", "", (s or "").upper().replace("O", "0").replace("I", "1").replace("L", "1"))
    return s[4:] if s.startswith("HUNT") else s


def code_hash(code):
    return hashlib.sha256((CODE_SALT + norm_code(code)).encode()).hexdigest()


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"^the ", "", s)


def answer_hash(salt, s):
    return hashlib.sha256((salt + "\n" + norm(s)).encode()).hexdigest()


def bare(name):
    """Grunt-Realm -> grunt"""
    return (name or "").split("-")[0].strip().lower()


def pt(ts):
    d = datetime.datetime.fromtimestamp(ts, PT) if PT else datetime.datetime.fromtimestamp(ts)
    return d


LINK_RE = re.compile(r"\|Hplayer:[^|]*\|h\[([^\]]*)\]\|h")  # |Hplayer:Grunt|h[Grunt]|h -> Grunt
# anchored to the start of the line (after WoW's timestamp) so a viewer can't smuggle
# "To Grunt: HUNT_DONE" inside the text of their own whisper
TS = r"^\s*(?:\d+/\d+(?:/\d+)? [\d:.]+\s+)?"
OUT_RE = re.compile(TS + r"To \[?([^:\]\s]+)\]?: HUNT_(DONE|UNDO) (\w+)(?: (\S+))?")
IN_RE = re.compile(TS + r"\[?([^\]\s]+)\]? whispers: HUNT_(DONE|UNDO) (\w+)(?: (\S+))?")


class Hunt:
    def __init__(self, guide_path, state_path, character=None, cooldown=5, now=time.time):
        with open(guide_path, encoding="utf-8") as f:
            self.g = json.load(f)
        self.slug = self.g["slug"]
        self.steps = self.g["steps"]
        self.by_id = {s["id"]: s for s in self.steps}
        self.state_path = state_path
        self.character = bare(character) if character else None
        self.cooldown = cooldown
        self.now = now
        self.lock = threading.RLock()
        self.s = self._load()

    # -- state -------------------------------------------------------------
    def _fresh(self):
        return {"hunt": self.slug, "solved": {}, "found": {}, "order": [], "ledger": [], "rewards": {},
                "moments": [], "guesses": [], "cool": {}, "history": [], "started": self.now()}

    def _load(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                s = json.load(f)
        except FileNotFoundError:
            return self._fresh()
        if s.get("hunt") != self.slug:
            # a different hunt: keep the old progress beside it, start clean
            os.replace(self.state_path, f"{self.state_path}.bak-{s.get('hunt', 'old')}")
            return self._fresh()
        s.setdefault("rewards", {})
        return s

    def save(self):
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.s, f, indent=1)
        os.replace(tmp, self.state_path)

    def _log(self, what, **kw):
        self.s["history"].append(dict(at=self.now(), what=what, **kw))
        self.s["history"] = self.s["history"][-200:]

    def active(self):
        for st in self.steps:
            if st["id"] not in self.s["found"]:
                return st
        return None

    # -- chat guesses --------------------------------------------------------
    def guess(self, login, text):
        with self.lock:
            at = self.now()
            login = (login or "").lower().strip()
            st = self.active()
            if not login:
                return {"ok": False, "why": "no login"}
            if not st:
                return {"ok": False, "why": "hunt over"}
            if at - self.s["cool"].get(login, 0) < self.cooldown:
                return {"ok": False, "why": "cooldown"}
            self.s["cool"][login] = at
            self.s["guesses"] = [t for t in self.s["guesses"] if at - t < GUESS_WINDOW] + [at]
            if st["id"] in self.s["solved"]:
                return {"ok": False, "why": "already solved", "by": self.s["solved"][st["id"]]["login"]}
            if not st["answers"]:
                return {"ok": False, "why": "this clue has no chat answer"}
            if answer_hash(self.slug, text) not in st["answers"]:
                return {"ok": False, "why": "wrong"}
            self.s["solved"][st["id"]] = {"login": login, "at": at}
            self.s["moments"].append({"kind": "solve", "id": st["id"], "at": at, "login": login})
            self._log("solve", id=st["id"], login=login)
            self.save()
            return {"ok": True, "id": st["id"], "title": st["title"], "login": login}

    # -- the game's word ------------------------------------------------------
    def feed(self, line):
        """A chat-log line. Only our own outgoing whisper counts as proof."""
        line = LINK_RE.sub(r"\1", line)
        m = OUT_RE.search(line)
        if m:
            if self.character and bare(m.group(1)) != self.character:
                return None  # Max whispering someone else the magic words
        else:
            m = IN_RE.search(line)
            if not m or not self.character or bare(m.group(1)) != self.character:
                return None  # anyone else whispering HUNT_DONE is ignored
        kind, sid, slug = m.group(2), m.group(3), m.group(4)
        if slug and slug != self.slug:
            return {"ok": False, "why": "other hunt"}
        return self.found(sid, "game") if kind == "DONE" else self.undo(sid, "game")

    def found(self, sid, src="desk"):
        with self.lock:
            st = self.by_id.get(sid)
            if not st:
                return {"ok": False, "why": "unknown clue"}
            if sid in self.s["found"]:
                return {"ok": False, "why": "already found"}
            at = self.now()
            self.s["found"][sid] = {"at": at, "src": src}
            self.s["order"].append(sid)
            solver = self.s["solved"].get(sid)
            if solver and st["bucks"] > 0:
                eid = f"hunt:{self.slug}:{sid}"
                if not any(e["id"] == eid and e["status"] != "void" for e in self.s["ledger"]):
                    self.s["ledger"] = [e for e in self.s["ledger"] if e["id"] != eid]
                    self.s["ledger"].append({"id": eid, "login": solver["login"], "n": st["bucks"],
                                             "why": f"hunt: solved {st['title']}", "status": "pending",
                                             "at": at})
            if solver:
                self._mint(sid, solver["login"], at)
            self.s["moments"].append({"kind": "find", "id": sid, "at": at, "src": src,
                                      "login": solver["login"] if solver else None})
            self._log("found", id=sid, src=src)
            self.save()
            return {"ok": True, "id": sid, "title": st["title"], "solver": solver["login"] if solver else None}

    def undo(self, sid=None, src="desk"):
        with self.lock:
            if not sid:
                sid = self.s["order"][-1] if self.s["order"] else None
            if not sid or sid not in self.s["found"]:
                return {"ok": False, "why": "nothing to undo"}
            del self.s["found"][sid]
            self.s["order"] = [x for x in self.s["order"] if x != sid]
            note = None
            for e in self.s["ledger"]:
                if e["id"] == f"hunt:{self.slug}:{sid}":
                    if e["status"] == "pending":
                        e["status"] = "void"
                    elif e["status"] == "paid":
                        note = "already paid; take it back by hand on the helper if it was wrong"
            rw = self.s["rewards"].get(f"hunt:{self.slug}:{sid}")
            if rw and rw["status"] in ("pending_issue", "issued"):
                rw["status"] = "pending_void"  # the site voids it unless someone already redeemed
            for mo in self.s["moments"]:
                if mo["kind"] == "find" and mo["id"] == sid and not mo.get("undone"):
                    mo["undone"] = True
            self._log("undo", id=sid, src=src)
            self.save()
            return {"ok": True, "id": sid, "note": note}

    # -- Bounty Sounds reward codes ------------------------------------------
    def _mint(self, sid, login, at):
        key = f"hunt:{self.slug}:{sid}"
        rw = self.s["rewards"].get(key)
        if rw and rw["status"] in ("pending_issue", "issued", "redeemed_on_site"):
            return rw
        if rw and rw["status"] == "pending_void":
            rw["status"] = "issued"  # undo then re-find before the void went out: same code stands
            return rw
        code = mint_code()  # first find, or a re-find after a void: fresh code
        rw = {"key": key, "clue": sid, "title": self.by_id[sid]["title"], "login": login,
              "code": code, "hash": code_hash(code), "status": "pending_issue", "at": at}
        self.s["rewards"][key] = rw
        return rw

    def sync_rewards(self, sender):
        """sender(payload) -> the bridge's JSON reply, or None on failure. Retries are safe:
        the bridge is idempotent on rewardKey."""
        with self.lock:
            todo = [dict(r) for r in self.s["rewards"].values() if r["status"] in ("pending_issue", "pending_void")]
        done = 0
        for r in todo:
            if r["status"] == "pending_issue":
                payload = {"action": "issue", "rewardKey": r["key"], "huntSlug": self.slug,
                           "huntName": self.g["name"], "clueTitle": r["title"],
                           "twitchLogin": r["login"], "codeHash": r["hash"]}
            else:
                payload = {"action": "void", "rewardKey": r["key"]}
            try:
                reply = sender(payload)
            except Exception:
                reply = None
            if not reply:
                continue
            with self.lock:
                cur = self.s["rewards"][r["key"]]
                if cur["status"] != r["status"]:
                    continue  # changed under us (undo/re-find); next pass sends the new intent
                if r["status"] == "pending_issue":
                    cur["status"] = "issued"
                elif reply.get("status") in ("redeemed", "approved", "paid"):
                    cur["status"] = "redeemed_on_site"  # too late to void here: Max decides on the admin desk
                else:
                    cur["status"] = "void"
                done += 1
        if done:
            with self.lock:
                self.save()
        return {"synced": done, "waiting": len(todo) - done}

    def rewards(self):
        """For Max's desk only: holds the codes. Never on the board, never on florra.net."""
        with self.lock:
            return [dict(r) for r in self.s["rewards"].values()]

    # -- Desk Bucks -----------------------------------------------------------
    def pay(self, sender):
        """sender(entry) -> True once the helper says ok. Safe to call over and over."""
        with self.lock:
            todo = [e for e in self.s["ledger"] if e["status"] == "pending"]
        paid = 0
        for e in todo:
            try:
                ok = sender(e)
            except Exception:
                ok = False
            if ok:
                with self.lock:
                    e["status"], e["paid_at"] = "paid", self.now()
                    paid += 1
        if paid:
            with self.lock:
                self.save()
        return {"paid": paid, "pending": len(todo) - paid}

    def bucks(self):
        c = {"paid": 0, "pending": 0, "void": 0, "credited": 0}
        for e in self.s["ledger"]:
            c[e["status"]] += 1
            if e["status"] == "paid":
                c["credited"] += e["n"]
        return c

    # -- what the board reads ---------------------------------------------------
    def heat(self):
        at = self.now()
        n = len(self.steps)
        recent = len([t for t in self.s["guesses"] if at - t < GUESS_WINDOW])
        return min(100, round(70 * len(self.s["found"]) / n + 30 * min(1.0, recent / 30)))

    def state(self):
        with self.lock:
            act = self.active()
            cards = []
            for st in self.steps:
                sid = st["id"]
                f, sv = self.s["found"].get(sid), self.s["solved"].get(sid)
                status = "found" if f else ("active" if act and act["id"] == sid else "sealed")
                cards.append({
                    "id": sid, "n": st["n"], "status": status,
                    "title": st["title"] if status != "sealed" else None,
                    "riddle": st["riddle"] if status != "sealed" else None,
                    "solver": sv["login"] if sv else None,
                    "string": st["string"] if f else None,
                    "manual": st["verify"]["kind"] == "manual",
                })
            return {"hunt": self.g["name"], "slug": self.slug, "door": self.g.get("door"),
                    "total": len(self.steps), "found": len(self.s["found"]),
                    "solved": len(self.s["solved"]), "heat": self.heat(),
                    "active": next((c for c in cards if c["status"] == "active"), None),
                    "cards": cards, "door_open": act is None, "bucks": self.bucks(),
                    "last": self.s["history"][-1] if self.s["history"] else None}

    def florra(self):
        """The public slice florra.net may read: no riddles for sealed clues, no answers, ever."""
        st = self.state()
        return {"hunt": st["hunt"], "door": st["door"], "heat": st["heat"], "found": st["found"],
                "total": st["total"], "door_open": st["door_open"],
                "solvers": [c["solver"] for c in st["cards"] if c["status"] == "found" and c["solver"]]}

    # -- filing the night ---------------------------------------------------------
    def night_folder(self, root):
        day = pt(self.now()).strftime("%Y-%m-%d")
        found = [os.path.join(root, day)] if os.path.isdir(os.path.join(root, day)) else []
        k = 2
        while os.path.isdir(os.path.join(root, f"{day}-{k}")):
            found.append(os.path.join(root, f"{day}-{k}"))
            k += 1
        folder = found[-1] if found else os.path.join(root, day)
        os.makedirs(folder, exist_ok=True)
        return folder

    def file_night(self, root):
        with self.lock:
            folder = self.night_folder(root)
            st = self.state()
            live = [m for m in self.s["moments"] if not m.get("undone")]
            finds = [m for m in live if m["kind"] == "find"]
            solves = [m for m in live if m["kind"] == "solve"]
            report = {"hunt": st["hunt"], "slug": self.slug, "night": os.path.basename(folder),
                      "found": st["found"], "total": st["total"], "solved": st["solved"],
                      "door_open": st["door_open"], "heat": st["heat"],
                      "solvers": sorted({m["login"] for m in solves}),
                      "moments": len(finds) + len(solves), "bucks": st["bucks"],
                      "rewards": self._reward_counts(),
                      "filed_at": self.now()}
            with open(os.path.join(folder, "hunt-report.json"), "w") as f:
                json.dump(report, f, indent=1)
            with open(os.path.join(folder, "hunt-specs.md"), "w") as f:
                f.write(self._specs(finds, solves))
            with open(os.path.join(folder, "hunt-bounty-brief-DRAFT.md"), "w") as f:
                f.write(self._brief(st, report))
            self._log("filed", folder=folder)
            self.save()
            return folder, report

    def _reward_counts(self):
        c = {}
        for r in self.s["rewards"].values():
            c[r["status"]] = c.get(r["status"], 0) + 1
        return c

    def _specs(self, finds, solves):
        total = len(self.steps)
        out = [f"# Horde Hunt clip specs: {self.g['name']}",
               "Times are wall clock PT from the engine. Line them up against the VOD before cutting.",
               "Finds rank first: the card pinning to the board is the payoff.", ""]
        k = 1
        for m in finds + solves:
            st = self.by_id[m["id"]]
            t = pt(m["at"])
            if m["kind"] == "find":
                a, b = t - datetime.timedelta(seconds=25), t + datetime.timedelta(seconds=20)
                who = f"@{m['login']} called it in chat" if m["login"] else "nobody in chat cracked it"
                hook = (f"\"@{m['login']} solved it. Then the grunt went to check.\"" if m["login"]
                        else f"\"Clue {st['n']}. Chat had nothing. The grunt went anyway.\"")
                premise = f"Clue {st['n']} of {total}, {st['title']}: verified in game; {who}."
                turn = f"{t:%H:%M:%S} — the find lands and the card pins to the board"
                payoff = "the FOUND stamp" + (" and the solver's Desk Bucks" if m["login"] else "")
            else:
                a, b = t - datetime.timedelta(seconds=10), t + datetime.timedelta(seconds=15)
                hook = f"\"@{m['login']} cracked clue {st['n']} from chat.\""
                premise = f"Clue {st['n']} of {total}, {st['title']}: solved in chat, not yet proven."
                turn = f"{t:%H:%M:%S} — the SOLVED stamp hits the card"
                payoff = "the answer is right only if the game agrees: tease the find"
            out += [f"CLIP H{k:02d}",
                    f"Source in/out:  {a:%H:%M:%S} – {b:%H:%M:%S} PT  ({int((b - a).total_seconds())}s)",
                    f"One-line premise: {premise}",
                    f"Hook (on-screen, 0:00): {hook}",
                    f"Turn at:        {turn}",
                    f"Payoff line:    {payoff}",
                    f"Caption:        Clue {st['n']} of {total}. Would you have cracked it? #wowforever #hordehunt",
                    "Risk:           keep the riddle on screen, never the answer, if later clues build on it",
                    ""]
            k += 1
        if k == 1:
            out.append("No hunt moments tonight.")
        return "\n".join(out) + "\n"

    def _brief(self, st, report):
        lines = [f"# DRAFT bounty brief: {self.g['name']}",
                 "",
                 "DRAFT. Nothing is posted from this file. Max fills the money fields and says go;",
                 "then the bounty-desk skill takes it from there.",
                 "",
                 f"- Night: {report['night']}",
                 f"- Clues found: {st['found']} of {st['total']} (door {'open' if st['door_open'] else 'still shut'})",
                 f"- Solvers: {', '.join('@' + s for s in report['solvers']) or 'none yet'}",
                 f"- Clip specs: hunt-specs.md ({report['moments']} moments)",
                 f"- Reward codes: {sum(report['rewards'].values())} minted "
                 f"({report['rewards'].get('issued', 0)} live on bountysounds.com/redeem, "
                 f"{report['rewards'].get('pending_issue', 0)} still waiting to reach the site)",
                 "",
                 "## Money (Max fills these)",
                 "- Purse: $____",
                 "- Rate per 1,000 verified views: $____",
                 "- Window: ____ to ____",
                 "",
                 "## How the purse splits by clue (weights from hunt.txt)",
                 ]
        wsum = sum(s["weight"] for s in self.steps) or 1
        for s in self.steps:
            f = self.s["found"].get(s["id"])
            lines.append(f"- Clue {s['n']} {s['title']}: weight {s['weight']} "
                         f"({100 * s['weight'] / wsum:.0f}% of the purse) — {'found' if f else 'not found'}")
        lines += ["",
                  "## Rules to keep",
                  "- Pay for verified clips of verified finds. Never for in-game items or gold.",
                  "- Desk Bucks are a stream currency, not money. They are not part of the purse.",
                  "- Original art only: no Blizzard logos, UI art or game audio in clips' added graphics.",
                  ""]
        return "\n".join(lines)
