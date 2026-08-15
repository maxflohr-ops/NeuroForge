#!/usr/bin/env python3
"""
Static console build tests.

The property that matters most is negative: the built page must have no way to
launch anything. It is meant to be hosted, and the live commander it mirrors
runs subprocesses.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from commander import profiles, webapp

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
EVENTS = PROJECT_DIR / "commander" / "state" / "events.jsonl"


def sample_events():
    return [
        {"seq": 1, "ts": 1000.0, "type": "run.queued", "run_id": "run_a",
         "agent": "mission"},
        {"seq": 2, "ts": 1000.4, "type": "run.started", "run_id": "run_a",
         "agent": "mission"},
        {"seq": 3, "ts": 1090.0, "type": "run.log", "run_id": "run_a",
         "agent": "research", "line": "hello", "level": "info"},
        {"seq": 4, "ts": 1090.2, "type": "run.finished", "run_id": "run_a",
         "agent": "mission", "status": "ok"},
    ]


class PacingTests(unittest.TestCase):
    def test_schedule_is_monotonic_and_starts_after_a_lead_in(self):
        paced = webapp.pace(sample_events())
        times = [event["at"] for event in paced]
        self.assertEqual(times, sorted(times))
        self.assertGreaterEqual(times[0], webapp.LEAD_IN_MS)

    def test_long_pauses_are_capped_so_the_demo_never_stalls(self):
        paced = webapp.pace(sample_events())
        gaps = [b["at"] - a["at"] for a, b in zip(paced, paced[1:])]
        self.assertTrue(all(gap <= webapp.MAX_GAP_MS for gap in gaps), gaps)

    def test_original_payloads_survive(self):
        paced = webapp.pace(sample_events())
        self.assertEqual(paced[2]["line"], "hello")
        self.assertEqual(paced[3]["type"], "run.finished")


class RewindTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = webapp.idle({
            "fleet": {"agents": [{"id": "research",
                                  "state": {"status": "ok", "last_score": 44}}]},
            "graph": {"ir": {"nodes": [{"id": "research",
                                        "state": {"status": "ok"}}]}},
            "runs": {"runs": [{"id": "run_a", "status": "ok",
                               "params": {"topic": "Beat Anxiety Fast",
                                          "faculty": "Kai Ren"},
                               "stages": [{"name": "x"}], "scores": {"a": 1},
                               "artifacts": ["y"], "started_at": 1, "finished_at": 2}]},
            "autopilot": {"status": "running", "objective": "Something Else",
                          "active_run": "run_a"},
        })

    def test_agents_and_nodes_are_rewound_to_idle(self):
        self.assertEqual(
            self.snapshot["fleet"]["agents"][0]["state"]["status"], "idle")
        self.assertEqual(
            self.snapshot["graph"]["ir"]["nodes"][0]["state"]["status"], "idle")

    def test_the_recorded_run_is_emptied_so_the_replay_fills_it(self):
        run = self.snapshot["runs"]["runs"][0]
        self.assertEqual(run["stages"], [])
        self.assertEqual(run["scores"], {})
        self.assertEqual(run["status"], "queued")
        self.assertIsNone(run["started_at"])

    def test_autopilot_is_held_and_points_at_the_replayed_topic(self):
        pilot = self.snapshot["autopilot"]
        self.assertEqual(pilot["status"], "paused")
        self.assertIsNone(pilot["active_run"])
        self.assertEqual(pilot["objective"], "Beat Anxiety Fast")
        self.assertEqual(pilot["faculty"], "Kai Ren")

    def test_the_source_snapshot_is_not_mutated(self):
        original = {"fleet": {"agents": [{"id": "a", "state": {"status": "ok"}}]}}
        webapp.idle(original)
        self.assertEqual(original["fleet"]["agents"][0]["state"]["status"], "ok")


class SnapshotTests(unittest.TestCase):
    def test_every_endpoint_the_console_boots_against_is_present(self):
        snapshot = webapp.build_snapshot(PROJECT_DIR, "florra_alpha")
        # The console awaits these together; one missing fails the whole boot.
        for key in ("fleet", "graph", "metrics", "runs", "health", "autopilot",
                    "topics"):
            with self.subTest(endpoint=key):
                self.assertIsNotNone(snapshot.get(key), key)
        self.assertTrue(snapshot["graph"]["validation"]["ok"])
        self.assertIn("profile", snapshot["fleet"])


@unittest.skipUnless(EVENTS.exists(), "no recording available")
class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = webapp.build(PROJECT_DIR, "florra_alpha", EVENTS, None, True)

    def test_the_page_is_self_contained(self):
        neutral = self.page.replace('xmlns="http://www.w3.org/2000/svg"', "")
        for forbidden in ('<script src=', '<link rel="stylesheet"', "@import",
                          'src="http', 'href="http'):
            with self.subTest(pattern=forbidden):
                self.assertNotIn(forbidden, neutral)

    def test_it_ships_the_real_console_assets(self):
        app_js = (webapp.WEB_DIR / "app.js").read_text(encoding="utf-8")
        graph_js = (webapp.WEB_DIR / "graph.js").read_text(encoding="utf-8")
        # A forked copy would let the demo drift from the console it shows.
        self.assertIn("class FleetMap", graph_js)
        self.assertIn("class FleetMap", self.page)
        self.assertIn("applyAutopilotEvent", app_js)
        self.assertIn("applyAutopilotEvent", self.page)

    def test_the_transport_is_replaced_before_the_console_loads(self):
        self.assertLess(self.page.index("window.EventSource = class"),
                        self.page.index("class FleetMap"))

    def test_nothing_can_be_dispatched(self):
        """The hosted page must have no path to launching a process."""
        self.assertIn("This is a recording", self.page)
        # No absolute URL to a commander, and no leftover token plumbing that
        # would let it reach one.
        self.assertNotIn("http://127.0.0.1", self.page)
        self.assertNotIn("localhost:8787", self.page)

    def test_it_says_what_it_is(self):
        self.assertIn("recorded · read-only", self.page)
        self.assertIn("Replay mission", self.page)

    def test_fragment_and_standalone_differ_only_in_the_wrapper(self):
        fragment = webapp.build(PROJECT_DIR, "florra_alpha", EVENTS, None, False)
        self.assertTrue(self.page.lstrip().startswith("<!doctype html>"))
        self.assertFalse(fragment.lstrip().startswith("<!doctype"))
        for tag in ("<html", "<head>", "<body>"):
            with self.subTest(tag=tag):
                self.assertNotIn(tag, fragment)

    def test_the_title_carries_the_fleet_name(self):
        profile = profiles.load("florra_alpha")
        self.assertIn(f"<title>{profile.name} Console</title>", self.page)

    def test_the_embedded_recording_is_valid_json(self):
        match = re.search(r"const EVENTS = (\[.*?\]);\n", self.page, re.S)
        self.assertIsNotNone(match, "no embedded recording found")
        events = json.loads(match.group(1))
        self.assertGreater(len(events), 10)
        self.assertTrue(all("at" in event for event in events))


class MissingRecordingTests(unittest.TestCase):
    def test_a_missing_recording_is_an_actionable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as caught:
                webapp.load_events(Path(tmp) / "nope.jsonl")
            self.assertIn("run the commander first", str(caught.exception))

    def test_an_empty_recording_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text("\n\nnot json\n")
            with self.assertRaises(SystemExit):
                webapp.load_events(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
