#!/usr/bin/env python3
"""Compile hunt.txt -> engine/hunt.json (hashed answers) + addon/HordeHunt/HuntData.lua (no answers).

usage: python3 hunt/compile.py [hunt.txt] [--out <package root>]
  live hunt:  python3 hunt/compile.py live/<hunt>.txt --out live
  (live/ is gitignored: this repo is public and a real hunt's answers must never be pushed)
Prints the florra.net HUNT snippet (door id, salt, PBKDF2 hash of the door code).
"""
import hashlib, json, os, re, sys, unicodedata

DOOR_ITER = 150000  # PBKDF2 rounds for the public door hash (florra.net checks it in the browser)


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"['\u2019`]", "", s).replace("&", " and ")  # ukor's -> ukors, & -> and
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"^the ", "", s)


def answer_hash(salt, s):
    return hashlib.sha256((salt + "\n" + norm(s)).encode()).hexdigest()


def door_hash(salt, s):
    return hashlib.pbkdf2_hmac("sha256", norm(s).encode(), salt.encode(), DOOR_ITER).hex()


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "hunt"


class HuntError(Exception):
    pass


def parse(text):
    hunt = {"name": None, "door": None, "code": None, "steps": []}
    cur = None
    errs = []
    for ln, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(hunt|door|code):\s*(.+)$", line)
        if m:
            hunt["name" if m.group(1) == "hunt" else m.group(1)] = m.group(2).strip()
            continue
        tag, rest = line[0], line[1:].strip()
        if tag == "=":
            if "|" not in rest:
                errs.append(f"line {ln}: '= id | title' needs a |")
                continue
            sid, title = [p.strip() for p in rest.split("|", 1)]
            if not re.match(r"^[A-Za-z0-9_]+$", sid):
                errs.append(f"line {ln}: clue id '{sid}' must be letters, digits or _")
            cur = {"id": sid, "title": title, "riddle": [], "verify": [], "answers": [],
                   "bucks": 100, "weight": 1, "string": "", "line": ln}
            hunt["steps"].append(cur)
            continue
        if cur is None:
            errs.append(f"line {ln}: '{tag}' line before the first '= id | title'")
            continue
        if tag == "?":
            cur["riddle"].append(rest)
        elif tag == "@":
            m = re.match(r"^(.+?)\s*\|\s*([\d.]+)\s+([\d.]+)(?:\s+([\d.]+))?$", rest)
            if not m:
                errs.append(f"line {ln}: '@ zone | x y [r]' expected")
                continue
            x, y = float(m.group(2)), float(m.group(3))
            r = float(m.group(4)) if m.group(4) else 1.0
            if not (0 <= x <= 100 and 0 <= y <= 100):
                errs.append(f"line {ln}: map coordinates run 0-100")
            cur["verify"].append({"kind": "loc", "zone": m.group(1).strip(), "x": x, "y": y, "r": r})
        elif tag == "$":
            cur["verify"].append({"kind": "loot", "item": rest})
        elif tag == ">":
            cur["verify"].append({"kind": "npc", "npc": rest})
        elif tag == "!":
            cur["verify"].append({"kind": "manual"})
        elif tag == "a":
            cur["answers"] += [a.strip() for a in rest.split("|") if norm(a)]
        elif tag in "bw":
            try:
                v = int(rest)
                assert v >= 0
            except Exception:
                errs.append(f"line {ln}: '{tag}' takes a whole number")
                continue
            cur["bucks" if tag == "b" else "weight"] = v
        elif tag == "s":
            cur["string"] = rest
        else:
            errs.append(f"line {ln}: unknown line '{tag}'")

    if not hunt["name"]:
        errs.append("missing 'hunt: <name>'")
    if not hunt["steps"]:
        errs.append("no clues ('= id | title')")
    seen = set()
    for s in hunt["steps"]:
        where = f"clue {s['id']} (line {s['line']})"
        if s["id"] in seen:
            errs.append(f"{where}: duplicate id")
        seen.add(s["id"])
        if not s["riddle"]:
            errs.append(f"{where}: needs a '?' riddle")
        if len(s["verify"]) != 1:
            errs.append(f"{where}: needs exactly one verify line (@ $ > or !), has {len(s['verify'])}")
        if not s["answers"] and not (s["verify"] and s["verify"][0]["kind"] == "manual"):
            errs.append(f"{where}: needs an 'a' answer (only '! manual' clues may skip it)")
    if hunt["code"] and not hunt["door"]:
        errs.append("'code:' needs a 'door:' petal")
    if errs:
        raise HuntError("\n".join(errs))
    return hunt


def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def build(hunt):
    slug = slugify(hunt["name"])
    guide = {"name": hunt["name"], "slug": slug, "door": hunt["door"], "steps": []}
    for n, s in enumerate(hunt["steps"], 1):
        guide["steps"].append({
            "id": s["id"], "n": n, "title": s["title"], "riddle": " ".join(s["riddle"]),
            "verify": s["verify"][0], "answers": [answer_hash(slug, a) for a in s["answers"]],
            "bucks": s["bucks"], "weight": s["weight"], "string": s["string"],
        })
    if hunt["code"]:
        guide["door_hash"] = door_hash(slug, hunt["code"])

    L = ["-- generated by hunt/compile.py from hunt.txt. Do not edit by hand.",
         "-- No answers in here: the addon only needs where to verify.",
         "HordeHuntData = {", f"  name = {lua_str(hunt['name'])},", f"  slug = {lua_str(slug)},", "  steps = {"]
    for s in guide["steps"]:
        v = s["verify"]
        if v["kind"] == "loc":
            vs = f'kind="loc", zone={lua_str(v["zone"])}, x={v["x"]}, y={v["y"]}, r={v["r"]}'
        elif v["kind"] == "loot":
            vs = f'kind="loot", item={lua_str(v["item"])}'
        elif v["kind"] == "npc":
            vs = f'kind="npc", npc={lua_str(v["npc"])}'
        else:
            vs = 'kind="manual"'
        L.append(f'    {{ id={lua_str(s["id"])}, title={lua_str(s["title"])}, riddle={lua_str(s["riddle"])}, {vs} }},')
    L += ["  },", "}", ""]
    return guide, "\n".join(L)


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(root, "hunt", "hunt.txt")
    args = list(argv)
    if "--out" in args:
        i = args.index("--out")
        root = args[i + 1]
        del args[i:i + 2]
    if args:
        src = args[0]
    try:
        hunt = parse(open(src, encoding="utf-8").read())
    except HuntError as e:
        print("hunt.txt has problems:\n" + str(e))
        return 1
    guide, lua = build(hunt)
    os.makedirs(os.path.join(root, "engine"), exist_ok=True)
    os.makedirs(os.path.join(root, "addon", "HordeHunt"), exist_ok=True)
    with open(os.path.join(root, "engine", "hunt.json"), "w") as f:
        json.dump(guide, f, indent=1)
    with open(os.path.join(root, "addon", "HordeHunt", "HuntData.lua"), "w") as f:
        f.write(lua)
    # make the output's addon folder complete, so a live/ build can be copied to AddOns as is
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("HordeHunt.lua", "HordeHunt.toc"):
        src_f = os.path.join(here, "addon", "HordeHunt", name)
        dst_f = os.path.join(root, "addon", "HordeHunt", name)
        if os.path.abspath(src_f) != os.path.abspath(dst_f):
            with open(src_f, "rb") as a, open(dst_f, "wb") as b:
                b.write(a.read())
    print(f"compiled {len(guide['steps'])} clues for '{guide['name']}' -> engine/hunt.json + addon/HordeHunt/HuntData.lua")
    if guide.get("door_hash"):
        print("florra.net HUNT snippet (paste over the HUNT line in index.html):")
        print("const HUNT=" + json.dumps({"door": guide["door"], "salt": guide["slug"],
                                         "iter": DOOR_ITER, "hash": guide["door_hash"]}) + ";")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
