#!/usr/bin/env python3
"""
Loads brand.yaml once and exposes the channel's visual identity as typed
values, so every renderer (captions, diagrams, stills, footage assembly)
reads canvas size / palette / motion timing from the same place instead of
hardcoding its own copy that can drift.

Usage:
    from brand import BRAND
    BRAND.canvas.width, BRAND.canvas.height, BRAND.canvas.fps
    BRAND.palette.accent          # "#FFD24A"
    BRAND.palette.accent_rgb      # (255, 210, 74)
"""
import functools
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BRAND_PATH = ROOT / "brand.yaml"


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


@dataclass(frozen=True)
class Canvas:
    width: int
    height: int
    fps: int


@dataclass(frozen=True)
class Palette:
    background: str
    ink: str
    accent: str
    success: str
    warning: str

    @property
    def background_rgb(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.background)

    @property
    def ink_rgb(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.ink)

    @property
    def accent_rgb(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.accent)

    @property
    def success_rgb(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.success)

    @property
    def warning_rgb(self) -> tuple[int, int, int]:
        return hex_to_rgb(self.warning)


@dataclass(frozen=True)
class Typography:
    family: str
    diagram_family: str
    label_weight: str
    caption_stroke_px: int


@dataclass(frozen=True)
class Line:
    primary_width: int
    secondary_width: int
    node_corner_radius: int
    style: str


@dataclass(frozen=True)
class Motion:
    pop_in_seconds: float
    ease: str


@dataclass(frozen=True)
class Brand:
    name: str
    canvas: Canvas
    palette: Palette
    typography: Typography
    line: Line
    motion: Motion


@functools.lru_cache(maxsize=1)
def load_brand(path: Path = BRAND_PATH) -> Brand:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Brand(
        name=data["name"],
        canvas=Canvas(**data["canvas"]),
        palette=Palette(**data["palette"]),
        typography=Typography(**data["typography"]),
        line=Line(**data["line"]),
        motion=Motion(**data["motion"]),
    )


BRAND = load_brand()
