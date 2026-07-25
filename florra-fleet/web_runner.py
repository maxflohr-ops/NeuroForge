"""Fleet web chat runner — serves an agent as a website chat endpoint.

    python web_runner.py archivist [--port 8080]

Generic like runner.py: it loads agents/<name>/, uses the agent's
build_web_system_prompt() (falling back to build_system_prompt()), and
exposes:

    POST /chat      {"message": "...", "visitor": "<any stable id>"}
    GET  /health
    GET  /widget.js  (the embeddable widget, endpoint auto-wired)
    GET  /           (a local demo page)

Per-visitor rolling memory and rate limits ride on the same core services
as Discord. Deploy behind HTTPS (Railway/Fly) and point the widget at it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import os
from pathlib import Path

from aiohttp import web

from core.llm import STANDARD
from core.log import log_event
from runner import build_context

MAX_MESSAGE_CHARS = 500

CHAT_PROMPT = """Conversation so far (newest last):
{context}

The visitor says:
{message}

Reply as the front desk — short, warm, in-world, grounded only in the bible."""

DEMO_PAGE = """<!doctype html><meta charset="utf-8">
<title>front desk — local demo</title>
<body style="background:#141210;color:#E6E0D3;font-family:Georgia,serif;padding:4rem">
<h1 style="font-weight:normal">the estate — front desk demo</h1>
<p>the widget floats bottom-right. this page only exists for local testing.</p>
<script src="/widget.js"></script>
</body>"""


def _visitor_channel(visitor: str) -> int:
    """Stable pseudo-channel id for a visitor string (memory is keyed by int)."""
    return int(hashlib.sha1(visitor.encode()).hexdigest()[:12], 16)


def _cors(response: web.StreamResponse) -> web.StreamResponse:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def build_app(agent_name: str) -> web.Application:
    ctx = build_context(agent_name)
    agent_module = importlib.import_module(f"agents.{agent_name}")
    build_prompt = getattr(
        agent_module, "build_web_system_prompt", None
    ) or getattr(agent_module, "build_system_prompt")
    system_prompt = build_prompt()
    widget_js = (Path(__file__).resolve().parent / "web" / "widget.js").read_text()

    async def chat(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            return _cors(web.json_response({"error": "bad request"}, status=400))
        message = str(payload.get("message", "")).strip()[:MAX_MESSAGE_CHARS]
        visitor = str(payload.get("visitor", "anon"))[:100]
        if not message:
            return _cors(web.json_response({"error": "empty message"}, status=400))

        channel = _visitor_channel(visitor)
        if not ctx.limiter.allow(channel, 0):
            return _cors(
                web.json_response(
                    {"reply": "the desk is helping someone else — give it a minute."},
                    status=429,
                )
            )

        context = "\n".join(
            f"{author}: {content}" for author, content in ctx.memory.recent(channel)
        )
        reply = await ctx.llm.complete(
            STANDARD,
            system_prompt,
            CHAT_PROMPT.format(context=context or "(a new visitor)", message=message),
            max_tokens=400,
        )
        reply = reply.strip() or "that page isn't in the file yet."
        ctx.memory.remember(channel, "visitor", message)
        ctx.memory.remember(channel, "front desk", reply)
        log_event(ctx.log, "web_chat", visitor=visitor[:20], chars=len(message))
        return _cors(web.json_response({"reply": reply}))

    async def health(_request: web.Request) -> web.Response:
        return _cors(web.json_response({"ok": True, "agent": ctx.config.name}))

    async def widget(_request: web.Request) -> web.Response:
        return _cors(web.Response(text=widget_js, content_type="application/javascript"))

    async def demo(_request: web.Request) -> web.Response:
        return web.Response(text=DEMO_PAGE, content_type="text/html")

    async def options(_request: web.Request) -> web.Response:
        return _cors(web.Response())

    app = web.Application()
    app.router.add_post("/chat", chat)
    app.router.add_options("/chat", options)
    app.router.add_get("/health", health)
    app.router.add_get("/widget.js", widget)
    app.router.add_get("/", demo)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="serve one fleet agent as web chat")
    parser.add_argument("agent", help="agent name, e.g. archivist")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)))
    args = parser.parse_args()
    web.run_app(build_app(args.agent), port=args.port)


if __name__ == "__main__":
    main()
