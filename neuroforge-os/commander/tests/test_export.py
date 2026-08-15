#!/usr/bin/env python3
"""
Export tests.

The point of an exported map is that it survives on its own — no network, no
scripts, no host stylesheet — and that it never ships a picture the validator
would have rejected.
"""

from __future__ import annotations

import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from commander import export, graph, profiles, registry


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ir = graph.build()
        cls.profile = profiles.load("florra_alpha")

    def test_svg_fragment_is_well_formed_xml(self):
        root = ET.fromstring(export.render_svg(self.ir))
        self.assertTrue(root.tag.endswith("svg"))
        self.assertIn("viewBox", root.attrib)

    def test_every_agent_is_drawn(self):
        svg = export.render_svg(self.ir)
        for spec in registry.AGENTS:
            with self.subTest(agent=spec.id):
                self.assertIn(export._truncate(spec.name, 20), svg)

    def test_edge_classes_can_be_filtered(self):
        flow_only = export.render_svg(self.ir, include=("flow",))
        self.assertNotIn("fm-edge--review", flow_only)
        self.assertNotIn("fm-edge--dependency", flow_only)

        everything = export.render_svg(self.ir)
        self.assertIn("fm-edge--review", everything)
        self.assertIn("fm-edge--dependency", everything)

    def test_fragment_carries_no_styles_and_standalone_does(self):
        # Inline in a host page, the page owns the colours.
        self.assertNotIn("<style>", export.render_svg(self.ir))
        self.assertIn("<style>", export.render_svg(self.ir, standalone=True))

    def test_output_is_self_contained(self):
        """Nothing is fetched at render time.

        The SVG namespace URI is a name, not a request, so it is excluded —
        everything that would actually hit the network is not.
        """
        page = export.render_html(self.ir, self.profile)
        neutral = page.replace('xmlns="http://www.w3.org/2000/svg"', "")
        for forbidden in ("<script", "@import", "url(http", 'src="http',
                          'href="http', "//fonts.", "<iframe", "<link"):
            with self.subTest(pattern=forbidden):
                self.assertNotIn(forbidden, neutral)

    def test_marker_references_stay_inside_the_document(self):
        svg = export.render_svg(self.ir)
        for reference in re.findall(r'marker-end="([^"]+)"', svg):
            with self.subTest(reference=reference):
                self.assertTrue(reference.startswith("url(#"), reference)

    def test_both_themes_are_defined_for_every_squad(self):
        css = export.stylesheet()
        for squad in registry.SQUADS:
            with self.subTest(squad=squad.id):
                self.assertIn(squad.accent, css)
                self.assertIn(squad.accent_light or squad.accent, css)
        # The un-stamped default, the OS preference and the explicit toggle.
        self.assertIn('@media (prefers-color-scheme: dark)', css)
        self.assertIn(':root:not([data-theme="light"])', css)
        self.assertIn(':root[data-theme="dark"]', css)

    def test_accessible_labelling(self):
        svg = export.render_svg(self.ir, description="A fleet of agents")
        self.assertIn('role="img"', svg)
        self.assertIn('aria-label="A fleet of agents"', svg)
        self.assertIn("<title>", svg)

    def test_labels_are_escaped(self):
        hostile = {**self.ir}
        hostile["nodes"] = [dict(n) for n in self.ir["nodes"]]
        hostile["nodes"][0]["label"] = '<script>bad()</script>'
        svg = export.render_svg(hostile)
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)

    def test_html_reports_real_counts(self):
        page = export.render_html(self.ir, self.profile)
        self.assertIn(self.profile.name, page)
        self.assertIn(self.profile.callsign, page)
        self.assertIn(f">{len(self.ir['nodes'])}</b>", page)
        self.assertIn(f">{len(self.profile.backlog)}</b>", page)

    def test_written_files_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg_path = Path(tmp) / "fleet.svg"
            html_path = Path(tmp) / "fleet.html"
            svg_path.write_text(
                export.render_svg(self.ir, standalone=True), encoding="utf-8")
            html_path.write_text(
                export.render_html(self.ir, self.profile), encoding="utf-8")
            self.assertGreater(svg_path.stat().st_size, 5000)
            self.assertGreater(html_path.stat().st_size, 5000)
            ET.fromstring(svg_path.read_text(encoding="utf-8"))

    def test_paths_are_finite_numbers(self):
        svg = export.render_svg(self.ir)
        for value in re.findall(r"[-\d.]+(?=[ ,])", svg):
            if value.strip("-.") == "":
                continue
            with self.subTest(value=value):
                self.assertNotIn("nan", value.lower())
                self.assertNotIn("inf", value.lower())

    def test_an_unsound_map_is_not_exportable(self):
        broken = {**self.ir, "nodes": [dict(n) for n in self.ir["nodes"]]}
        broken["nodes"][1]["x"] = broken["nodes"][0]["x"]
        broken["nodes"][1]["y"] = broken["nodes"][0]["y"]
        self.assertFalse(graph.validate(broken)["ok"],
                         "the exporter's guard relies on this staying an error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
