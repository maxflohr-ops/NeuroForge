#!/usr/bin/env python3
"""
Fleet memory tests.

Memory is an enhancement bolted to an unattended loop, so the properties that
matter are the defensive ones: off unless configured, and never able to stop a
mission no matter how badly the server behaves. Those are tested against a real
HTTP stub rather than a mock, so the wire format is exercised too.
"""

from __future__ import annotations

import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from commander import registry
from commander.memory import MemoryLink, mission_summary

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent


class StubMemory(BaseHTTPRequestHandler):
    """Stands in for a TencentDB Agent Memory server."""

    behaviour = "ok"
    seen: list[dict] = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        StubMemory.seen.append({"path": self.path, "body": body,
                                "auth": self.headers.get("Authorization"),
                                "service": self.headers.get("x-tdai-service-id")})

        if StubMemory.behaviour == "500":
            self.send_error(500, "boom")
            return
        if StubMemory.behaviour == "garbage":
            payload = b"<html>not json</html>"
        elif StubMemory.behaviour == "hang":
            time.sleep(3)
            payload = b"{}"
        elif self.path.endswith("/atomic/search"):
            payload = json.dumps({"items": [
                {"content": "Nova Vale briefs land best opening on a symptom",
                 "background": "from Stop Overthinking"},
                {"content": "Funnel copy scored 36/50 — too many claims"},
                {"content": ""},
            ]}).encode()
        elif self.path.endswith("/core/read"):
            payload = json.dumps({"content": "# Fleet profile\nships weekly"}).encode()
        else:
            payload = json.dumps({"accepted_ids": ["mem-1"]}).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class MemoryHarness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), StubMemory)
        cls.server.daemon_threads = True
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.endpoint = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        StubMemory.behaviour = "ok"
        StubMemory.seen = []

    def link(self, **kwargs):
        return MemoryLink(endpoint=self.endpoint, api_key="k",
                          service_id="space-1", **kwargs)


class DisabledTests(unittest.TestCase):
    """With nothing configured the fleet must behave exactly as before."""

    def test_no_endpoint_means_disabled(self):
        link = MemoryLink()
        self.assertFalse(link.enabled)

    def test_every_operation_is_a_no_op(self):
        link = MemoryLink()
        self.assertEqual(link.recall("anything"), "")
        self.assertEqual(link.profile(), "")
        self.assertFalse(link.record("s", "summary"))
        self.assertFalse(link.health())
        self.assertEqual(link.failures, 0, "a disabled link must not count failures")

    def test_from_env_reads_the_documented_variables(self):
        link = MemoryLink.from_env({"MEMORY_ENDPOINT": "http://host:8420/",
                                    "MEMORY_API_KEY": "key",
                                    "MEMORY_SERVICE_ID": "space",
                                    "MEMORY_AGENT_ID": "ffa"})
        self.assertTrue(link.enabled)
        self.assertEqual(link.endpoint, "http://host:8420", "trailing slash kept")
        self.assertEqual(link.agent_id, "ffa")

    def test_a_bad_timeout_falls_back_rather_than_raising(self):
        link = MemoryLink.from_env({"MEMORY_ENDPOINT": "http://h",
                                    "MEMORY_TIMEOUT": "not-a-number"})
        self.assertGreater(link.timeout, 0)


class ProtocolTests(MemoryHarness):
    def test_recall_reaches_the_documented_endpoint_with_auth(self):
        self.link().recall("Stop Overthinking")
        call = StubMemory.seen[-1]
        self.assertEqual(call["path"], "/v2/atomic/search")
        self.assertEqual(call["auth"], "Bearer k")
        self.assertEqual(call["service"], "space-1")
        self.assertEqual(call["body"]["query"], "Stop Overthinking")

    def test_record_posts_a_conversation(self):
        self.assertTrue(self.link().record("run_1", "summary line", "detail"))
        call = StubMemory.seen[-1]
        self.assertEqual(call["path"], "/v2/conversation/add")
        self.assertEqual(call["body"]["session_id"], "run_1")
        self.assertEqual(len(call["body"]["messages"]), 2)

    def test_the_agent_id_scopes_every_call(self):
        self.link(agent_id="ffa").recall("x")
        self.assertEqual(StubMemory.seen[-1]["body"]["agent_id"], "ffa")

    def test_recall_renders_items_as_usable_context(self):
        recalled = self.link().recall("Stop Overthinking")
        self.assertIn("Nova Vale briefs land best", recalled)
        self.assertIn("(from Stop Overthinking)", recalled)
        self.assertIn("36/50", recalled)

    def test_empty_items_are_dropped_not_rendered_as_blanks(self):
        recalled = self.link().recall("x")
        self.assertNotIn("- \n", recalled)
        self.assertEqual(len(recalled.strip().split("\n")), 3, recalled)

    def test_recall_is_capped_so_it_fits_the_pipeline(self):
        from commander import memory
        recalled = self.link().recall("x")
        self.assertLessEqual(len(recalled), memory.MAX_RECALL_CHARS)

    def test_profile_reads_core_memory(self):
        self.assertIn("Fleet profile", self.link().profile())
        self.assertEqual(StubMemory.seen[-1]["path"], "/v2/core/read")


class FailOpenTests(MemoryHarness):
    """However the server misbehaves, the fleet keeps running."""

    def test_a_server_error_degrades_to_no_context(self):
        StubMemory.behaviour = "500"
        link = self.link()
        self.assertEqual(link.recall("x"), "")
        self.assertFalse(link.record("s", "x"))
        self.assertEqual(link.failures, 2)

    def test_a_non_json_response_is_survived(self):
        StubMemory.behaviour = "garbage"
        self.assertEqual(self.link().recall("x"), "")

    def test_a_slow_server_is_abandoned_not_waited_on(self):
        StubMemory.behaviour = "hang"
        link = self.link(timeout=0.4)
        started = time.time()
        self.assertEqual(link.recall("x"), "")
        self.assertLess(time.time() - started, 2.5, "recall blocked the caller")

    def test_an_unreachable_server_is_survived(self):
        link = MemoryLink(endpoint="http://127.0.0.1:1", api_key="k",
                          service_id="s", timeout=0.5)
        self.assertEqual(link.recall("x"), "")
        self.assertFalse(link.health())

    def test_errors_are_reported_rather_than_swallowed_silently(self):
        StubMemory.behaviour = "500"
        seen: list[str] = []
        self.link(on_error=seen.append).recall("x")
        self.assertTrue(seen)
        self.assertIn("memory unavailable", seen[0])


class SummaryTests(unittest.TestCase):
    def test_summary_names_the_weakest_and_strongest_stage(self):
        summary = mission_summary("Stop Overthinking", "Dr. Nova Vale",
                                  {"Research Brief": 42, "Funnel Copy": 36},
                                  "complete")
        self.assertIn("Stop Overthinking", summary)
        self.assertIn("Dr. Nova Vale", summary)
        self.assertIn("weakest stage Funnel Copy at 36/50", summary)
        self.assertIn("strongest Research Brief at 42/50", summary)

    def test_a_scoreless_run_still_summarises(self):
        summary = mission_summary("T", "Kai Ren", {}, "complete")
        self.assertIn("no QA scores recorded", summary)


class DispatchIntegrationTests(unittest.TestCase):
    def test_recalled_prose_survives_parameter_validation(self):
        """Recall is multi-line prose; the topic pattern would have rejected it."""
        recalled = ("Prior work by this fleet on related topics:\n"
                    "- Nova Vale briefs land best opening on a symptom "
                    "(from Stop Overthinking)\n- Funnel copy scored 36/50.")
        argv = registry.get("mission").build_argv(
            {"topic": "Beat Anxiety Fast", "faculty": "Dr. Nova Vale",
             "audience_notes": recalled})
        self.assertIn("--audience_notes", argv)
        self.assertIn(recalled, argv)

    def test_control_characters_are_still_rejected(self):
        with self.assertRaises(ValueError):
            registry.get("mission").build_argv(
                {"topic": "T", "faculty": "Kai Ren",
                 "audience_notes": "bad\x00null"})

    def test_oversized_context_is_rejected(self):
        with self.assertRaises(ValueError):
            registry.get("mission").build_argv(
                {"topic": "T", "faculty": "Kai Ren",
                 "audience_notes": "x" * 5000})

    def test_the_memory_service_appears_on_the_map_as_a_dependency(self):
        from commander import graph
        ir = graph.build()
        self.assertTrue(graph.validate(ir)["ok"])
        edges = {(e["from"], e["to"]): e for e in ir["edges"]}
        self.assertEqual(edges[("commander", "agent_memory")]["kind"],
                         graph.EDGE_DEPENDENCY)


class AutopilotMemoryTests(unittest.TestCase):
    """The loop must not change shape when memory is absent."""

    def test_an_autopilot_without_memory_configured_is_inert(self):
        from commander.autopilot import Autopilot
        from commander.eventbus import EventBus
        from commander.profiles import load
        from commander.runner import Runner
        from commander.store import FleetStore
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            bus = EventBus(None)
            store = FleetStore(PROJECT_DIR, state)
            pilot = Autopilot(load("florra_alpha"),
                              Runner(PROJECT_DIR, bus, store), store, bus, state,
                              memory=MemoryLink())
            self.assertFalse(pilot.memory.enabled)
            self.assertFalse(pilot.snapshot()["memory"]["enabled"])
            # Remembering a mission with no link must be a silent no-op.
            pilot._remember({"id": "run_1", "scores": {}, "params": {}},
                            "T", "complete")


if __name__ == "__main__":
    unittest.main(verbosity=2)
