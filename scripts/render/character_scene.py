#!/usr/bin/env python3
"""
One generic manim.Scene that draws a simple stick figure in a fixed named
pose, for the "general overview, then zoom into detail" narrative beat --
a brief on-brand transition shot before cutting into a diagram, not a
performing/gesturing character. No rig, no joints: each pose is a fixed set
of line segments, matching the "cheap static device" scope (see Ardens'
channel, which uses its character the same way).

Every visual choice (background, ink color, line weight, pop-in timing)
comes from brand.yaml, same as diagram_scene.py.

Not run directly with `manim` on its own -- scripts/render_character.py
sets the CHARACTER_SPEC env var and invokes this via the manim CLI with the
correct --resolution/--fps for the brand canvas.

Spec shape (see schemas/character.schema.json):
    {"pose": "overview" | "point-right", "duration": 3.0}
"""
import json
import os
import sys
from pathlib import Path

from manim import DOWN, LEFT, ORIGIN, RIGHT, UP, Circle, Dot, FadeIn, Line, Scene, VGroup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from brand import BRAND  # noqa: E402

HEAD_RADIUS = 0.32
TORSO_LEN = 0.9
LEG_LEN = 0.9
LEG_SPREAD = 0.35
ARM_LEN = 0.75
EYE_RADIUS = 0.035
EYE_OFFSET_X = 0.12
EYE_OFFSET_Y = 0.05


def load_spec() -> dict:
    spec_path = os.environ.get("CHARACTER_SPEC")
    if not spec_path:
        raise RuntimeError(
            "CHARACTER_SPEC is not set -- render a character via "
            "scripts/render_character.py, not by invoking manim on this file directly."
        )
    return json.loads(Path(spec_path).read_text(encoding="utf-8"))


def build_figure(pose: str) -> VGroup:
    """A stick figure, feet at the origin, built from brand-styled line
    segments. `pose` picks a fixed arm arrangement -- there is no joint
    rig, just a couple of named, hand-tuned poses.
    """
    ink = BRAND.palette.ink
    width = BRAND.line.primary_width

    hip = ORIGIN + UP * LEG_LEN
    shoulder = hip + UP * TORSO_LEN
    head_center = shoulder + UP * HEAD_RADIUS

    parts = [
        Line(hip, hip + DOWN * LEG_LEN + LEFT * LEG_SPREAD, color=ink, stroke_width=width),
        Line(hip, hip + DOWN * LEG_LEN + RIGHT * LEG_SPREAD, color=ink, stroke_width=width),
        Line(hip, shoulder, color=ink, stroke_width=width),
        Circle(radius=HEAD_RADIUS, color=ink, stroke_width=width, fill_opacity=0).move_to(head_center),
        Dot(head_center + LEFT * EYE_OFFSET_X + UP * EYE_OFFSET_Y, radius=EYE_RADIUS, color=ink),
        Dot(head_center + RIGHT * EYE_OFFSET_X + UP * EYE_OFFSET_Y, radius=EYE_RADIUS, color=ink),
    ]

    if pose == "point-right":
        # One arm extended to point toward where a diagram will appear
        # next; the other hangs relaxed -- the "now let's zoom in" beat.
        parts.append(Line(shoulder, shoulder + LEFT * 0.15 + DOWN * ARM_LEN * 0.9, color=ink, stroke_width=width))
        parts.append(Line(shoulder, shoulder + RIGHT * ARM_LEN * 1.15 + UP * 0.05, color=ink, stroke_width=width))
    else:
        # "overview": both arms open and slightly down -- a presenting,
        # here's-the-whole-system stance.
        parts.append(Line(shoulder, shoulder + LEFT * ARM_LEN * 0.8 + DOWN * ARM_LEN * 0.35,
                          color=ink, stroke_width=width))
        parts.append(Line(shoulder, shoulder + RIGHT * ARM_LEN * 0.8 + DOWN * ARM_LEN * 0.35,
                          color=ink, stroke_width=width))

    return VGroup(*parts)


class CharacterScene(Scene):
    def construct(self):
        self.camera.background_color = BRAND.palette.background
        spec = load_spec()

        figure = build_figure(spec.get("pose", "overview"))
        self.play(FadeIn(figure, scale=0.72, run_time=BRAND.motion.pop_in_seconds))

        duration = spec.get("duration", 3.0)
        remaining = duration - BRAND.motion.pop_in_seconds
        if remaining > 0:
            self.wait(remaining)
