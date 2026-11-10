# Horde Hunt

A clue hunt that runs on Florra OS. **Don't pay for clues. Pay for proof.**

1. **Bounty layer.** A viewer solves a clue in chat with `!clue <answer>`, which only *names* them. The game then has to verify the find: the addon stamps it into the chat log. Only then does the solver's Desk Bucks payout go into the ledger. Real-money purses go into a draft brief with the money left blank.
2. **Case board.** A red-string overlay in the Redstring style: pinned cards, a red string drawn to each find, a 0–100° heat meter, SOLVED and FOUND stamps. A mini strip covers the gameplay scene.
3. **The florra.net door.** The last clue hands out a door code. `florra.net/#hunt=<code>` checks it in the browser against a PBKDF2 hash, warms that petal and opens its panel. The code itself is never in the page.
4. **Clip engine.** Every find and solve becomes a clip spec in the ai-clipping CLIP format, with finds ranked first. They're filed into the same night folder as Orders of the Horde.

Runs beside the Orders of the Horde engine (8907) on **port 8908**. It never touches that engine's state.

## What's in the box

| Path | What it is |
|---|---|
| `hunt/hunt.txt` | The hunt source. **Holds the answers, so it stays off stream.** Currently a placeholder example. |
| `hunt/compile.py` | Compiles `hunt.txt` into `engine/hunt.json` (answers hashed) and `addon/HordeHunt/HuntData.lua` (no answers), then prints the florra.net `HUNT` line. |
| `addon/HordeHunt/` | The WoW addon: the clue card, location/loot/NPC verification, and the `HUNT_DONE` whisper-to-self. |
| `engine/hunt.py` | Core logic: guesses, verification, ledger, heat, night filing. |
| `engine/hunt_server.py` | HTTP on 8908, chat-log tail, anonymous Twitch chat reader, Desk Bucks pay loop. |
| `engine/hunt-board.html` | The case board overlay (`/hunt/board`, or `/hunt/board?mini=1` for the corner strip). |
| `engine/selftest.py` | Plays a whole hunt in a temp folder. Expect `76/76 checks passed`. |
| `engine/config.example.json` | Copy to `engine/config.json` and fill in. |

## Write a hunt

Legend at the top of `hunt/hunt.txt`. Each clue gets an id, a title, a riddle, **exactly one** verify line, and an answer:

```
= h1 | The First Mark
? the riddle chat sees
@ Durotar | 52.1 41.3 1.5     verify: stand within 1.5 map-% of that spot
a razor hill | razorhill       what chat types after !clue (alternates with |)
b 100                          Desk Bucks to the solver once the find is verified
w 2                            purse weight for the bounty draft
s the string label             drawn on the board when the clue is found
```

Other verify lines are `$ Item Name` (looted), `> Npc Name` (talked to) and `! manual` (Max types `/hunt done`). Clue ids must never be reused within a hunt.

Then:
```
python3 hunt/compile.py
python3 engine/selftest.py
```
`compile.py` refuses a hunt with a missing riddle, missing answer, duplicate id or bad coordinates, and lists every problem at once.

**Use only clue text you can source. Never invent coordinates or names.** Check every spot in the WoW Forever client before the hunt goes on stream. Retail coordinates may not match.

## Live hunts: never in git

**This repo is public.** A real hunt's `hunt.txt` holds the answers. Its compiled `hunt.json` holds hashed answers, and short place names are easy to brute-force. `HuntData.lua` names the items and spots. So live hunts live in `live/`, which is gitignored:

```
python3 hunt/compile.py live/hunt-one.txt --out live
```
That builds `live/engine/hunt.json` (point `guide` in `engine/config.json` at it) and a complete `live/addon/HordeHunt/` to copy into AddOns. The example hunt in `hunt/` is the only one that belongs in git.

## Install on the Mac mini

1. Copy `addon/HordeHunt` into WoW Forever's `Interface/AddOns/`. Set `## Interface:` in `HordeHunt.toc` to what `/dump select(4, GetBuildInfo())` prints in the Forever client. The 11507 in the file is a placeholder.
2. `cp engine/config.example.json engine/config.json`, then set `chat_log` (the Forever `Logs/WoWChatLog.txt`), `character` (your character's name) and `nights_root`.
3. `python3 engine/hunt_server.py`. Start it the same way the guide engine starts (from OBS) if macOS blocks the WoW folder.
4. OBS: add a browser source at `http://localhost:8908/hunt/board` (1920×1080) for a Case Board scene, and `?mini=1` (620×210) on the WoW Forever scene.

## Endpoints

| Route | Does |
|---|---|
| `/hunt/state` | What the board reads (no answers, sealed clues hidden). |
| `/hunt/board` | The overlay. |
| `/hunt/florra` | Public slice: heat, found/total, door_open, solver names. |
| `/hunt/guess?login=&text=` | A guess, as if typed after `!clue`. |
| `/hunt/chat?login=&text=` | A whole chat line. |
| `/hunt/feed?line=` | A chat-log line. |
| `/hunt/found?id=` / `/hunt/undo[?id=]` | Desk overrides. |
| `/hunt/pay` | Retry Desk Bucks now (it also retries every 30 s). |
| `/hunt/sync` | Send pending reward codes / voids to Bounty Sounds now. |
| `/hunt/rewards` | **Desk only:** every reward code and its status. Never on stream. |
| `/hunt/file` | File the night: `hunt-report.json`, `hunt-specs.md`, `hunt-bounty-brief-DRAFT.md`. |

## How proof works (and why viewers can't fake it)

The addon whispers itself `HUNT_DONE <id> <slug>`, so the chat log gets `To <you>: HUNT_DONE …`. The engine trusts only that outgoing line, anchored to the start of the log line, and only to your own character. If a viewer whispers `HUNT_DONE`, or hides `To Grunt: HUNT_DONE` inside their own whisper, it's ignored (the selftest covers both). Stamps from a different hunt's slug are also ignored.

## Rewards: redeemed on Bounty Sounds

When the game verifies a find that someone solved in chat, the engine mints a one-time code like `HUNT-7K3MQ-9TXA2`.

1. **Only the code's hash goes to Bounty Sounds**, signed with `HUNT_BRIDGE_SECRET` and sent to the `bridge-hunt-rewards` edge function. It retries every 30 s until the site confirms, and re-sending is safe.
2. **You hand the winner the code.** Open `/hunt/rewards` on the phone desk (it lists every code; never put it on stream) and whisper it to them. The engine can't message anyone.
3. **The winner redeems at `bountysounds.com/redeem`.** They sign in and enter the code, and it locks to their account. Codes are one use and forgive case, dashes and O/0, I/1 mix-ups.
4. **Admin desk → Hunt tab.** You set the amount and approve, send the money through your usual payout, then press Mark paid. Nothing pays on its own.

Undoing a find voids its code on the site, unless the winner already redeemed it. Then the engine flags it `redeemed_on_site` and it's your call on the admin desk. A re-find after a void mints a fresh code. Someone who finds a clue that nobody solved in chat gets no code.

**Setup:** set `bounty_bridge` in `engine/config.json` (the example has the project URL), and put the same random secret in two places: `HUNT_BRIDGE_SECRET` in the Mac's environment for the engine, and as a Supabase function secret on the bountysounds project. Until both are set, codes wait in the state file and nothing is lost.

## Desk Bucks

The ledger ids are `hunt:<slug>:<clue>`, and the helper must ignore an id it has already applied. These use the same `/bucks/add` route as Orders of the Horde (spec: `helper/DESK-BUCKS-ENDPOINT.md`). **Until the helper has that route, entries stay pending, not paid.** Undoing a find voids an unpaid entry. A paid entry is never clawed back automatically: the undo returns a note and the fix is made by hand.

## The florra.net door

`compile.py` prints a line like:
```
const HUNT={"door": "bounty-sounds", "salt": "...", "iter": 150000, "hash": "..."};
```
Paste it over `const HUNT=null;` in florra-net `index.html`. The code works at `florra.net/#hunt=<code>` (case and punctuation don't matter). Add `"state": "<public url of /hunt/florra>"` to warm the door petal live. That needs a public copy of the slice: `/hunt/florra` is on the Mac's localhost. Set `florra_export` in the config to write it to a file you sync somewhere public.

## Filing and handing off

`/hunt/file` writes into the night folder the guide engine uses: today's PT date, or the latest `-2`/`-3` folder if one exists.

- `hunt-specs.md` goes to **ai-clipping** §2 Production, finds first.
- `hunt-bounty-brief-DRAFT.md` goes to **bounty-desk**, but only after Max fills in the purse, rate and window and says go.

## Rules

- Purses pay for verified clips of verified finds. Never for in-game items or gold.
- Desk Bucks are a stream currency, not money.
- Original art and sound only: the board is paper, pins and string, with no Blizzard logos, UI art or audio.
- Any engine change ships with a clean selftest.

## Known limits

- The `## Interface` number has to come from the Forever client; it's a placeholder here.
- The Lua was written against the Classic Era API (`C_Map`, `SendChatMessage` whisper-to-self, `LoggingChat`) and has not run in the Forever client yet. Do a test run with the example hunt before going live.
- No `luac` on the build machine, so the selftest skips the Lua syntax check. Install `lua5.1` on the Mac to turn it on.
- Twitch chat is read anonymously; the engine can't post in chat.
