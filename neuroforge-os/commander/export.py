#!/usr/bin/env python3
"""
Map Export
==========
Renders the validated architecture IR as a standalone picture: an SVG file, or
a self-contained HTML page with a legend and roster. Nothing external is
referenced — no scripts, no fonts, no images — so the output can be committed,
attached to a doc, or opened from a filesystem years from now.

The map is validated before it is written. An unsound IR is an error, not a
crooked diagram.

    python -m commander.export --format svg  --out docs/fleet.svg
    python -m commander.export --format html --out docs/fleet.html
    python -m commander.export --format svg  --include flow --out docs/flow.svg

Colour is applied by CSS custom properties per squad rather than baked into
the shapes, so one fragment renders correctly on a light or a dark ground.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from . import graph, profiles, registry

ALL_KINDS = ("flow", "review", "dependency")


def _corner_path(points: list[list[float]], radius: float = 9.0) -> str:
    """Orthogonal polyline with rounded corners, as SVG path data."""
    if len(points) < 2:
        return ""
    parts = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    for index in range(1, len(points) - 1):
        px, py = points[index - 1]
        cx, cy = points[index]
        nx, ny = points[index + 1]
        into = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5 or 1.0
        out = ((nx - cx) ** 2 + (ny - cy) ** 2) ** 0.5 or 1.0
        r = min(radius, into / 2, out / 2)
        if r < 1:
            parts.append(f"L {cx:.1f} {cy:.1f}")
            continue
        parts.append(f"L {cx - (cx - px) / into * r:.1f} {cy - (cy - py) / into * r:.1f}")
        parts.append(f"Q {cx:.1f} {cy:.1f} "
                     f"{cx + (nx - cx) / out * r:.1f} {cy + (ny - cy) / out * r:.1f}")
    parts.append(f"L {points[-1][0]:.1f} {points[-1][1]:.1f}")
    return " ".join(parts)


def _curve_path(points: list[list[float]]) -> str:
    (ax, ay), (c1x, c1y), (c2x, c2y), (bx, by) = points
    return (f"M {ax:.1f} {ay:.1f} C {c1x:.1f} {c1y:.1f}, "
            f"{c2x:.1f} {c2y:.1f}, {bx:.1f} {by:.1f}")


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[:limit - 1]}…"


def stylesheet(scope: str = "") -> str:
    """CSS for the map fragment. Pass a scope selector to namespace it."""
    squad_vars = "\n".join(
        f"{scope}.sq-{squad.id} {{ --sq: {squad.accent_light or squad.accent}; }}"
        for squad in registry.SQUADS
    )
    squad_vars_dark = "\n".join(
        f"  {scope}.sq-{squad.id} {{ --sq: {squad.accent}; }}"
        for squad in registry.SQUADS
    )
    return f"""
{scope}.fleetmap {{
  --fm-ink: #0b0b0b;
  --fm-ink-2: #52514e;
  --fm-muted: #898781;
  --fm-rule: #c3c2b7;
  --fm-hairline: #e1e0d9;
  --fm-surface: #fcfcfb;
  --fm-node: #ffffff;
}}
{squad_vars}

@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {scope}.fleetmap {{
    --fm-ink: #ffffff;
    --fm-ink-2: #c3c2b7;
    --fm-muted: #898781;
    --fm-rule: #383835;
    --fm-hairline: #2c2c2a;
    --fm-surface: #1a1a19;
    --fm-node: #212120;
  }}
{squad_vars_dark.replace(scope + '.sq-', ':root:not([data-theme="light"]) ' + scope + '.sq-')}
}}

:root[data-theme="dark"] {scope}.fleetmap {{
  --fm-ink: #ffffff;
  --fm-ink-2: #c3c2b7;
  --fm-muted: #898781;
  --fm-rule: #383835;
  --fm-hairline: #2c2c2a;
  --fm-surface: #1a1a19;
  --fm-node: #212120;
}}
{squad_vars_dark.replace(scope + '.sq-', ':root[data-theme="dark"] ' + scope + '.sq-')}

{scope}.fleetmap {{ display: block; max-width: 100%; height: auto; }}
{scope}.fm-lane-rule {{ stroke: var(--sq); stroke-width: 2; stroke-linecap: round; }}
{scope}.fm-lane-label {{
  fill: var(--fm-ink-2); font-size: 10.5px; letter-spacing: 0.08em;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
{scope}.fm-node-box {{ fill: var(--fm-node); stroke: var(--fm-rule); stroke-width: 1; }}
{scope}.fm-node-accent {{ fill: var(--sq); }}
{scope}.fm-node-glyph {{ fill: var(--sq); font-size: 13px; }}
{scope}.fm-node-label {{ fill: var(--fm-ink); font-size: 12px; font-weight: 600; }}
{scope}.fm-node-sub {{
  fill: var(--fm-muted); font-size: 9.5px; letter-spacing: 0.04em;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
{scope}.fm-node--unconfigured .fm-node-box {{ stroke-dasharray: 3 3; }}
{scope}.fm-edge {{
  fill: none; stroke: var(--fm-rule); stroke-width: 1.5;
  stroke-linejoin: round; stroke-linecap: round;
}}
{scope}.fm-edge--review {{ stroke: #ec835a; stroke-width: 1.2; opacity: 0.5; stroke-dasharray: 2 4; }}
{scope}.fm-edge--dependency {{ stroke: var(--fm-muted); stroke-width: 1.2; opacity: 0.38; stroke-dasharray: 1 5; }}
{scope}.fm-edge-label {{
  fill: var(--fm-muted); font-size: 10px; text-anchor: middle;
  dominant-baseline: middle;
}}
{scope}.fm-edge-label-bg {{ fill: var(--fm-surface); }}
""".strip()


def render_svg(ir: dict[str, Any], include: tuple[str, ...] = ALL_KINDS,
               standalone: bool = False, title: str = "Agent fleet",
               description: str = "") -> str:
    """The `<svg>` fragment. With standalone=True it carries its own styles."""
    kinds = set(include)
    parts: list[str] = []

    header = (f'<svg xmlns="http://www.w3.org/2000/svg" '
              f'viewBox="0 0 {ir["width"]} {ir["height"]}" '
              f'class="fleetmap" role="img" '
              f'aria-label="{html.escape(description or title)}">')
    parts.append(header)
    parts.append(f"  <title>{html.escape(title)}</title>")

    parts.append("""  <defs>
    <marker id="fm-arrow" viewBox="0 0 8 8" refX="7" refY="4"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <polygon points="0,0 8,4 0,8" fill="currentColor" />
    </marker>
  </defs>""")

    if standalone:
        parts.append(f"  <style>\n{stylesheet()}\n  </style>")

    # Lane headers
    parts.append('  <g class="fm-lanes">')
    for lane in ir["lanes"]:
        parts.append(
            f'    <g class="sq-{lane["id"]}">'
            f'<line class="fm-lane-rule" x1="{lane["x"]}" y1="{lane["y"] + 7}" '
            f'x2="{lane["x"] + 26}" y2="{lane["y"] + 7}" />'
            f'<text class="fm-lane-label" x="{lane["x"] + 34}" y="{lane["y"] + 11}">'
            f'{html.escape(lane["name"].upper())}</text></g>'
        )
    parts.append("  </g>")

    # Edges, quietest class first so work reads on top
    parts.append('  <g class="fm-edges">')
    for kind in ("dependency", "review", "flow"):
        if kind not in kinds:
            continue
        for edge in ir["edges"]:
            if edge["kind"] != kind:
                continue
            data = (_curve_path(edge["points"]) if edge["render"] == "curve"
                    else _corner_path(edge["points"]))
            suffix = "" if kind == "flow" else f" fm-edge--{kind}"
            parts.append(
                f'    <path class="fm-edge{suffix}" d="{data}" '
                f'marker-end="url(#fm-arrow)" />'
            )
    parts.append("  </g>")

    # Edge labels sit above the routes but below the nodes
    if "flow" in kinds:
        parts.append('  <g class="fm-edge-labels">')
        for edge in ir["edges"]:
            if edge["kind"] != "flow" or not edge.get("label"):
                continue
            lx, ly = edge["label_point"]
            width = max(28.0, len(edge["label"]) * 5.8) + 12
            parts.append(
                f'    <rect class="fm-edge-label-bg" x="{lx - width / 2:.1f}" '
                f'y="{ly - 7.5:.1f}" width="{width:.1f}" height="15" rx="4" />'
                f'<text class="fm-edge-label" x="{lx}" y="{ly}">'
                f'{html.escape(edge["label"])}</text>'
            )
        parts.append("  </g>")

    # Nodes
    parts.append('  <g class="fm-nodes">')
    for node in ir["nodes"]:
        unconfigured = node["readiness"] == "unconfigured"
        classes = f'fm-node sq-{node["squad"]}'
        if unconfigured:
            classes += " fm-node--unconfigured"
        sub = "NO CREDENTIALS" if unconfigured else node["squad_name"].upper()
        parts.append(
            f'    <g class="{classes}" transform="translate({node["x"]} {node["y"]})">\n'
            f'      <rect class="fm-node-box" width="{node["w"]}" '
            f'height="{node["h"]}" rx="8" />\n'
            f'      <rect class="fm-node-accent" width="3.5" '
            f'height="{node["h"]}" rx="1.75" />\n'
            f'      <text class="fm-node-glyph" x="14" y="24">'
            f'{html.escape(node["glyph"])}</text>\n'
            f'      <text class="fm-node-label" x="34" y="24">'
            f'{html.escape(_truncate(node["label"], 20))}</text>\n'
            f'      <text class="fm-node-sub" x="14" y="42">'
            f'{html.escape(_truncate(sub, 24))}</text>\n'
            f'    </g>'
        )
    parts.append("  </g>")
    parts.append("</svg>")
    return "\n".join(parts)


def render_html(ir: dict[str, Any], profile: profiles.FleetProfile,
                include: tuple[str, ...] = ALL_KINDS) -> str:
    """A self-contained page: identity block, the map, a legend and the roster."""
    counts: dict[str, int] = {}
    for edge in ir["edges"]:
        counts[edge["kind"]] = counts.get(edge["kind"], 0) + 1

    dispatchable = [a for a in registry.AGENTS if a.dispatchable]
    armed = [a for a in dispatchable if not registry.missing_env(a)]

    roster_blocks = []
    for squad in registry.SQUADS:
        members = [a for a in registry.AGENTS if a.squad == squad.id]
        if not members:
            continue
        rows = "\n".join(
            f'      <li><span class="rk-glyph">{html.escape(a.glyph)}</span>'
            f'<span class="rk-name">{html.escape(a.name)}</span>'
            f'<span class="rk-sum">{html.escape(a.summary)}</span></li>'
            for a in members
        )
        roster_blocks.append(
            f'    <section class="rk-squad sq-{squad.id}">\n'
            f'      <h3><span class="rk-swatch"></span>{html.escape(squad.name)}</h3>\n'
            f'      <p class="rk-note">{html.escape(squad.summary)}</p>\n'
            f'      <ul>\n{rows}\n      </ul>\n'
            f'    </section>'
        )

    svg = render_svg(ir, include=include,
                     title=f"{profile.name} architecture",
                     description=(f"Architecture of {profile.name}: "
                                  f"{len(ir['nodes'])} agents in "
                                  f"{len(ir['lanes'])} squads, with work flow, "
                                  f"QA review and external dependencies."))

    lineage = (f" · cloned from {html.escape(profile.derived_from)}"
               if profile.derived_from else "")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(profile.name)} — Fleet Architecture</title>
<style>
:root {{
  --plane: #f9f9f7; --surface: #fcfcfb;
  --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --hairline: #e1e0d9; --rule: #c3c2b7; --accent: #2a78d6;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --plane: #0d0d0d; --surface: #1a1a19;
    --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --hairline: #2c2c2a; --rule: #383835; --accent: #3987e5;
  }}
}}
:root[data-theme="dark"] {{
  --plane: #0d0d0d; --surface: #1a1a19;
  --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --hairline: #2c2c2a; --rule: #383835; --accent: #3987e5;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--plane); color: var(--ink);
  font: 15px/1.6 system-ui, -apple-system, "Segoe UI", sans-serif;
}}
.wrap {{ max-width: 1180px; margin: 0 auto; padding: 40px 24px 72px; }}
.mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
header {{ border-bottom: 1px solid var(--hairline); padding-bottom: 20px; margin-bottom: 28px; }}
.callsign {{
  display: inline-block; padding: 3px 9px; border-radius: 5px;
  background: var(--surface); border: 1px solid var(--rule);
  font-size: 12px; letter-spacing: 0.06em; color: var(--accent);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
h1 {{ font-size: 30px; margin: 12px 0 6px; letter-spacing: -0.015em; text-wrap: balance; }}
.lede {{ margin: 0; color: var(--ink-2); max-width: 62ch; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 26px; margin-top: 20px; }}
.stat b {{ display: block; font-size: 22px; font-variant-numeric: tabular-nums; }}
.stat span {{ font-size: 11px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted); }}
figure {{ margin: 0 0 12px; }}
.mapframe {{
  overflow-x: auto; background: var(--surface);
  border: 1px solid var(--hairline); border-radius: 12px; padding: 8px;
}}
figcaption {{ font-size: 13px; color: var(--ink-2); margin-top: 10px; max-width: 70ch; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 20px; margin: 18px 0 0; padding: 0; list-style: none; font-size: 13px; color: var(--ink-2); }}
.legend li {{ display: flex; align-items: center; gap: 8px; }}
.swatch {{ width: 22px; height: 0; border-top: 2px solid var(--rule); }}
.swatch.review {{ border-top: 2px dashed #ec835a; }}
.swatch.dep {{ border-top: 2px dotted var(--muted); }}
.swatch.dash {{ border: 1px dashed var(--rule); height: 12px; width: 18px; border-radius: 3px; }}
h2 {{ font-size: 13px; letter-spacing: 0.09em; text-transform: uppercase; color: var(--muted); margin: 44px 0 14px; }}
.roster {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 22px; }}
.rk-squad h3 {{ display: flex; align-items: center; gap: 8px; font-size: 14px; margin: 0 0 4px; }}
.rk-swatch {{ width: 10px; height: 10px; border-radius: 3px; background: var(--sq); }}
.rk-note {{ margin: 0 0 10px; font-size: 12.5px; color: var(--muted); }}
.rk-squad ul {{ list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 9px; }}
.rk-squad li {{ display: grid; grid-template-columns: 20px 1fr; gap: 2px 8px; }}
.rk-glyph {{ color: var(--sq); }}
.rk-name {{ font-weight: 600; font-size: 13.5px; }}
.rk-sum {{ grid-column: 2; font-size: 12.5px; color: var(--ink-2); }}
footer {{ margin-top: 52px; padding-top: 18px; border-top: 1px solid var(--hairline);
  font-size: 12.5px; color: var(--muted); }}
{stylesheet()}
</style>
</head>
<body>
<div class="wrap">
<header>
  <span class="callsign">{html.escape(profile.callsign)}</span>
  <h1>{html.escape(profile.name)} — Fleet Architecture</h1>
  <p class="lede">{html.escape(profile.summary)}</p>
  <div class="stats">
    <div class="stat"><b>{len(ir["nodes"])}</b><span>agents</span></div>
    <div class="stat"><b>{len(ir["lanes"])}</b><span>squads</span></div>
    <div class="stat"><b>{counts.get("flow", 0)}</b><span>work paths</span></div>
    <div class="stat"><b>{len(armed)}/{len(dispatchable)}</b><span>credentialled</span></div>
    <div class="stat"><b>{len(profile.backlog)}</b><span>objectives</span></div>
  </div>
</header>

<figure>
  <div class="mapframe">
{svg}
  </div>
  <figcaption>Work enters at Command and moves left to right; the QA agent
  scores every artifact it produces, and the optimizer feeds what it learns
  back into the forge prompts — the loop that makes the fleet self-improving.
  Dashed outlines mark agents whose credentials are not set.</figcaption>
</figure>

<ul class="legend">
  <li><span class="swatch"></span>work</li>
  <li><span class="swatch review"></span>QA review</li>
  <li><span class="swatch dep"></span>external call</li>
  <li><span class="swatch dash"></span>no credentials</li>
</ul>

<h2>Roster</h2>
<div class="roster">
{chr(10).join(roster_blocks)}
</div>

<footer class="mono">
  {html.escape(profile.callsign)} · {len(ir["nodes"])} agents ·
  generated from commander/registry.py · map validated before export
</footer>
</div>
</body>
</html>
"""


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Export the fleet architecture map")
    parser.add_argument("--format", choices=("svg", "html"), default="html")
    parser.add_argument("--out", required=True, help="Path to write")
    parser.add_argument("--fleet", default=profiles.DEFAULT_FLEET)
    parser.add_argument("--include", default="flow,review,dependency",
                        help="Edge classes to draw, comma separated")
    args = parser.parse_args()

    include = tuple(k.strip() for k in args.include.split(",") if k.strip())
    unknown = set(include) - set(ALL_KINDS)
    if unknown:
        print(f"✗ unknown edge class(es): {', '.join(sorted(unknown))}")
        return 2

    profile = profiles.load(args.fleet)
    ir = graph.build()
    report = graph.validate(ir)
    if not report["ok"]:
        for error in report["errors"]:
            print(f"✗ {error}")
        print("refusing to export an unsound map")
        return 1

    if args.format == "svg":
        content = render_svg(ir, include=include, standalone=True,
                             title=f"{profile.name} architecture")
    else:
        content = render_html(ir, profile, include=include)

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"✓ {path} · {len(ir['nodes'])} nodes · "
          f"{ir['width']}×{ir['height']} · {len(content) // 1024}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
