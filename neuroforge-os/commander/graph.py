#!/usr/bin/env python3
"""
Architecture Graph
==================
Builds a typed intermediate representation of the fleet — nodes, edges, lanes
and fully resolved geometry — and validates it before the browser draws a
single pixel. The renderer stays deliberately dumb: every layout decision
lives here, so the same registry produces the same picture every time and the
map can be diffed, tested and exported like any other artifact.

Validation is atomic. Schema, edge integrity, node overlap, route bounds and
label-to-node clearance must all pass, or the IR is reported broken rather
than rendered wrong.

Three edge classes, each routed differently because they mean different things:

    flow        work moves along it — solid, orthogonal, labelled, always shown
    review      the QA agent scoring an artifact — dimmed curve, toggleable
    dependency  an agent calling an external system — dimmed curve, toggleable

    python -m commander.graph --validate     # exit 1 if the map is unsound
    python -m commander.graph --json         # print the IR
"""

from __future__ import annotations

import json
from typing import Any

from . import registry

IR_VERSION = "neuroforge.fleet/1"

NODE_WIDTH = 176
NODE_HEIGHT = 58
LANE_GAP = 116
ROW_GAP = 34
MARGIN_X = 40
MARGIN_Y = 64
CHANNEL_PITCH = 17      # spacing between parallel routing channels
GUTTER_PITCH = 22       # spacing between same-lane sidestep channels
LABEL_CHAR_WIDTH = 5.8
LABEL_HEIGHT = 15
LABEL_PAD = 6

EDGE_FLOW = "flow"
EDGE_REVIEW = "review"
EDGE_DEPENDENCY = "dependency"

# External systems are inferred from the credentials an agent needs, so the
# registry stays the single source of truth for both dispatch and topology.
ENV_TO_SYSTEM = {
    "ANTHROPIC_API_KEY": "anthropic_api",
    "HEYGEN_API_KEY": "heygen_api",
    "AIRTABLE_API_KEY": "airtable_api",
    "META_ADS_ACCESS_TOKEN": "meta_api",
    "TIKTOK_ADS_ACCESS_TOKEN": "tiktok_api",
}


# ── topology ──────────────────────────────────────────────────────────────

def _lane_members() -> dict[int, list[registry.AgentSpec]]:
    """Group agents into lanes, ordered by squad then registry order."""
    squad_rank = {squad.id: index for index, squad in enumerate(registry.SQUADS)}
    order = {spec.id: index for index, spec in enumerate(registry.AGENTS)}
    lanes: dict[int, list[registry.AgentSpec]] = {}
    for spec in registry.AGENTS:
        lane = registry.SQUADS_BY_ID[spec.squad].lane
        lanes.setdefault(lane, []).append(spec)
    for specs in lanes.values():
        specs.sort(key=lambda s: (squad_rank[s.squad], order[s.id]))
    return lanes


def _classify(source: registry.AgentSpec, target: registry.AgentSpec) -> str:
    """What kind of relationship this edge represents."""
    if target.kind == registry.KIND_EXTERNAL:
        return EDGE_DEPENDENCY
    if target.id == "qa":
        return EDGE_REVIEW
    return EDGE_FLOW


def _collect_edges() -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    edges: list[dict[str, Any]] = []

    for spec in registry.AGENTS:
        for target_id in spec.feeds:
            target = registry.AGENTS_BY_ID.get(target_id)
            if target is None or target_id == spec.id:
                continue
            seen.add((spec.id, target_id))
            kind = _classify(spec, target)
            edges.append({
                "id": f"{spec.id}->{target_id}",
                "from": spec.id,
                "to": target_id,
                "kind": kind,
                # Only flow edges carry labels; the others are deliberately quiet.
                "label": spec.feed_labels.get(target_id, "") if kind == EDGE_FLOW else "",
            })

    for spec in registry.AGENTS:
        if spec.kind == registry.KIND_EXTERNAL:
            continue
        for env_key in spec.requires_env:
            target_id = ENV_TO_SYSTEM.get(env_key)
            if not target_id or target_id == spec.id or (spec.id, target_id) in seen:
                continue
            seen.add((spec.id, target_id))
            edges.append({
                "id": f"{spec.id}~{target_id}",
                "from": spec.id,
                "to": target_id,
                "kind": EDGE_DEPENDENCY,
                "label": "",
            })

    return edges


# ── layout ────────────────────────────────────────────────────────────────

def build(state: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Produce the full IR, optionally stamped with live per-agent state."""
    state = state or {}
    lanes = _lane_members()
    max_rows = max((len(v) for v in lanes.values()), default=1)
    lane_pitch = NODE_WIDTH + LANE_GAP
    row_pitch = NODE_HEIGHT + ROW_GAP

    placement = {
        spec.id: (lane, row)
        for lane, specs in lanes.items()
        for row, spec in enumerate(specs)
    }

    edges = _collect_edges()
    for edge in edges:
        edge["route"] = _route_class(edge, placement)

    # Orthogonal routes need reserved space above and below the node field,
    # so the bands are sized before anything is positioned.
    top_band = sum(1 for e in edges if e["route"] == "overpass") * CHANNEL_PITCH
    bottom_band = sum(1 for e in edges if e["route"] == "feedback") * CHANNEL_PITCH
    top = MARGIN_Y + top_band

    nodes: list[dict[str, Any]] = []
    for lane_index in sorted(lanes):
        specs = lanes[lane_index]
        # Centre each lane vertically so the map reads as a balanced system.
        offset = (max_rows - len(specs)) * row_pitch / 2
        for row, spec in enumerate(specs):
            squad = registry.SQUADS_BY_ID[spec.squad]
            nodes.append({
                "id": spec.id,
                "label": spec.name,
                "kind": spec.kind,
                "squad": spec.squad,
                "squad_name": squad.name,
                "accent": squad.accent,
                "glyph": spec.glyph,
                "summary": spec.summary,
                "lane": lane_index,
                "row": row,
                "x": MARGIN_X + lane_index * lane_pitch,
                "y": top + offset + row * row_pitch,
                "w": NODE_WIDTH,
                "h": NODE_HEIGHT,
                "dispatchable": spec.dispatchable,
                "readiness": registry.readiness(spec),
                "state": state.get(spec.id, {"status": "idle"}),
            })

    by_id = {node["id"]: node for node in nodes}
    node_bottom = top + max_rows * row_pitch - ROW_GAP
    width = MARGIN_X * 2 + (max(lanes) + 1) * lane_pitch - LANE_GAP
    height = node_bottom + MARGIN_Y + bottom_band

    counters: dict[str, int] = {}

    def channel(key: str) -> int:
        index = counters.get(key, 0)
        counters[key] = index + 1
        return index

    for edge in edges:
        source, target = by_id[edge["from"]], by_id[edge["to"]]
        edge["points"], edge["render"] = _route(
            edge, source, target, channel, top, node_bottom)

    _place_labels(edges, nodes)

    return {
        "version": IR_VERSION,
        "width": round(width),
        "height": round(height),
        "lane_label_y": round(top - top_band - 26),
        "lanes": _lane_headers(lanes, lane_pitch, top - top_band - 26),
        "nodes": nodes,
        "edges": edges,
        "mission_chain": list(registry.MISSION_CHAIN),
        "edge_kinds": [EDGE_FLOW, EDGE_REVIEW, EDGE_DEPENDENCY],
    }


def _lane_headers(lanes: dict[int, list[registry.AgentSpec]],
                  lane_pitch: int, label_y: float) -> list[dict[str, Any]]:
    """One header per squad, positioned over its column."""
    headers: list[dict[str, Any]] = []
    used: dict[int, int] = {}
    for squad in registry.SQUADS:
        if squad.lane not in lanes:
            continue
        members = [s for s in lanes[squad.lane] if s.squad == squad.id]
        if not members:
            continue
        # Two squads may share a column; stack their headers so they never
        # print over one another.
        stack = used.get(squad.lane, 0)
        used[squad.lane] = stack + 1
        headers.append({
            "id": squad.id,
            "name": squad.name,
            "lane": squad.lane,
            "accent": squad.accent,
            "summary": squad.summary,
            "count": len(members),
            "x": MARGIN_X + squad.lane * lane_pitch,
            "y": round(label_y + stack * 15),
            "w": NODE_WIDTH,
        })
    return headers


def _route_class(edge: dict[str, Any],
                 placement: dict[str, tuple[int, int]]) -> str:
    """Pick a routing strategy from the lane/row relationship alone."""
    if edge["kind"] != EDGE_FLOW:
        return "curve"

    source_lane, source_row = placement[edge["from"]]
    target_lane, target_row = placement[edge["to"]]

    if target_lane == source_lane:
        if target_row == source_row + 1:
            return "chain"
        if target_row > source_row:
            return "sidestep"
        return "feedback"
    if target_lane < source_lane:
        return "feedback"
    if target_lane - source_lane > 1:
        return "overpass"
    return "step"


def _route(edge: dict[str, Any], source: dict[str, Any], target: dict[str, Any],
           channel, top: float, node_bottom: float) -> tuple[list[list[float]], str]:
    style = edge["route"]

    if style == "curve":
        return _curve(source, target), "curve"

    if style == "chain":
        x = source["x"] + source["w"] / 2
        return ([[x, source["y"] + source["h"]], [x, target["y"]]], "orthogonal")

    if style == "step":
        # Parallel edges crossing the same lane gap get their own vertical channel.
        index = channel(f"gap:{source['lane']}")
        gap_start = source["x"] + source["w"]
        mid = gap_start + LANE_GAP * 0.32 + index * 16
        y1 = source["y"] + source["h"] / 2
        y2 = target["y"] + target["h"] / 2
        if abs(y1 - y2) < 0.5:
            return ([[gap_start, y1], [target["x"], y2]], "orthogonal")
        return ([[gap_start, y1], [mid, y1], [mid, y2], [target["x"], y2]],
                "orthogonal")

    if style == "sidestep":
        # Same column, skipping rows: jog out into the gutter on the left.
        index = channel(f"gutter:{source['lane']}")
        gutter = source["x"] - GUTTER_PITCH * (index + 1)
        y1 = source["y"] + source["h"] / 2
        y2 = target["y"] + target["h"] / 2
        return ([[source["x"], y1], [gutter, y1], [gutter, y2], [target["x"], y2]],
                "orthogonal")

    if style == "overpass":
        # Skipping a whole column: go over the top rather than through it.
        index = channel("overpass")
        lane = top - CHANNEL_PITCH * (index + 1)
        x1 = source["x"] + source["w"] / 2
        x2 = target["x"] + target["w"] / 2
        return ([[x1, source["y"]], [x1, lane], [x2, lane], [x2, target["y"]]],
                "orthogonal")

    # feedback: drop below every node and travel back
    index = channel("feedback")
    lane = node_bottom + CHANNEL_PITCH * (index + 1)
    x1 = source["x"] + source["w"] / 2
    x2 = target["x"] + target["w"] / 2
    return ([[x1, source["y"] + source["h"]], [x1, lane],
             [x2, lane], [x2, target["y"] + target["h"]]], "orthogonal")


def _curve(source: dict[str, Any], target: dict[str, Any]) -> list[list[float]]:
    """Cubic bezier as [start, control1, control2, end]."""
    y1 = source["y"] + source["h"] / 2
    y2 = target["y"] + target["h"] / 2

    if target["lane"] > source["lane"]:
        x1, x2 = source["x"] + source["w"], target["x"]
        bow = max(60.0, (x2 - x1) * 0.45)
        return [[x1, y1], [x1 + bow, y1], [x2 - bow, y2], [x2, y2]]

    if target["lane"] < source["lane"]:
        x1, x2 = source["x"], target["x"] + target["w"]
        bow = max(60.0, (x1 - x2) * 0.45)
        return [[x1, y1], [x1 - bow, y1], [x2 + bow, y2], [x2, y2]]

    # Same column — bow out to the right of the lane.
    x1 = x2 = source["x"] + source["w"]
    bow = 54.0 + abs(source["row"] - target["row"]) * 12
    return [[x1, y1], [x1 + bow, y1], [x2 + bow, y2], [x2, y2]]


# ── labels ────────────────────────────────────────────────────────────────

def _place_labels(edges: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> None:
    """Give every labelled edge a position with clearance, or drop the label.

    Layout resolves collisions here rather than leaving the renderer to draw
    text on top of a box; anything unresolvable is dropped and reported, so a
    validated IR never contains an unreadable label.
    """
    placed: list[dict[str, Any]] = []

    for edge in edges:
        label = edge.get("label")
        if not label:
            edge["label_point"] = None
            continue

        chosen = None
        for candidate in _label_candidates(edge["points"], edge["render"]):
            box = _label_box(candidate, label)
            if any(_overlaps(box, node) for node in nodes):
                continue
            if any(_overlaps(box, other) for other in placed):
                continue
            chosen = candidate
            placed.append(box)
            break

        if chosen is None:
            edge["label"] = ""
            edge["label_point"] = None
            edge["label_dropped"] = True
        else:
            edge["label_point"] = [round(chosen[0], 1), round(chosen[1], 1)]


def _label_candidates(points: list[list[float]], render: str) -> list[list[float]]:
    """Positions to try, best first: the roomiest straight segments."""
    if render == "curve" or len(points) < 2:
        mid = points[len(points) // 2]
        return [[mid[0], mid[1]]]

    segments = []
    for start, end in zip(points, points[1:]):
        length = abs(end[0] - start[0]) + abs(end[1] - start[1])
        horizontal = abs(end[1] - start[1]) < 0.5
        # Horizontal runs read better than vertical ones for text.
        segments.append((length + (40 if horizontal else 0), start, end))
    segments.sort(key=lambda s: s[0], reverse=True)

    # Fractions fan out from the middle so a long vertical run can drop its
    # label into the gap between two rows instead of across one of them.
    candidates: list[list[float]] = []
    for _, start, end in segments:
        for fraction in (0.5, 0.35, 0.65, 0.24, 0.76, 0.18, 0.82):
            candidates.append([
                start[0] + (end[0] - start[0]) * fraction,
                start[1] + (end[1] - start[1]) * fraction,
            ])
    return candidates


def _label_box(point: list[float], label: str) -> dict[str, Any]:
    width = max(28.0, len(label) * LABEL_CHAR_WIDTH) + LABEL_PAD * 2
    return {
        "x": point[0] - width / 2,
        "y": point[1] - LABEL_HEIGHT / 2,
        "w": width,
        "h": LABEL_HEIGHT,
    }


# ── validation ────────────────────────────────────────────────────────────

def validate(ir: dict[str, Any]) -> dict[str, Any]:
    """Atomic pre-render check. Returns {ok, errors, warnings}."""
    errors: list[str] = []
    warnings: list[str] = []

    if ir.get("version") != IR_VERSION:
        errors.append(f"unexpected IR version: {ir.get('version')!r}")

    nodes = ir.get("nodes")
    edges = ir.get("edges")
    if not isinstance(nodes, list) or not nodes:
        errors.append("IR has no nodes")
        return {"ok": False, "errors": errors, "warnings": warnings}
    if not isinstance(edges, list):
        errors.append("IR has no edge list")
        return {"ok": False, "errors": errors, "warnings": warnings}

    required = ("id", "label", "x", "y", "w", "h", "lane", "kind")
    ids: set[str] = set()
    for node in nodes:
        missing = [field for field in required if field not in node]
        if missing:
            errors.append(f"node {node.get('id', '?')} missing {', '.join(missing)}")
            continue
        if node["id"] in ids:
            errors.append(f"duplicate node id: {node['id']}")
        ids.add(node["id"])
        if node["w"] <= 0 or node["h"] <= 0:
            errors.append(f"node {node['id']} has non-positive size")
        if node["x"] < 0 or node["y"] < 0:
            errors.append(f"node {node['id']} sits outside the canvas")
        if node["x"] + node["w"] > ir["width"] or node["y"] + node["h"] > ir["height"]:
            errors.append(f"node {node['id']} overflows the canvas bounds")

    for index, first in enumerate(nodes):
        for second in nodes[index + 1:]:
            if _overlaps(first, second):
                errors.append(f"nodes {first['id']} and {second['id']} overlap")

    label_boxes: list[tuple[str, dict[str, Any]]] = []
    for edge in edges:
        edge_id = edge.get("id", "?")
        for end in ("from", "to"):
            if edge.get(end) not in ids:
                errors.append(f"edge {edge_id} points at unknown node "
                              f"{edge.get(end)!r}")
        if edge.get("from") == edge.get("to"):
            errors.append(f"edge {edge_id} is a self-loop")
        if edge.get("kind") not in (EDGE_FLOW, EDGE_REVIEW, EDGE_DEPENDENCY):
            errors.append(f"edge {edge_id} has unknown kind {edge.get('kind')!r}")

        points = edge.get("points")
        if not isinstance(points, list) or len(points) < 2:
            errors.append(f"edge {edge_id} has no route")
            continue
        if edge.get("render") == "curve" and len(points) != 4:
            errors.append(f"edge {edge_id} is a curve without four control points")
        malformed = False
        for point in points:
            if not (isinstance(point, list) and len(point) == 2):
                errors.append(f"edge {edge_id} has a malformed point")
                malformed = True
                break
        if malformed:
            continue
        for point in points:
            if not (-MARGIN_X <= point[0] <= ir["width"] + MARGIN_X):
                errors.append(f"edge {edge_id} routes off-canvas horizontally")
                break
            if not (0 <= point[1] <= ir["height"]):
                errors.append(f"edge {edge_id} routes off-canvas vertically")
                break

        if edge.get("label"):
            if not edge.get("label_point"):
                errors.append(f"edge {edge_id} has a label with no position")
            else:
                label_boxes.append((edge_id, _label_box(edge["label_point"],
                                                        edge["label"])))
        if edge.get("label_dropped"):
            warnings.append(f"edge {edge_id} label dropped — no clear position")

    # Label clearance: text must not sit on a node or on another label.
    for edge_id, box in label_boxes:
        for node in nodes:
            if _overlaps(box, node):
                errors.append(f"edge {edge_id} label overlaps node {node['id']}")
    for index, (first_id, first) in enumerate(label_boxes):
        for second_id, second in label_boxes[index + 1:]:
            if _overlaps(first, second):
                errors.append(f"labels on {first_id} and {second_id} collide")

    connected = {e.get("from") for e in edges} | {e.get("to") for e in edges}
    for orphan in sorted(ids - connected):
        warnings.append(f"node {orphan} has no connections")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return not (
        a["x"] + a["w"] <= b["x"]
        or b["x"] + b["w"] <= a["x"]
        or a["y"] + a["h"] <= b["y"]
        or b["y"] + b["h"] <= a["y"]
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Fleet architecture graph")
    parser.add_argument("--validate", action="store_true",
                        help="Validate the IR and exit non-zero if it is unsound")
    parser.add_argument("--json", action="store_true", help="Print the IR")
    args = parser.parse_args()

    registry_errors = registry.validate()
    ir = build()
    report = validate(ir)

    if args.json:
        print(json.dumps(ir, indent=2))
        return 0

    for error in registry_errors:
        print(f"✗ registry: {error}")
    for error in report["errors"]:
        print(f"✗ graph: {error}")
    for warning in report["warnings"]:
        print(f"! graph: {warning}")

    kinds: dict[str, int] = {}
    for edge in ir["edges"]:
        kinds[edge["kind"]] = kinds.get(edge["kind"], 0) + 1
    breakdown = ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items()))

    ok = report["ok"] and not registry_errors
    print(f"{'✓' if ok else '✗'} {len(ir['nodes'])} nodes · {breakdown} · "
          f"{ir['width']}×{ir['height']} · {len(report['warnings'])} warning(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
