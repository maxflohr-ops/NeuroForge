#!/usr/bin/env python3
"""
Fleet profile and autopilot tests.

The autopilot is driven by calling `tick()` directly rather than by letting its
thread run, so each decision is asserted deterministically instead of waited
for. The safety rails get the most coverage — they are the part that must not
regress.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from commander import autopilot as ap
from commander import profiles, registry
from commander.autopilot import Autopilot
from commander.eventbus import EventBus
from commander.runner import Runner
from commander.store import ERROR, FleetStore, OK

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault("COMMANDER_SIM_SPEED", "60")


class ProfileTests(unittest.TestCase):
    def test_every_shipped_profile_loads_and_validates(self):
        self.assertIn("neuroforge", profiles.available())
        self.assertIn("florra_alpha", profiles.available())
        for fleet_id in profiles.available():
            with self.subTest(fleet=fleet_id):
                profiles.load(fleet_id)  # raises if unsound

    def test_florra_alpha_is_derived_from_neuroforge(self):
        florra = profiles.load("florra_alpha")
        base = profiles.load("neuroforge")
        self.assertEqual(florra.derived_from, "neuroforge")
        self.assertEqual(florra.name, "Florra Fleet Alpha")
        self.assertEqual(florra.callsign, "FFA")
        # Inherits the mission book it did not restate…
        self.assertEqual([o.topic for o in florra.backlog],
                         [o.topic for o in base.backlog])
        # …and overrides the operating policy it did.
        self.assertNotEqual(florra.autopilot.budget_usd, base.autopilot.budget_usd)
        self.assertTrue(florra.autopilot.enabled)

    def test_florra_alpha_ships_safe(self):
        policy = profiles.load("florra_alpha").autopilot
        self.assertEqual(policy.mode, "simulate",
                         "a shipped fleet must not default to spending money")
        self.assertFalse(policy.optimize_applies,
                         "a shipped fleet must not rewrite its own prompts unasked")
        self.assertGreater(policy.budget_usd, 0)
        self.assertGreaterEqual(policy.qa_floor, 35)

    def test_every_backlog_objective_is_dispatchable(self):
        for fleet_id in profiles.available():
            profile = profiles.load(fleet_id)
            for objective in profile.backlog:
                with self.subTest(fleet=fleet_id, topic=objective.topic):
                    argv = registry.get("mission").build_argv(objective.mission_params())
                    self.assertIn(objective.topic, argv)
                    self.assertIn(objective.faculty, registry.FACULTY)

    def test_unknown_autopilot_settings_are_rejected(self):
        with self.assertRaises(ValueError):
            profiles.AutopilotPolicy.from_dict({"budget_usd": 5, "yolo": True})

    def test_policy_rails_are_enforced(self):
        for bad in ({"mode": "yolo"}, {"budget_usd": 0}, {"cadence_seconds": 1},
                    {"qa_floor": 99}, {"daily_mission_cap": 0}, {"optimize_every": 0}):
            with self.subTest(setting=bad):
                with self.assertRaises(ValueError):
                    profiles.AutopilotPolicy.from_dict(bad)

    def test_circular_inheritance_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = profiles.FLEET_DIR
            try:
                profiles.FLEET_DIR = Path(tmp)
                (Path(tmp) / "fleet_a.json").write_text(json.dumps(
                    {"id": "fleet_a", "name": "A", "callsign": "A",
                     "derived_from": "fleet_b"}))
                (Path(tmp) / "fleet_b.json").write_text(json.dumps(
                    {"id": "fleet_b", "name": "B", "callsign": "B",
                     "derived_from": "fleet_a"}))
                with self.assertRaises(ValueError) as caught:
                    profiles.load("fleet_a")
                self.assertIn("circular", str(caught.exception))
            finally:
                profiles.FLEET_DIR = original

    def test_clone_writes_a_derived_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = profiles.FLEET_DIR
            try:
                target = Path(tmp)
                for name in ("neuroforge", "florra_alpha"):
                    (target / f"{name}.json").write_text(
                        (original / f"{name}.json").read_text())
                profiles.FLEET_DIR = target
                profiles.clone("florra_alpha", "florra_beta", name="Florra Fleet Beta")
                clone = profiles.load("florra_beta")
                self.assertEqual(clone.name, "Florra Fleet Beta")
                self.assertEqual(clone.derived_from, "florra_alpha")
                self.assertFalse(clone.autopilot.enabled, "a clone must not self-start")
                self.assertEqual([o.topic for o in clone.backlog],
                                 [o.topic for o in profiles.load("florra_alpha").backlog])
                with self.assertRaises(FileExistsError):
                    profiles.clone("florra_alpha", "florra_beta")
            finally:
                profiles.FLEET_DIR = original


class AutopilotHarness(unittest.TestCase):
    """Shared fixture: a real runner and store, a hand-driven autopilot."""

    def build(self, **policy_overrides) -> Autopilot:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        state_dir = Path(self.tmp.name)

        self.bus = EventBus(state_dir / "events.jsonl")
        self.store = FleetStore(PROJECT_DIR, state_dir)
        self.runner = Runner(PROJECT_DIR, self.bus, self.store,
                             max_concurrent=1, simulate=True)
        self.addCleanup(self.runner.shutdown, 15)

        base = profiles.load("florra_alpha")
        defaults = {"enabled": True, "mode": "simulate", "cadence_seconds": 30,
                    "skip_completed": False}
        profile = replace(base, autopilot=replace(base.autopilot,
                                                  **{**defaults, **policy_overrides}))
        pilot = Autopilot(profile, self.runner, self.store, self.bus, state_dir)
        pilot.state["status"] = ap.RUNNING
        return pilot

    def run_one_mission(self, pilot: Autopilot, timeout: float = 30.0) -> None:
        """Tick until the in-flight run is accounted for."""
        pilot.tick()
        self.assertIsNotNone(pilot.state["active_run"], "no mission was dispatched")
        deadline = time.time() + timeout
        while pilot.state["active_run"] and time.time() < deadline:
            time.sleep(0.1)
            pilot.tick()
        self.assertIsNone(pilot.state["active_run"], "mission never settled")


class AutopilotLoopTests(AutopilotHarness):
    def test_a_mission_is_dispatched_and_completed(self):
        pilot = self.build()
        first = pilot.current_objective()
        self.run_one_mission(pilot)
        self.assertEqual(pilot.state["missions"], 1)
        self.assertEqual(pilot.state["completed"], [first.slug])
        self.assertEqual(pilot.state["cursor"], 1)
        self.assertEqual(pilot.state["failures"], 0)

    def test_cadence_holds_the_next_mission_back(self):
        pilot = self.build(cadence_seconds=3600)
        self.run_one_mission(pilot)
        pilot.tick()
        self.assertIsNone(pilot.state["active_run"],
                          "autopilot ignored its own cadence")
        self.assertGreater(pilot.state["next_action_at"], time.time() + 3000)

    def test_completed_topics_are_skipped_in_one_pass(self):
        # Five topics already have full output on disk in this repo.
        pilot = self.build(skip_completed=True, cadence_seconds=3600)
        pilot.tick()
        self.assertGreaterEqual(len(pilot.state["preexisting"]), 1)
        self.assertEqual(pilot.state["cursor"],
                         len(pilot.state["preexisting"]))
        self.assertIsNotNone(pilot.state["active_run"],
                             "should have reached live work in the same tick")

    def test_simulated_missions_do_not_move_the_spend_estimate(self):
        pilot = self.build()
        self.run_one_mission(pilot)
        self.assertEqual(pilot.state["spend_estimate"], 0.0)
        self.assertEqual(pilot.state["today_missions"], 1)

    def test_the_optimizer_runs_on_cadence(self):
        pilot = self.build(optimize_every=1)
        self.run_one_mission(pilot)
        pilot.state["next_action_at"] = 0.0
        pilot.tick()
        self.assertEqual(pilot.state["active_kind"], "optimize")
        deadline = time.time() + 30
        while pilot.state["active_run"] and time.time() < deadline:
            time.sleep(0.1)
            pilot.tick()
        self.assertEqual(len(pilot.state["optimizations"]), 1)
        self.assertEqual(pilot.state["optimizations"][0]["applied"], False)

    def test_state_survives_a_restart(self):
        pilot = self.build()
        self.run_one_mission(pilot)
        reopened = Autopilot(pilot.profile, self.runner, self.store, self.bus,
                             pilot.state_path.parent)
        self.assertEqual(reopened.state["cursor"], pilot.state["cursor"])
        self.assertEqual(reopened.state["completed"], pilot.state["completed"])
        self.assertIsNone(reopened.state["active_run"],
                          "an interrupted run must not look live after a restart")


class AutopilotRailTests(AutopilotHarness):
    def test_budget_ceiling_stops_the_fleet(self):
        pilot = self.build(mode="live", budget_usd=0.20)
        pilot.state["spend_estimate"] = 0.19
        pilot.tick()
        self.assertEqual(pilot.state["status"], ap.BUDGET_REACHED)
        self.assertIsNone(pilot.state["active_run"], "dispatched past the ceiling")

    def test_the_fleet_cannot_restart_itself_past_the_ceiling(self):
        pilot = self.build(mode="live", budget_usd=0.20)
        pilot.state["spend_estimate"] = 0.19
        pilot.tick()
        pilot.start()
        self.assertEqual(pilot.state["status"], ap.BUDGET_REACHED)

    def test_raising_the_budget_is_an_operator_action(self):
        pilot = self.build(mode="live", budget_usd=0.20)
        pilot.state["spend_estimate"] = 0.19
        pilot.tick()
        with self.assertRaises(ValueError):
            pilot.raise_budget(0.10)          # below what is already spent
        pilot.raise_budget(5.0)
        self.assertEqual(pilot.state["status"], ap.PAUSED)
        pilot.start()
        self.assertEqual(pilot.state["status"], ap.RUNNING)

    def test_daily_cap_stops_dispatch_and_resets_the_next_day(self):
        pilot = self.build(daily_mission_cap=1)
        pilot.state["today_missions"] = 1
        pilot.tick()
        self.assertEqual(pilot.state["status"], ap.CAPPED)
        pilot.state["day"] = "1999-01-01"
        pilot.tick()
        self.assertEqual(pilot.state["today_missions"], 0)
        self.assertNotEqual(pilot.state["status"], ap.CAPPED)

    def test_weak_scores_are_reworked_then_quarantined(self):
        pilot = self.build(qa_floor=50, rework_attempts=1)
        first = pilot.current_objective()

        self.run_one_mission(pilot)
        self.assertEqual(pilot.state["cursor"], 0, "rework should retry the topic")
        self.assertEqual(pilot.state["attempts"][first.slug], 1)
        self.assertEqual(pilot.state["quarantined"], [])

        pilot.state["next_action_at"] = 0.0
        self.run_one_mission(pilot)
        self.assertEqual(pilot.state["quarantined"], [first.slug])
        self.assertEqual(pilot.state["cursor"], 1)
        self.assertEqual(pilot.state["completed"], [],
                         "weak work must never count as complete")

    def test_repeated_failures_halt_the_fleet(self):
        pilot = self.build(max_consecutive_failures=2, backoff_seconds=30)
        pilot._fail("boom")
        self.assertEqual(pilot.state["status"], ap.BACKOFF)
        self.assertGreater(pilot.state["next_action_at"], time.time())
        pilot._fail("boom again")
        self.assertEqual(pilot.state["status"], ap.HALTED)

        pilot.tick()
        self.assertIsNone(pilot.state["active_run"], "a halted fleet kept working")

    def test_backoff_expires_back_into_running(self):
        pilot = self.build(max_consecutive_failures=5, backoff_seconds=30)
        pilot._fail("transient")
        pilot.state["next_action_at"] = time.time() - 1
        pilot.tick()
        self.assertEqual(pilot.state["status"], ap.RUNNING)

    def test_pause_stops_dispatch(self):
        pilot = self.build()
        pilot.pause()
        pilot.tick()
        self.assertIsNone(pilot.state["active_run"])
        self.assertEqual(pilot.state["status"], ap.PAUSED)

    def test_an_exhausted_mission_book_ends_cleanly(self):
        pilot = self.build()
        pilot.state["cursor"] = len(pilot.profile.backlog)
        pilot.tick()
        self.assertEqual(pilot.state["status"], ap.BACKLOG_EMPTY)

    def test_a_failed_run_counts_as_a_failure(self):
        pilot = self.build()
        pilot.tick()
        run_id = pilot.state["active_run"]
        deadline = time.time() + 30
        while self.store.get_run(run_id)["status"] in ("queued", "running") \
                and time.time() < deadline:
            time.sleep(0.1)
        self.store.update_run(run_id, status=ERROR, error="synthetic failure")
        pilot.tick()
        self.assertEqual(pilot.state["failures"], 1)
        self.assertEqual(pilot.state["status"], ap.BACKOFF)

    def test_disabled_profiles_never_resume_into_running(self):
        pilot = self.build(enabled=True)
        pilot.state["status"] = ap.RUNNING
        pilot._persist()
        held = replace(pilot.profile,
                       autopilot=replace(pilot.profile.autopilot, enabled=False))
        reopened = Autopilot(held, self.runner, self.store, self.bus,
                             pilot.state_path.parent)
        self.assertEqual(reopened.state["status"], ap.PAUSED)


class AutopilotReportingTests(AutopilotHarness):
    def test_snapshot_reports_what_the_console_needs(self):
        pilot = self.build()
        snapshot = pilot.snapshot()
        for key in ("fleet", "status", "mode", "objective", "backlog_total",
                    "settled", "spend_estimate", "budget_usd", "budget_remaining",
                    "missions_affordable", "next_action_at", "qa_floor"):
            self.assertIn(key, snapshot)
        self.assertEqual(snapshot["fleet"]["name"], "Florra Fleet Alpha")
        self.assertEqual(snapshot["fleet"]["derived_from"], "neuroforge")

    def test_progress_counts_pre_existing_work(self):
        pilot = self.build(skip_completed=True, cadence_seconds=3600)
        pilot.tick()
        snapshot = pilot.snapshot()
        self.assertEqual(
            snapshot["settled"],
            snapshot["completed"] + snapshot["preexisting"] + snapshot["quarantined"])
        self.assertGreater(snapshot["settled"], 0)

    def test_decisions_are_published_as_events(self):
        pilot = self.build()
        self.run_one_mission(pilot)
        types = {event["type"] for event in self.bus.replay(0, limit=5000)}
        self.assertIn("autopilot.dispatched", types)
        self.assertIn("autopilot.completed", types)

    def test_skip_advances_past_the_current_objective(self):
        pilot = self.build(cadence_seconds=3600)
        first = pilot.current_objective()
        pilot.skip()
        self.assertNotEqual(pilot.current_objective().topic, first.topic)


if __name__ == "__main__":
    unittest.main(verbosity=2)
