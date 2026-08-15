#!/usr/bin/env python3
"""
Evidence Agent — smolagents CodeAgent
=====================================
The fleet's non-negotiables say "no fake citations or fabricated studies", but
nothing in the pipeline actually checks a claim against the world. The Research
Agent writes from the model's own knowledge; this agent goes and looks.

Given an artifact, it pulls out the checkable factual claims, searches the web
for each, and writes an evidence table: claim, verdict, and the real URLs that
support or contradict it. That table feeds back to the Research Agent and gives
the QA Agent something to score against.

Why a CodeAgent rather than a tool-calling agent: the work is a loop over many
claims with deduplication and aggregation across results — the thing code is
better at than a sequence of individual tool calls.

    python scripts/evidence_agent.py --topic "Stop Overthinking" \
                                     --file output/stop_overthinking/01_research_brief_x.md

Execution safety
----------------
A CodeAgent writes Python and runs it. This one defaults to a **Docker**
sandbox, never the in-process interpreter. `--executor local` runs generated
code inside this process and is refused unless EVIDENCE_ALLOW_LOCAL=1 is set
deliberately; it is never appropriate for an unattended run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_DIR / "output"

MODEL = "anthropic/claude-sonnet-4-6"
MAX_CLAIMS = 12
MAX_STEPS = 14

# The generated code only ever needs to shuffle text and results around.
AUTHORIZED_IMPORTS = ["json", "re", "collections", "itertools", "statistics"]

EXECUTORS = ("docker", "e2b", "local")


# ─────────────────────────────────────────────
# Fleet log vocabulary
# ─────────────────────────────────────────────

def banner(detail: str) -> None:
    print(f"\n🔎 EVIDENCE AGENT — {detail}", flush=True)


def rule() -> None:
    print("─" * 50, flush=True)


def event(kind: str, **payload) -> None:
    """Structured telemetry the commander's interpreter understands."""
    print("NEUROFORGE_EVENT " + json.dumps({"kind": kind, **payload}), flush=True)


def slug(topic: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", topic.lower())


# ─────────────────────────────────────────────
# Wiring
# ─────────────────────────────────────────────

def require_smolagents():
    """Import smolagents with an actionable message when it is absent."""
    try:
        import smolagents  # noqa: F401
    except ImportError:
        print("❌ smolagents is not installed.", file=sys.stderr)
        print("   pip install smolagents   (or rebuild the Docker image)",
              file=sys.stderr)
        raise SystemExit(3)
    return smolagents


def resolve_executor(requested: str) -> tuple[str, dict]:
    """Pick the sandbox, refusing in-process execution unless unlocked.

    Generated code is untrusted by construction. Docker is the default because
    it needs no third-party account and this project already ships a Dockerfile.
    """
    if requested not in EXECUTORS:
        raise SystemExit(f"unknown executor {requested!r}; choose from {EXECUTORS}")

    if requested == "local":
        if os.getenv("EVIDENCE_ALLOW_LOCAL") != "1":
            print("❌ Refusing --executor local: generated code would run in this "
                  "process.", file=sys.stderr)
            print("   Use --executor docker (default), or set "
                  "EVIDENCE_ALLOW_LOCAL=1 to override for a supervised run.",
                  file=sys.stderr)
            raise SystemExit(4)
        print("⚠️  Running generated code IN THIS PROCESS (EVIDENCE_ALLOW_LOCAL=1). "
              "Never do this unattended.", flush=True)
        return "local", {}

    if requested == "e2b" and not os.getenv("E2B_API_KEY"):
        raise SystemExit("--executor e2b needs E2B_API_KEY in the environment")

    return requested, {}


def build_search_tool():
    """Prefer a keyed search API when one is configured; fall back to DuckDuckGo."""
    from smolagents import ApiWebSearchTool, DuckDuckGoSearchTool

    if os.getenv("SERPER_API_KEY") or os.getenv("SEARCHAPI_API_KEY"):
        return ApiWebSearchTool()

    try:
        return DuckDuckGoSearchTool(max_results=6)
    except ImportError:
        # The keyless fallback carries its own dependency; say which, rather
        # than letting a library traceback stand in for the instruction.
        raise SystemExit(
            "No web search available. Either:\n"
            "  pip install ddgs                       (keyless DuckDuckGo search)\n"
            "  or set SERPER_API_KEY / SEARCHAPI_API_KEY  (keyed search API)"
        )


def build_model():
    """Claude through the SDK the project already depends on.

    smolagents ships no Anthropic model, and its LiteLLM path would drag a
    large dependency tree into the image for no gain — this project already
    has `anthropic`. The subclass is small, and unlike the rest of the fleet it
    reports *real* token counts rather than an estimate.
    """
    import anthropic
    from smolagents import Model
    from smolagents.models import ChatMessage, MessageRole, TokenUsage

    class ClaudeModel(Model):
        def __init__(self, model_id: str, api_key: str, max_tokens: int = 4096):
            super().__init__(model_id=model_id, flatten_messages_as_text=True)
            self.client = anthropic.Anthropic(api_key=api_key)
            self.max_tokens = max_tokens
            self.input_tokens = 0
            self.output_tokens = 0

        @staticmethod
        def _text(content) -> str:
            """smolagents may hand over a string or a list of content blocks."""
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                )
            return "" if content is None else str(content)

        def _split(self, messages) -> tuple[str, list[dict]]:
            """Anthropic takes the system prompt separately and wants
            alternating turns starting with the user."""
            system: list[str] = []
            turns: list[dict] = []
            for message in messages:
                role = getattr(message, "role", None) or (
                    message.get("role") if isinstance(message, dict) else None)
                content = getattr(message, "content", None) if not isinstance(
                    message, dict) else message.get("content")
                role = str(getattr(role, "value", role) or "user").lower()
                text = self._text(content)
                if not text:
                    continue
                if role == "system":
                    system.append(text)
                    continue
                mapped = "assistant" if role == "assistant" else "user"
                if turns and turns[-1]["role"] == mapped:
                    turns[-1]["content"] += "\n\n" + text
                else:
                    turns.append({"role": mapped, "content": text})

            if not turns or turns[0]["role"] != "user":
                turns.insert(0, {"role": "user", "content": "Begin."})
            return "\n\n".join(system), turns

        def generate(self, messages, stop_sequences=None, response_format=None,
                     tools_to_call_from=None, **kwargs) -> "ChatMessage":
            system, turns = self._split(messages)
            request = {
                "model": self.model_id,
                "max_tokens": self.max_tokens,
                "messages": turns,
            }
            if system:
                request["system"] = system
            if stop_sequences:
                request["stop_sequences"] = list(stop_sequences)

            response = self.client.messages.create(**request)
            text = "".join(block.text for block in response.content
                           if getattr(block, "type", None) == "text")

            self.input_tokens += response.usage.input_tokens
            self.output_tokens += response.usage.output_tokens

            return ChatMessage(
                role=MessageRole.ASSISTANT,
                content=text,
                raw=response,
                token_usage=TokenUsage(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                ),
            )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is required")
    return ClaudeModel(MODEL, api_key)


def build_agent(executor_type: str, executor_kwargs: dict, verbose: bool = False):
    from smolagents import CodeAgent, LogLevel, VisitWebpageTool

    model = build_model()

    return CodeAgent(
        tools=[build_search_tool(), VisitWebpageTool()],
        model=model,
        executor_type=executor_type,
        executor_kwargs=executor_kwargs,
        additional_authorized_imports=AUTHORIZED_IMPORTS,
        max_steps=MAX_STEPS,
        name="evidence_agent",
        description="Checks factual claims in fleet artifacts against real sources.",
        instructions=(
            "You verify claims for a content pipeline that forbids fabricated "
            "citations. Never invent a source, a study or a statistic. If you "
            "cannot find real supporting evidence for a claim, say so plainly and "
            "mark it unsupported — an honest 'unsupported' is the correct and "
            "expected answer, not a failure. Every URL you report must be one you "
            "actually retrieved."
        ),
        verbosity_level=LogLevel.INFO if verbose else LogLevel.ERROR,
    )


TASK = """
Verify the factual claims in the artifact below.

Steps:
1. Read the artifact and list the checkable factual claims — statistics, study
   references, mechanisms stated as established fact. Ignore opinion, advice and
   stylistic copy. Cap the list at {max_claims}, keeping the ones a reader would
   most likely challenge.
2. For each claim, search for real supporting or contradicting sources and open
   the promising ones.
3. Return a markdown table with columns: Claim | Verdict | Source URL | Note.
   Verdict is exactly one of: supported, partially supported, unsupported,
   contradicted.
4. Below the table add "## Fabrication risks" listing any claim that reads like a
   citation but has no locatable source. If there are none, say "None found."

Do not invent sources. An unsupported verdict with no URL is correct when the
evidence is not there.

--- ARTIFACT ({label}) ---
{artifact}
""".strip()


def run(args) -> int:
    require_smolagents()
    executor_type, executor_kwargs = resolve_executor(args.executor)

    path = Path(args.file)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    if not path.exists():
        raise SystemExit(f"no such artifact: {path}")

    artifact = path.read_text(encoding="utf-8")
    if len(artifact) > args.max_chars:
        artifact = artifact[: args.max_chars] + "\n\n[truncated]"

    banner(f"Verifying {path.name}")
    rule()
    print(f"  Calling: Evidence Agent")
    print(f"  Model:   {MODEL}")
    print(f"  Sandbox: {executor_type}")
    rule()
    event("stage_start", stage="Evidence Agent", detail=f"sandbox {executor_type}")

    agent = build_agent(executor_type, executor_kwargs, verbose=args.verbose)

    try:
        result = agent.run(TASK.format(artifact=artifact, label=path.name,
                                       max_claims=args.max_claims))
    except Exception as exc:                      # noqa: BLE001 - reported, not swallowed
        print(f"❌ Evidence Agent failed: {exc}", file=sys.stderr)
        event("stage_end", stage="Evidence Agent", status="error")
        return 1
    finally:
        # Docker/E2B sandboxes hold a container open until told otherwise.
        cleanup = getattr(getattr(agent, "python_executor", None), "cleanup", None)
        if callable(cleanup):
            try:
                cleanup()
            except Exception:                     # noqa: BLE001 - best effort
                pass

    report = format_report(args.topic, path, str(result), executor_type)
    out_path = save(args.topic, report)
    print(f"  ✓ Saved: {out_path}")

    verdicts = count_verdicts(str(result))
    event("stage_end", stage="Evidence Agent", status="ok")
    if verdicts:
        summary = " · ".join(f"{k} {v}" for k, v in verdicts.items())
        print(f"\n✅ Evidence complete. {summary}")
    else:
        print("\n✅ Evidence complete.")
    return 0


def format_report(topic: str, source: Path, body: str, executor_type: str) -> str:
    return (
        f"# Evidence Report — {topic}\n\n"
        f"- **Artifact:** `{source.name}`\n"
        f"- **Checked:** {datetime.now().isoformat(timespec='seconds')}\n"
        f"- **Agent:** smolagents CodeAgent · {MODEL} · {executor_type} sandbox\n\n"
        f"> Sources below were retrieved by the agent. Claims marked unsupported "
        f"are claims no source was found for — treat them as needing a citation "
        f"or removal before publishing.\n\n---\n\n{body}\n"
    )


def count_verdicts(body: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for verdict in ("contradicted", "partially supported", "unsupported", "supported"):
        # Longest labels first so "unsupported" is not counted as "supported".
        found = len(re.findall(rf"\|\s*{verdict}\s*\|", body, re.IGNORECASE))
        if found:
            counts[verdict] = found
            body = re.sub(rf"\|\s*{verdict}\s*\|", "| |", body, flags=re.IGNORECASE)
    return counts


def save(topic: str, content: str) -> Path:
    topic_dir = OUTPUT_DIR / slug(topic)
    topic_dir.mkdir(parents=True, exist_ok=True)
    path = topic_dir / f"06_evidence_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    path.write_text(content, encoding="utf-8")
    return path


def selftest(args) -> int:
    """Verify wiring without spending a token: build the agent, do not run it."""
    require_smolagents()
    print("✓ smolagents importable")

    executor_type, _ = resolve_executor(args.executor)
    print(f"✓ executor resolved: {executor_type}")

    from smolagents import CodeAgent, LiteLLMModel  # noqa: F401
    print("✓ CodeAgent and LiteLLMModel importable")

    tool = build_search_tool()
    print(f"✓ search tool: {type(tool).__name__}")

    if os.getenv("ANTHROPIC_API_KEY"):
        agent = build_agent(executor_type, {}, verbose=False)
        print(f"✓ agent built: {len(agent.tools)} tools, max_steps={agent.max_steps}")
    else:
        print("• ANTHROPIC_API_KEY not set — skipped building the live agent")

    print(f"✓ authorized imports: {', '.join(AUTHORIZED_IMPORTS)}")
    print("\n✅ Self-test passed. No model call was made.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Evidence Agent (smolagents)")
    parser.add_argument("--topic", default="", help='Topic, e.g. "Stop Overthinking"')
    parser.add_argument("--file", default="", help="Artifact to verify")
    parser.add_argument("--executor", default=os.getenv("EVIDENCE_EXECUTOR", "docker"),
                        choices=EXECUTORS,
                        help="Sandbox for generated code (default: docker)")
    parser.add_argument("--max-claims", type=int, default=MAX_CLAIMS,
                        dest="max_claims")
    parser.add_argument("--max-chars", type=int, default=18000, dest="max_chars",
                        help="Truncate the artifact beyond this length")
    parser.add_argument("--verbose", action="store_true",
                        help="Stream the agent's reasoning")
    parser.add_argument("--selftest", action="store_true",
                        help="Check wiring without calling the model")
    args = parser.parse_args()

    if args.selftest:
        return selftest(args)
    if not args.topic or not args.file:
        parser.error("--topic and --file are required (or use --selftest)")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
