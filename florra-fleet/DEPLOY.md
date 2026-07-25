# Deploying the fleet for real

Two processes to host:

| process | start command | needs |
|---|---|---|
| Discord bot (the archivist) | `python runner.py archivist` | outbound only — no port |
| Website chat (the front desk) | `python web_runner.py archivist` | a public HTTPS URL, listens on `$PORT` |

Both read the same env vars (see `.env.example`). Rotate the Discord token
and both API keys when you first deploy — the originals passed through chat.

## Option A — Railway (recommended, ~$5/mo, ~10 min)

1. railway.app → New Project → **Deploy from GitHub repo** → pick this repo.
2. In the service settings: **Root Directory** = `florra-fleet`. Railway
   detects the Dockerfile. This first service is the Discord bot — its
   default command (`python runner.py archivist`) is already right.
3. **Variables** tab → paste everything from `.env.example` with real values.
4. Add the web service: **+ New → GitHub repo → same repo**, root directory
   `florra-fleet` again, and override **Start Command** to
   `python web_runner.py archivist`. Same variables (Railway lets you share
   them via a variable group). Under **Settings → Networking → Generate
   Domain** to get the public URL.
5. Shopify: Online Store → Themes → Edit code → `theme.liquid`, before
   `</body>`:
   `<script src="https://YOUR-RAILWAY-DOMAIN/widget.js"></script>`

## Option B — a computer you already own (free)

Any always-on box (old laptop, Mac mini, mini-PC) with Docker:

```bash
git clone <repo> && cd <repo>/florra-fleet
cp .env.example .env   # fill in
docker compose up -d archivist archivist-web
```

The Discord bot works immediately (outbound only). For the website chat
you need a public URL to the box — use a free Cloudflare Tunnel on that
machine (`cloudflared tunnel`), which gives you a stable HTTPS domain
without opening ports.

## Option C — Fly.io (~free for this size)

```bash
cd florra-fleet
fly launch --no-deploy          # accept Dockerfile detection
fly secrets import < .env       # loads the env vars
fly deploy                      # web chat is reachable at your fly domain
```

Run the Discord bot as a second process group in `fly.toml`
(`[processes] bot = "python runner.py archivist"`).

## Option D — Render.com (free tier, with caveats)

A free Render "Web Service" can host the website chat (build from Dockerfile,
start command `python web_runner.py archivist`), but free services sleep
after idle — first message after a quiet spell takes ~30-60s. Background
workers (the Discord bot) are not on the free tier. Fine for demoing the
widget; not the long-term home.

## After any deploy

- Rotate: Discord token (developer portal → Bot → Reset Token), Anthropic
  key (console.anthropic.com), Notion token (notion.so/my-integrations).
  Update the host's variables with the fresh values.
- The keepalive routine babysitting the dev-session bot becomes unnecessary —
  turn it off so two bot instances don't answer twice.
