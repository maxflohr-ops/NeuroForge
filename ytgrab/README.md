# ytgrab

A terminal for downloading YouTube videos — no ads, no ad-blocker fights, no
"skip in 5".

It is a small, opinionated front-end for
[yt-dlp](https://github.com/yt-dlp/yt-dlp) that keeps the good defaults and
hides the 400 flags.

## Why you get no ads

Two different things are called "ads", and ytgrab handles both:

| What | How it's handled |
| --- | --- |
| YouTube's pre-roll / mid-roll ad breaks | Never downloaded. yt-dlp fetches the media streams directly, so the ad player is never in the picture. |
| Sponsor reads baked into the creator's own audio | Cut out with [SponsorBlock](https://sponsor.ajay.app/) crowd-sourced timestamps, before the file is written. |

Default cut list: `sponsor`, `selfpromo`, `interaction` ("smash that like
button"). Switch to `aggressive` and it also drops intros, outros, previews,
filler and the non-music parts of music videos. Everything not cut is still
written as a chapter marker, so you can see where the segments were.

## Install

### macOS — three commands, no git

```bash
brew install yt-dlp ffmpeg
curl -fsSL https://raw.githubusercontent.com/maxflohr-ops/NeuroForge/0827eadf330ecec89df996a482f85676f2c746d9/ytgrab/ytgrab.py \
  -o "$(brew --prefix)/bin/ytgrab" && chmod +x "$(brew --prefix)/bin/ytgrab"
ytgrab
```

`$(brew --prefix)/bin` is already on your PATH and works on both Apple Silicon
and Intel Macs, so there is nothing to configure afterwards.

No Homebrew yet? Install it first — it takes a few minutes and asks for your
Mac password:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### From a clone

`ytgrab` lives on the `claude/youtube-video-downloader-f4qg1x` branch, which is
**not** this repository's default branch — clone that branch explicitly or the
folder will not be there:

```bash
git clone -b claude/youtube-video-downloader-f4qg1x \
  https://github.com/maxflohr-ops/NeuroForge.git
cd NeuroForge/ytgrab
./install.sh
```

The installer fetches yt-dlp, installs ffmpeg (Homebrew on macOS, apt/dnf/pacman
on Linux) and links `ytgrab` into a directory already on your PATH. Re-run it
any time to update.

### By hand

```bash
pip install -U "yt-dlp[default]"     # the downloader
brew install ffmpeg                  # or: apt install ffmpeg
python3 ytgrab.py                    # run it in place, no install
```

**ffmpeg is not optional in practice.** YouTube serves video and audio as
separate streams above 720p, and merging them — plus extracting MP3s and
cutting sponsor segments — is ffmpeg's job. ytgrab runs without it, just
limited, and tells you so.

## The terminal

Type `ytgrab`, paste a link, press Enter. That's the whole thing.

```
ytgrab › https://www.youtube.com/watch?v=dQw4w9WgXcQ
[download] 100% of 47.21MiB in 00:03
[SponsorBlock] Removing 2 segments (1m14s)
✓ done → /home/you/Videos/ytgrab
ytgrab › 
```

The prompt comes straight back, so you can keep pasting. Paste is forgiving:

- bare share links with no `https://` — `youtu.be/dQw4w9WgXcQ`
- links that came wrapped in quotes, `<angle brackets>` or a trailing comma
- several links at once, separated by spaces or commas — they queue up
- mobile, `music.youtube.com` and `youtube-nocookie` links
- timestamps and tracking junk (`?si=`, `&t=90s`) — kept or ignored as needed

Everything else is optional:

| Command | Does |
| --- | --- |
| `audio <url>` | audio only, just this once |
| `formats <url>` | list every available stream |
| `info <url>` | title, channel, duration, views |
| `batch <file>` | download every URL in a text file |
| `set <opt> <val>` | `quality` `dir` `container` `audio` `sponsorblock` `cookies` `rate` `proxy` |
| `toggle <opt>` | `subtitles` `thumbnail` `metadata` `chapters` `playlist` `archive` |
| `config` | show current settings |
| `update` | update yt-dlp — fixes most YouTube breakage |
| `archive clear` | forget what has already been downloaded |
| `help` · `quit` | |

Settings are saved to `~/.config/ytgrab/config.json` the moment you change
them, so the next session starts where you left off. Arrow-key history works.

## One-shot use

If you'd rather not stay in the terminal, pass the link as an argument:

```bash
ytgrab "https://youtu.be/dQw4w9WgXcQ"              # best quality, sponsors cut
ytgrab -q 1080p -o ~/Movies <url>                  # cap the resolution
ytgrab -q audio --audio-format mp3 <url>           # rip the audio
ytgrab --playlist "<playlist-url>"                 # whole playlist, numbered
ytgrab --sponsorblock aggressive <url>             # cut intros/outros too
ytgrab --cookies-from-browser chrome <url>         # age-restricted video
ytgrab -F <url>                                    # list available streams
ytgrab -q 1080p --save                             # make those flags the default
ytgrab --update                                    # update yt-dlp
```

## Defaults, and why

- **Quality `best`** — highest video + highest audio, merged into MP4.
- **Archive on** — every finished video ID is recorded, so re-running a
  playlist downloads only what's new. `archive clear` resets it.
- **Thumbnail, metadata and chapters embedded** — the file carries its title,
  channel, upload date and chapter marks into your player.
- **Playlists off** — a URL that happens to sit inside a playlist downloads one
  video, not four hundred. `--playlist` opts in.
- **10 retries with backoff, 4 parallel fragments** — survives flaky networks
  without hammering YouTube.
- **Filenames** as `Title [videoId].mp4`, truncated to a length every
  filesystem accepts, with the ID keeping re-uploads from colliding.

## When something breaks

YouTube changes its player constantly; yt-dlp keeps up, so **`update` fixes
most failures**. Beyond that, ytgrab reads the error and tells you what to do:

| Error | Fix |
| --- | --- |
| "Sign in to confirm you're not a bot" | `set cookies chrome` (or `firefox`, `brave`, `edge`, `safari`) — borrows your logged-in session |
| Age-restricted / members-only | same — cookies from an account that can watch it |
| HTTP 429, too many requests | wait a few minutes, or `set rate 2M` |
| Geo-blocked | `set proxy socks5://host:port` |
| Stuck at 720p | install ffmpeg |

Close the browser before using `--cookies-from-browser` on Chrome-family
browsers — they lock the cookie database while running.

## Tests

```bash
python3 -m pytest test_ytgrab.py -q
```

## Fair use

This downloads video for personal use — offline viewing, archiving, clipping
material you have the rights to. Redistributing other people's work is on you,
and so is your relationship with YouTube's Terms of Service. Support creators
whose work you keep.
