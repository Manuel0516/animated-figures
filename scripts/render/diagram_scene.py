#!/usr/bin/env python3
"""
One generic manim.Scene that builds an engineering diagram (nodes, edges,
labels, a timed reveal, optional highlights) from a declarative JSON spec --
so the agent authoring a diagram only ever writes the spec, never bespoke
manim code for the common case.

Every visual choice (background, ink/accent colors, line weights, corner
radius, pop-in timing) comes from brand.yaml via scripts/brand.py, not from
constants in this file, so a diagram can't drift from captions/stills.

Not run directly with `manim` on its own -- scripts/render_diagram.py sets
the DIAGRAM_SPEC env var and invokes this via the manim CLI with the correct
--resolution/--fps for the brand canvas.

Spec shape (see schemas/diagram.schema.json):
    {
      "duration": 6.0,
      "nodes": [{"id": "...", "label": "...", "position": [x, y], "icon": ""}, ...],
      "edges": [{"from": "...", "to": "...", "label": "...", "style": "solid|dashed",
                 "direction": "forward|backward|both|none"}, ...],
      "reveal": [{"at": 0.0, "show": ["node-or-edge-id", ...]}, ...],
      "highlight": [{"at": 3.0, "id": "node-or-edge-id"}, ...]
    }

Node/edge positions and sizes are in manim's own coordinate space (~14.2
units wide for a 16:9 frame at default zoom), not pixels -- only stroke
widths and corner radius are converted from the brand's pixel-based values.

Edges anchor at the center of the top/bottom (horizontal) side of each
node -- left/right only as a fallback when both nodes sit at the same
height, where top/bottom would be degenerate -- not wherever a straight
line between box centers happens to cross the boundary, which for boxes
offset in both x and y usually lands near a corner instead of the middle
of a side. They default to a single arrowhead
("forward"); "both" draws arrowheads on both ends for bidirectional links,
"none" draws a plain line for a passive physical connection. An edge label
sits directly on the line, and the line itself is split into two segments
around the label's backdrop -- the gap is the exact geometric intersection
of the line with the backdrop rectangle (via get_boundary_point), so the
line can never touch the label regardless of the edge's angle. Node boxes
are sized from their own label (generous fixed padding), not a fixed box
size, so a short label ("VPS") and a long one ("Old Laptop")
both get correct, even padding instead of one looking cramped.

The diagram font is a Nerd Font (brand.yaml's typography.diagram_family), so
a node's optional "icon" field can use one of its glyphs as a simple
thin-line pictogram (laptop, server, router, lock, ...) instead of needing a
separate SVG icon asset.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
from manim import (
    BOLD,
    NORMAL,
    DashedLine,
    FadeIn,
    Indicate,
    Line,
    Rectangle,
    RoundedRectangle,
    Scene,
    Text,
    VGroup,
    config,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from brand import BRAND  # noqa: E402

NODE_PAD_X = 0.55
NODE_PAD_Y = 0.4
NODE_MIN_WIDTH = 2.6
NODE_MIN_HEIGHT = 1.1
LABEL_FONT_SIZE = 28
EDGE_LABEL_FONT_SIZE = 20
EDGE_LABEL_PAD_X = 0.3
EDGE_LABEL_PAD_Y = 0.22
LABEL_WEIGHT = BOLD if BRAND.typography.label_weight == "bold" else NORMAL


def load_spec() -> dict:
    spec_path = os.environ.get("DIAGRAM_SPEC")
    if not spec_path:
        raise RuntimeError(
            "DIAGRAM_SPEC is not set -- render diagrams via "
            "scripts/render_diagram.py, not by invoking manim on this file directly."
        )
    return json.loads(Path(spec_path).read_text(encoding="utf-8"))


def edge_id(edge: dict) -> str:
    return f"{edge['from']}->{edge['to']}"


def side_anchor(box, dx: float, dy: float):
    """Center of the box's top/bottom side facing (dx, dy) -- the horizontal
    edge -- or its left/right side only when the other node sits at (near
    enough) the same height, where top/bottom would be degenerate.

    A ray from box-center to the *other* box's center lands wherever it
    happens to cross the boundary -- for two boxes offset in both x and y,
    that's usually near a corner, not the middle of a side. Anchoring at a
    side's center instead is how architecture diagrams actually connect
    boxes; this house style prefers the horizontal (top/bottom) edge.
    """
    half_w, half_h = box.width / 2, box.height / 2
    if abs(dy) > 1e-6:
        return box.get_center() + np.array([0, half_h if dy > 0 else -half_h, 0])
    return box.get_center() + np.array([half_w if dx > 0 else -half_w, 0, 0])


class DiagramScene(Scene):
    def construct(self):
        self.camera.background_color = BRAND.palette.background
        spec = load_spec()

        # brand.yaml's line/corner values are pixel-based; manim geometry is
        # in its own coordinate space, so convert once using the canvas the
        # CLI was actually invoked with.
        px_to_units = config.frame_width / config.pixel_width
        corner_radius = BRAND.line.node_corner_radius * px_to_units

        node_groups: dict[str, VGroup] = {}
        node_boxes: dict[str, RoundedRectangle] = {}
        for node in spec["nodes"]:
            label_text = f"{node['icon']}  {node['label']}" if node.get("icon") else node["label"]
            label = Text(
                label_text,
                color=BRAND.palette.ink,
                font=BRAND.typography.diagram_family,
                weight=LABEL_WEIGHT,
                font_size=LABEL_FONT_SIZE,
            )
            # Size the box from its own label instead of a fixed constant, so
            # a short label ("VPS") and a long one ("Old Laptop") both get
            # the same even padding instead of one looking cramped and the
            # other looking mostly empty.
            box = RoundedRectangle(
                corner_radius=corner_radius,
                width=max(label.width + NODE_PAD_X * 2, NODE_MIN_WIDTH),
                height=max(label.height + NODE_PAD_Y * 2, NODE_MIN_HEIGHT),
                color=BRAND.palette.ink,
                stroke_width=BRAND.line.primary_width,
                fill_opacity=0,
            ).move_to(node["position"])
            label.move_to(box.get_center())
            node_groups[node["id"]] = VGroup(box, label)
            node_boxes[node["id"]] = box

        edge_groups: dict[str, VGroup] = {}
        for edge in spec.get("edges", []):
            from_box = node_boxes[edge["from"]]
            to_box = node_boxes[edge["to"]]
            delta = to_box.get_center() - from_box.get_center()
            # Anchor each end at the center of the facing side (not wherever
            # a diagonal ray happens to cross the boundary -- see side_anchor).
            start = side_anchor(from_box, delta[0], delta[1])
            end = side_anchor(to_box, -delta[0], -delta[1])
            direction = end - start
            direction = direction / np.linalg.norm(direction)
            line_cls = DashedLine if edge.get("style") == "dashed" else Line

            # Always show a direction; "none" is an explicit opt-out for a
            # passive physical link, not the default.
            arrow_mode = edge.get("direction", "forward")

            if edge.get("label"):
                label = Text(edge["label"], color=BRAND.palette.ink, font=BRAND.typography.diagram_family,
                            weight=LABEL_WEIGHT, font_size=EDGE_LABEL_FONT_SIZE)
                label.move_to((start + end) / 2)
                backdrop = Rectangle(
                    width=label.width + EDGE_LABEL_PAD_X * 2,
                    height=label.height + EDGE_LABEL_PAD_Y * 2,
                    fill_color=BRAND.palette.background,
                    fill_opacity=1,
                    stroke_width=0,
                ).move_to(label.get_center())
                # Split the line at the exact points it crosses the backdrop,
                # so it can never touch the label -- not an offset guess,
                # the real geometric intersection, same technique as the
                # node-boundary stop above.
                gap_start = backdrop.get_boundary_point(-direction)
                gap_end = backdrop.get_boundary_point(direction)
                seg_a = line_cls(start, gap_start, color=BRAND.palette.ink, stroke_width=BRAND.line.secondary_width)
                seg_b = line_cls(gap_end, end, color=BRAND.palette.ink, stroke_width=BRAND.line.secondary_width)
                if arrow_mode in ("backward", "both"):
                    seg_a.add_tip(at_start=True)
                if arrow_mode in ("forward", "both"):
                    seg_b.add_tip(at_start=False)
                parts = [seg_a, seg_b, backdrop, label]
            else:
                line = line_cls(start, end, color=BRAND.palette.ink, stroke_width=BRAND.line.secondary_width)
                if arrow_mode in ("forward", "both"):
                    line.add_tip(at_start=False)
                if arrow_mode in ("backward", "both"):
                    line.add_tip(at_start=True)
                parts = [line]

            edge_groups[edge_id(edge)] = VGroup(*parts)

        elements: dict[str, VGroup] = {**node_groups, **edge_groups}

        t = 0.0
        for step in sorted(spec.get("reveal", []), key=lambda r: r["at"]):
            gap = step["at"] - t
            if gap > 0:
                self.wait(gap)
            anims = [FadeIn(elements[key], scale=0.72, run_time=BRAND.motion.pop_in_seconds)
                     for key in step["show"] if key in elements]
            if anims:
                self.play(*anims)
            t = step["at"]

        for hl in sorted(spec.get("highlight", []), key=lambda h: h["at"]):
            gap = hl["at"] - t
            if gap > 0:
                self.wait(gap)
            mobj = elements.get(hl.get("id"))
            if mobj is not None:
                self.play(Indicate(mobj, color=BRAND.palette.accent, scale_factor=1.05,
                                   run_time=min(BRAND.motion.pop_in_seconds * 2, 0.5)))
            t = hl["at"]

        duration = spec.get("duration")
        if duration and duration > t:
            self.wait(duration - t)
