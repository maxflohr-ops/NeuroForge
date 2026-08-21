#!/usr/bin/env python3
"""ytgrab - a terminal for downloading YouTube videos, ad-free.

A thin, opinionated front-end for yt-dlp (https://github.com/yt-dlp/yt-dlp).

Why it is ad-free:
  * yt-dlp pulls the media streams directly, so YouTube's pre-roll / mid-roll
    ad breaks are never part of the file you get.
  * In-video sponsor reads are cut out with SponsorBlock, so the sponsor
    segments baked into the creator's own audio are removed too.

Run with no arguments for the interactive terminal, or pass URLs for one-shot
downloads.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path

__version__ = "1.0.0"

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ytgrab"
CONFIG_FILE = CONFIG_DIR / "config.json"
ARCHIVE_FILE = CONFIG_DIR / "downloaded.txt"
HISTORY_FILE = CONFIG_DIR / "shell_history"

# SponsorBlock category sets. "normal" strips paid promotion and self-promo,
# which is what people mean by "no ads". "aggressive" also drops intros,
# outros, subscribe-begging and non-music sections of music videos.
SB_NORMAL = ["sponsor", "selfpromo", "interaction"]
SB_AGGRESSIVE = SB_NORMAL + ["intro", "outro", "preview", "music_offtopic", "filler"]

QUALITIES = ["best", "4k", "1440p", "1080p", "720p", "480p", "360p", "audio"]

DEFAULT_CONFIG = {
    "output_dir": str(Path.home() / "Videos" / "ytgrab"),
    "quality": "best",
    "container": "mp4",          # mp4 | mkv | webm
    "audio_format": "mp3",       # mp3 | m4a | opus | flac | wav
    "sponsorblock": "normal",    # normal | aggressive | off
    "subtitles": False,
    "thumbnail": True,
    "metadata": True,
    "chapters": True,
    "playlist": False,           # follow playlists when a URL points into one
    "archive": True,             # never download the same video twice
    "cookies_from_browser": "",  # e.g. "chrome", "firefox", "brave:Profile 1"
    "concurrent_fragments": 4,
    "rate_limit": "",            # e.g. "2M"
    "proxy": "",
}


# --------------------------------------------------------------------------- #
# terminal helpers
# --------------------------------------------------------------------------- #

def _color_enabled() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


class C:
    if _color_enabled():
        RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
        RED, GREEN, YELLOW, BLUE, CYAN, MAGENTA = (
            "\033[31m", "\033[32m", "\033[33m", "\033[34m", "\033[36m", "\033[35m",
        )
    else:
        RESET = BOLD = DIM = RED = GREEN = YELLOW = BLUE = CYAN = MAGENTA = ""


def info(msg: str) -> None:
    print(f"{C.CYAN}::{C.RESET} {msg}")


def ok(msg: str) -> None:
    print(f"{C.GREEN}✓{C.RESET} {msg}")


def warn(msg: str) -> None:
    print(f"{C.YELLOW}!{C.RESET} {msg}", file=sys.stderr)


def err(msg: str) -> None:
    print(f"{C.RED}✗{C.RESET} {msg}", file=sys.stderr)


BANNER = rf"""{C.RED}
 ▄▄▄· ▄▄▄▄▄ ▄▄ • ▄▄▄  ▄▄▄· ▄▄▄▄·
 ▐█ ▄█•██  ▐█ ▀ ▪▀▄ █·▐█ ▀█ ▐█ ▀█▪
  ██▀· ▐█.▪▄█ ▀█▄▐▀▀▄ ▄█▀▀█ ▐█▀▀█▄
 ▐█▪·• ▐█▌·▐█▄▪▐█▐█•█▌▐█ ▪▐▌██▄▪▐█
 .▀     ▀▀▀ ·▀▀▀▀ .▀  ▀ ▀  ▀ ·▀▀▀▀{C.RESET}
 {C.BOLD}ytgrab v{__version__}{C.RESET} {C.DIM}· ad-free YouTube downloads, powered by yt-dlp{C.RESET}
"""


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #

def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except (json.JSONDecodeError, OSError) as exc:
            warn(f"ignoring unreadable config {CONFIG_FILE}: {exc}")
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2) + "\n")


# --------------------------------------------------------------------------- #
# dependency resolution
# --------------------------------------------------------------------------- #

def ytdlp_cmd() -> list[str] | None:
    """Return the command that runs yt-dlp, or None if it is not installed."""
    binary = shutil.which("yt-dlp")
    if binary:
        return [binary]
    try:
        subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            check=True, capture_output=True,
        )
        return [sys.executable, "-m", "yt_dlp"]
    except (subprocess.CalledProcessError, OSError):
        return None


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def install_ytdlp() -> bool:
    info("installing yt-dlp with pip …")
    for extra in (["--user"], ["--break-system-packages"], []):
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-U", "yt-dlp[default]", *extra]
        )
        if proc.returncode == 0 and ytdlp_cmd():
            ok("yt-dlp installed")
            return True
    err("could not install yt-dlp automatically — run: pip install -U yt-dlp")
    return False


def check_deps(auto_install: bool = True) -> list[str] | None:
    cmd = ytdlp_cmd()
    if cmd is None:
        if not auto_install or not install_ytdlp():
            return None
        cmd = ytdlp_cmd()
    if not have_ffmpeg():
        warn(
            "ffmpeg/ffprobe not found. Without it you are capped at ~720p "
            "(no stream merging), audio extraction and SponsorBlock cutting are "
            "unavailable. Install it: apt install ffmpeg / brew install ffmpeg"
        )
    return cmd


# --------------------------------------------------------------------------- #
# argument building
# --------------------------------------------------------------------------- #

def format_selector(cfg: dict) -> str:
    q = cfg["quality"]
    if q == "audio":
        return "bestaudio/best"
    if q == "best":
        return "bestvideo*+bestaudio/best"
    heights = {"4k": 2160, "1440p": 1440, "1080p": 1080,
               "720p": 720, "480p": 480, "360p": 360}
    h = heights.get(q, 1080)
    # Fall back to the next best thing rather than failing outright.
    return (
        f"bestvideo[height<={h}]+bestaudio/"
        f"best[height<={h}]/"
        f"bestvideo*+bestaudio/best"
    )


def output_template(cfg: dict) -> str:
    base = Path(cfg["output_dir"]).expanduser()
    # %(title).200B truncates on byte boundaries so long titles stay legal on
    # every filesystem; the id keeps re-uploads from colliding.
    name = "%(title).200B [%(id)s].%(ext)s"
    if cfg["playlist"]:
        return str(base / "%(playlist_title,channel,uploader|)s" /
                   ("%(playlist_index&{} - |)s" + name))
    return str(base / name)


def build_args(cfg: dict, urls: list[str]) -> list[str]:
    args: list[str] = [
        "--ignore-config",              # our settings only, no surprise ~/.config/yt-dlp
        "--no-warnings",
        "--progress",
        "--console-title",
        "--retries", "10",
        "--fragment-retries", "10",
        "--retry-sleep", "exp=1:30",
        "--concurrent-fragments", str(cfg["concurrent_fragments"]),
        "--format", format_selector(cfg),
        "--output", output_template(cfg),
        "--no-mtime",
    ]
    if os.name == "nt":
        args.append("--windows-filenames")

    args += ["--yes-playlist"] if cfg["playlist"] else ["--no-playlist"]

    if cfg["quality"] == "audio":
        args += ["--extract-audio", "--audio-format", cfg["audio_format"],
                 "--audio-quality", "0"]
    else:
        args += ["--merge-output-format", cfg["container"]]

    if cfg["thumbnail"]:
        args += ["--embed-thumbnail"] if have_ffmpeg() else ["--write-thumbnail"]
    if cfg["metadata"]:
        args += ["--embed-metadata"]
    if cfg["chapters"] and cfg["quality"] != "audio":
        args += ["--embed-chapters"]
    if cfg["subtitles"]:
        args += ["--sub-langs", "en.*,-live_chat", "--write-auto-subs",
                 "--write-subs", "--embed-subs", "--compat-options", "no-keep-subs"]

    # The ad-stripping bit.
    mode = cfg["sponsorblock"]
    if mode != "off" and have_ffmpeg():
        cats = SB_AGGRESSIVE if mode == "aggressive" else SB_NORMAL
        args += ["--sponsorblock-remove", ",".join(cats),
                 "--sponsorblock-mark", "all"]
    elif mode != "off":
        warn("SponsorBlock skipped: cutting segments needs ffmpeg")

    if cfg["archive"]:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        args += ["--download-archive", str(ARCHIVE_FILE)]
    if cfg["cookies_from_browser"]:
        args += ["--cookies-from-browser", cfg["cookies_from_browser"]]
    if cfg["rate_limit"]:
        args += ["--limit-rate", cfg["rate_limit"]]
    if cfg["proxy"]:
        args += ["--proxy", cfg["proxy"]]

    return args + ["--"] + urls


# --------------------------------------------------------------------------- #
# running
# --------------------------------------------------------------------------- #

def _hint_for(tail: str) -> str | None:
    low = tail.lower()
    if "confirm you're not a bot" in low or "sign in to confirm" in low:
        return ("YouTube wants a logged-in session. Run "
                "`set cookies chrome` (or firefox/brave/edge) and retry.")
    if "age" in low and "restrict" in low:
        return "Age-restricted video — cookies from a logged-in browser will fix it."
    if "private video" in low or "members-only" in low:
        return "Private/members-only video — you need an account that can see it."
    if "unavailable" in low and "country" in low:
        return "Geo-blocked — try `set proxy socks5://…` or a different network."
    if "ffmpeg" in low or "ffprobe" in low:
        return "Install ffmpeg to merge streams, extract audio and cut sponsors."
    if "http error 429" in low or "too many requests" in low:
        return "Rate-limited by YouTube. Wait a few minutes or `set rate 2M`."
    if "unable to extract" in low or "nsig extraction failed" in low:
        return "YouTube changed something — run `update` to get the newest yt-dlp."
    return None


def run_download(cfg: dict, urls: list[str]) -> int:
    cmd = check_deps()
    if cmd is None:
        return 127

    Path(cfg["output_dir"]).expanduser().mkdir(parents=True, exist_ok=True)
    full = cmd + build_args(cfg, urls)

    tail: deque[str] = deque(maxlen=40)
    try:
        proc = subprocess.Popen(full, stderr=subprocess.PIPE, text=True,
                                errors="replace", bufsize=1)
    except OSError as exc:
        err(f"could not start yt-dlp: {exc}")
        return 127

    assert proc.stderr is not None
    for line in proc.stderr:
        tail.append(line)
        sys.stderr.write(line)
    code = proc.wait()

    if code == 0:
        ok(f"done → {Path(cfg['output_dir']).expanduser()}")
    else:
        err(f"yt-dlp exited with status {code}")
        hint = _hint_for("".join(tail))
        if hint:
            print(f"{C.YELLOW}hint:{C.RESET} {hint}", file=sys.stderr)
    return code


def run_plain(extra: list[str], urls: list[str]) -> int:
    """Run yt-dlp for read-only queries (--list-formats, -j, …)."""
    cmd = check_deps()
    if cmd is None:
        return 127
    return subprocess.run(cmd + ["--ignore-config", "--no-warnings",
                                 *extra, "--", *urls]).returncode


def update_ytdlp() -> int:
    cmd = ytdlp_cmd()
    if cmd is None:
        return 0 if install_ytdlp() else 1
    info("updating yt-dlp …")
    # A self-updating binary knows best; a pip install needs pip.
    if len(cmd) == 1 and subprocess.run(cmd + ["-U"]).returncode == 0:
        ok("yt-dlp up to date")
        return 0
    return 0 if install_ytdlp() else 1


# --------------------------------------------------------------------------- #
# interactive terminal
# --------------------------------------------------------------------------- #

SETTERS = {
    "quality": ("quality", QUALITIES),
    "dir": ("output_dir", None),
    "container": ("container", ["mp4", "mkv", "webm"]),
    "audio": ("audio_format", ["mp3", "m4a", "opus", "flac", "wav"]),
    "sponsorblock": ("sponsorblock", ["normal", "aggressive", "off"]),
    "cookies": ("cookies_from_browser", None),
    "rate": ("rate_limit", None),
    "proxy": ("proxy", None),
}
TOGGLES = ["subtitles", "thumbnail", "metadata", "chapters", "playlist", "archive"]

HELP = f"""{C.BOLD}commands{C.RESET}
  {C.CYAN}<url> [url …]{C.RESET}      download (paste as many as you like)
  {C.CYAN}audio <url>{C.RESET}        download just the audio, this once
  {C.CYAN}formats <url>{C.RESET}      list every available stream
  {C.CYAN}info <url>{C.RESET}         title, channel, duration, view count
  {C.CYAN}batch <file>{C.RESET}       download every URL in a text file
  {C.CYAN}set <opt> <value>{C.RESET}  quality | dir | container | audio |
                     sponsorblock | cookies | rate | proxy
  {C.CYAN}toggle <opt>{C.RESET}       {' | '.join(TOGGLES)}
  {C.CYAN}config{C.RESET}             show current settings
  {C.CYAN}open{C.RESET}               open the download folder in Finder
  {C.CYAN}update{C.RESET}             update yt-dlp (fixes most YouTube breakage)
  {C.CYAN}archive clear{C.RESET}      forget what has already been downloaded
  {C.CYAN}help{C.RESET} · {C.CYAN}quit{C.RESET}         this text · exit

{C.DIM}quality: {', '.join(QUALITIES)}{C.RESET}
"""


def show_config(cfg: dict) -> None:
    print(f"\n{C.BOLD}settings{C.RESET} {C.DIM}({CONFIG_FILE}){C.RESET}")
    for key in DEFAULT_CONFIG:
        val = cfg[key]
        shown = (f"{C.GREEN}on{C.RESET}" if val is True else
                 f"{C.DIM}off{C.RESET}" if val is False else
                 f"{C.DIM}—{C.RESET}" if val == "" else str(val))
        print(f"  {key:<22} {shown}")
    sb = cfg["sponsorblock"]
    cats = {"normal": SB_NORMAL, "aggressive": SB_AGGRESSIVE}.get(sb)
    if cats:
        print(f"  {C.DIM}└ cutting: {', '.join(cats)}{C.RESET}")
    print()


def _setup_readline() -> None:
    try:
        import readline  # noqa: F401  (import registers the hooks)
    except ImportError:
        return
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        readline.read_history_file(HISTORY_FILE)
    except OSError:
        pass
    readline.set_history_length(500)
    import atexit
    atexit.register(lambda: _save_history(readline))


def _save_history(readline) -> None:
    try:
        readline.write_history_file(HISTORY_FILE)
    except OSError:
        pass


# Pasted links arrive wrapped in quotes, angle brackets or trailing sentence
# punctuation depending on where they were copied from, and share sheets often
# hand over a bare "youtu.be/..." with no scheme at all.
PASTE_JUNK = "\"'<>()[]{}`,.;!"
SITE_RE = re.compile(
    r"^(?:(?:www|m|music)\.)?(?:youtube\.com|youtu\.be|youtube-nocookie\.com)/",
    re.I,
)
BARE_HOST_RE = re.compile(r"^[\w-]+(?:\.[\w-]+)+/", re.I)


def normalize_url(token: str) -> str | None:
    """Turn one pasted token into a URL yt-dlp will accept, or None."""
    token = token.strip().strip(PASTE_JUNK).strip()
    if not token:
        return None
    if token.startswith(("http://", "https://")):
        return token
    if token.startswith(("ytsearch", "ytsearchdate")):  # ytsearch5:query
        return token
    if SITE_RE.match(token) or BARE_HOST_RE.match(token):
        return "https://" + token
    return None


def extract_urls(line: str) -> list[str]:
    """URLs from a pasted line, or [] if the line is not purely URLs.

    Whitespace-, comma- and pipe-separated lists all work, so you can dump a
    whole batch of links in one paste.
    """
    tokens = [t for t in re.split(r"[\s,|]+", line) if t]
    urls = [normalize_url(t) for t in tokens]
    return list(urls) if urls and all(urls) else []


def looks_like_url(token: str) -> bool:
    return normalize_url(token) is not None


def reveal(path: Path) -> None:
    """Open the download folder in Finder / the desktop file manager."""
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    if shutil.which(opener):
        subprocess.run([opener, str(path)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ok(f"opened {path}")
    else:
        print(path)


def shell(cfg: dict) -> int:
    print(BANNER)
    if check_deps() is None:
        return 127
    print(f"{C.DIM}saving to{C.RESET} {Path(cfg['output_dir']).expanduser()}   "
          f"{C.DIM}quality{C.RESET} {cfg['quality']}   "
          f"{C.DIM}sponsorblock{C.RESET} {cfg['sponsorblock']}")
    print(f"\n{C.BOLD}Paste a YouTube link and press Enter.{C.RESET}"
          f"{C.DIM}  (`help` for everything else, `quit` to leave){C.RESET}\n")
    _setup_readline()

    while True:
        try:
            raw = input(f"{C.MAGENTA}ytgrab{C.RESET} {C.BOLD}›{C.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not raw:
            continue

        # A pasted link (or several) is the common case — handle it before
        # anything gets parsed as a command.
        urls = extract_urls(raw)
        if urls:
            try:
                run_download(cfg, urls)
            except KeyboardInterrupt:
                print()
                warn("cancelled")
            continue

        try:
            parts = shlex.split(raw)
        except ValueError:
            parts = raw.split()
        cmd, args = parts[0].lower(), parts[1:]
        cmd_urls = extract_urls(" ".join(args))  # for `audio`/`formats`/`info`

        if cmd in ("quit", "exit", "q"):
            return 0
        if cmd in ("help", "?", "h"):
            print(HELP)
        elif cmd == "config":
            show_config(cfg)
        elif cmd in ("open", "folder"):
            reveal(Path(cfg["output_dir"]).expanduser())
        elif cmd == "update":
            update_ytdlp()
        elif cmd == "set":
            do_set(cfg, args)
        elif cmd == "toggle":
            do_toggle(cfg, args)
        elif cmd == "archive":
            if args[:1] == ["clear"]:
                ARCHIVE_FILE.unlink(missing_ok=True)
                ok("archive cleared")
            else:
                n = len(ARCHIVE_FILE.read_text().splitlines()) if ARCHIVE_FILE.exists() else 0
                info(f"{n} videos remembered ({ARCHIVE_FILE})")
        elif cmd == "formats":
            if cmd_urls:
                run_plain(["--list-formats"], cmd_urls)
            else:
                err("usage: formats <url>")
        elif cmd == "info":
            if cmd_urls:
                run_plain(["--print",
                           "%(title)s\n  channel: %(channel)s\n  duration: "
                           "%(duration_string)s\n  views: %(view_count)s\n"
                           "  uploaded: %(upload_date>%Y-%m-%d)s"], cmd_urls)
            else:
                err("usage: info <url>")
        elif cmd == "audio":
            if cmd_urls:
                run_download({**cfg, "quality": "audio"}, cmd_urls)
            else:
                err("usage: audio <url>")
        elif cmd == "batch":
            do_batch(cfg, args)
        else:
            err(f"not a link or a command: {cmd}  (try `help`)")


def do_set(cfg: dict, args: list[str]) -> None:
    if len(args) < 2:
        err(f"usage: set <{' | '.join(SETTERS)}> <value>")
        return
    key, value = args[0].lower(), " ".join(args[1:])
    if key not in SETTERS:
        err(f"unknown option {key}  (one of: {', '.join(SETTERS)})")
        return
    field, allowed = SETTERS[key]
    if allowed and value not in allowed:
        err(f"{key} must be one of: {', '.join(allowed)}")
        return
    if field == "output_dir":
        value = str(Path(value).expanduser())
    cfg[field] = value
    save_config(cfg)
    ok(f"{field} = {value or '—'}")


def do_toggle(cfg: dict, args: list[str]) -> None:
    if not args or args[0] not in TOGGLES:
        err(f"usage: toggle <{' | '.join(TOGGLES)}>")
        return
    cfg[args[0]] = not cfg[args[0]]
    save_config(cfg)
    ok(f"{args[0]} = {'on' if cfg[args[0]] else 'off'}")


def do_batch(cfg: dict, args: list[str]) -> None:
    if not args:
        err("usage: batch <file>")
        return
    path = Path(args[0]).expanduser()
    if not path.exists():
        err(f"no such file: {path}")
        return
    urls = [ln.strip() for ln in path.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")]
    if not urls:
        err(f"{path} has no URLs")
        return
    info(f"{len(urls)} URLs queued")
    run_download(cfg, urls)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ytgrab",
        description="Ad-free YouTube downloads in your terminal (yt-dlp front-end). "
                    "Run without URLs for the interactive terminal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  ytgrab                                   interactive terminal\n"
               "  ytgrab https://youtu.be/dQw4w9WgXcQ      download, sponsors cut\n"
               "  ytgrab -q 1080p -o ~/Movies <url>        cap the resolution\n"
               "  ytgrab -q audio --audio-format mp3 <url> rip the audio\n"
               "  ytgrab --playlist <playlist-url>         whole playlist\n"
               "  ytgrab --cookies-from-browser chrome <url>   age-restricted video\n",
    )
    p.add_argument("urls", nargs="*", help="YouTube (or any supported site) URLs")
    p.add_argument("-q", "--quality", choices=QUALITIES, help="target quality")
    p.add_argument("-o", "--output", metavar="DIR", help="download folder")
    p.add_argument("--container", choices=["mp4", "mkv", "webm"])
    p.add_argument("--audio-format", choices=["mp3", "m4a", "opus", "flac", "wav"])
    p.add_argument("--sponsorblock", choices=["normal", "aggressive", "off"],
                   help="how much of the in-video sponsor talk to cut")
    p.add_argument("--subs", action="store_true", help="embed English subtitles")
    p.add_argument("--playlist", action="store_true", help="follow playlists")
    p.add_argument("--no-archive", action="store_true",
                   help="allow re-downloading videos you already have")
    p.add_argument("--cookies-from-browser", metavar="BROWSER",
                   help="chrome | firefox | brave | edge | safari (for age-gated "
                        "videos and bot checks)")
    p.add_argument("--rate-limit", metavar="RATE", help="e.g. 2M")
    p.add_argument("--proxy", metavar="URL")
    p.add_argument("-F", "--list-formats", action="store_true",
                   help="show available streams and exit")
    p.add_argument("--info", action="store_true", help="show video details and exit")
    p.add_argument("--config", action="store_true", help="print settings and exit")
    p.add_argument("--save", action="store_true",
                   help="persist the flags given here as the new defaults")
    p.add_argument("--update", action="store_true", help="update yt-dlp and exit")
    p.add_argument("-V", "--version", action="version",
                   version=f"ytgrab {__version__}")
    return p


def apply_flags(cfg: dict, a: argparse.Namespace) -> dict:
    cfg = dict(cfg)
    if a.quality:
        cfg["quality"] = a.quality
    if a.output:
        cfg["output_dir"] = str(Path(a.output).expanduser())
    if a.container:
        cfg["container"] = a.container
    if a.audio_format:
        cfg["audio_format"] = a.audio_format
    if a.sponsorblock:
        cfg["sponsorblock"] = a.sponsorblock
    if a.subs:
        cfg["subtitles"] = True
    if a.playlist:
        cfg["playlist"] = True
    if a.no_archive:
        cfg["archive"] = False
    if a.cookies_from_browser:
        cfg["cookies_from_browser"] = a.cookies_from_browser
    if a.rate_limit:
        cfg["rate_limit"] = a.rate_limit
    if a.proxy:
        cfg["proxy"] = a.proxy
    return cfg


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.urls = [normalize_url(u) or u for u in args.urls]
    cfg = apply_flags(load_config(), args)

    if args.save:
        save_config(cfg)
        ok(f"defaults saved to {CONFIG_FILE}")

    if args.update:
        return update_ytdlp()
    if args.config:
        show_config(cfg)
        return 0

    if not args.urls:
        return shell(cfg)

    if args.list_formats:
        return run_plain(["--list-formats"], args.urls)
    if args.info:
        return run_plain(["--print",
                          "%(title)s\n  channel: %(channel)s\n  duration: "
                          "%(duration_string)s\n  views: %(view_count)s"], args.urls)

    try:
        return run_download(cfg, args.urls)
    except KeyboardInterrupt:
        print()
        warn("cancelled")
        return 130


if __name__ == "__main__":
    sys.exit(main())
