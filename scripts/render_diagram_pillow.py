#!/usr/bin/env python3
"""
Render a DIAGRAM from a declarative JSON spec into a crisp vector-style PNG
using pure Pillow — no manim, no Graphviz, no API, no sudo. This is the
"code-generated diagram" path for technical shots: the text is rendered by
Pillow so it is ALWAYS crisp and correct (never garbled like AI image text).

Spec shape (see schemas/diagram.schema.json for the canonical schema):

    {
      "title": "Jet engine airflow",          # optional, shown at top
      "nodes": [
        {"id": "fan",    "label": "Fan"},
        {"id": "core",   "label": "Core"},
        {"id": "nozzle", "label": "Nozzle"}
      ],
      "edges": [
        {"from": "fan", "to": "core", "label": "air"},
        {"from": "core", "to": "nozzle", "label": "thrust"}
      ]
    }

Layout: nodes are auto-arranged (left-to-right following edge order, or a
simple grid when the graph has branches). Optional per-node "position":
[column, row] (0-based) overrides auto-layout.

Style comes from brand.yaml (BRAND_FILE env override for Shorts).

Usage:
    python scripts/render_diagram_pillow.py --spec output/x/diagrams/scene-003.json \
        --out output/x/diagrams/scene-003.png
"""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand import BRAND  # noqa: E402

W, H = BRAND.canvas.width, BRAND.canvas.height
BG = BRAND.palette.background_rgb
INK = BRAND.palette.ink_rgb
ACCENT = BRAND.palette.accent_rgb
FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _font(size: int, bold: bool = True):
    for cand in FONT_DIRS:
        if Path(cand).exists():
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _font_size(font) -> int:
    """Font pixel size: FreeTypeFont has .size; default font reports via metrics."""
    size = getattr(font, "size", None)
    if isinstance(size, int):
        return size
    ascent, descent = font.getmetrics()
    return ascent + descent


def _auto_layout(spec: dict, vertical: bool) -> dict:
    """Assign (col, row) to each node. Horizontal brand: left-to-right flow;
    vertical (Shorts) brand: top-to-bottom flow. Branching nodes get new
    rows/cols (simple layered layout)."""
    nodes = spec.get("nodes", [])
    edges = spec.get("edges", [])
    ids = [n["id"] for n in nodes]
    pos: dict[str, list[int]] = {}
    # explicit positions win
    for n in nodes:
        if "position" in n:
            pos[n["id"]] = list(n["position"])

    incoming = {i: [] for i in ids}
    for e in edges:
        if e["from"] in incoming and e["to"] in incoming:
            incoming[e["to"]].append(e["from"])
    depth: dict[str, int] = {}
    for i in ids:
        if i not in depth:
            depth[i] = 0 if not incoming[i] else max(depth.get(p, 0) + 1 for p in incoming[i])
    # group by depth, spread across the other axis
    by_depth: dict[int, list[str]] = {}
    for i in ids:
        by_depth.setdefault(depth.get(i, 0), []).append(i)
    for d, members in by_depth.items():
        for k, i in enumerate(members):
            if i not in pos:
                # horizontal canvas: depth -> column, member -> row
                # vertical canvas: depth -> row, member -> column
                pos[i] = [k, d] if vertical else [d, k]
    return pos


def render(spec: dict, out_path: Path) -> None:
    title = spec.get("title", "")
    nodes = spec.get("nodes", [])
    edges = spec.get("edges", [])
    pos = _auto_layout(spec, vertical=(H > W))

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # margins for title
    top_margin = int(H * 0.14) if title else int(H * 0.08)
    draw_area_h = H - top_margin - int(H * 0.06)

    if title:
        tf = _font(int(H * 0.045))
        tw = draw.textlength(title, font=tf)
        draw.text(((W - tw) / 2, int(H * 0.045)), title, font=tf, fill=INK)

    # bounding box of used columns/rows
    cols = max((p[0] for p in pos.values()), default=0) + 1
    rows = max((p[1] for p in pos.values()), default=0) + 1
    pad_x = int(W * 0.08)
    pad_y = int(H * 0.05)
    cell_w = (W - 2 * pad_x) / cols
    cell_h = (draw_area_h - 2 * pad_y) / rows

    node_box_w = int(cell_w * 0.62)
    node_box_h = int(min(cell_h * 0.5, H * 0.09))  # cap height so rows stay compact

    centers: dict[str, tuple[int, int]] = {}
    # font sized to fit the LONGEST label in its box: width-bounded.
    def _label_font(label: str, max_w: int, max_h: int):
        size = max(int(max_h * 0.34), 14)
        while size > 12:
            f = _font(size)
            if draw.textlength(label, font=f) <= max_w * 0.92:
                return f
            size -= 2
        return _font(12)

    for n in nodes:
        c, r = pos[n["id"]]
        cx = int(pad_x + cell_w * (c + 0.5))
        cy = int(top_margin + pad_y + cell_h * (r + 0.5))
        centers[n["id"]] = (cx, cy)
        x0, y0 = cx - node_box_w // 2, cy - node_box_h // 2
        draw.rounded_rectangle([x0, y0, x0 + node_box_w, y0 + node_box_h],
                               radius=node_box_h // 4, outline=ACCENT, width=3)
        label = n.get("label", n["id"])
        label_font = _label_font(label, node_box_w, node_box_h)
        lw = draw.textlength(label, font=label_font)
        draw.text((cx - lw / 2, cy - _font_size(label_font) / 2), label, font=label_font, fill=INK)

    # edges after nodes so arrows sit on top of boxes' borders is fine; draw
    # from box edge to box edge
    edge_font = _font(max(int(node_box_h * 0.28), 14))
    for e in edges:
        a, b = centers.get(e["from"]), centers.get(e["to"])
        if not a or not b:
            continue
        # shorten so the line starts/ends at the box border
        dx, dy = b[0] - a[0], b[1] - a[1]
        dist = max((dx ** 2 + dy ** 2) ** 0.5, 1)
        ux, uy = dx / dist, dy / dist
        s = (a[0] + ux * node_box_w // 2, a[1] + uy * node_box_h // 2)
        t = (b[0] - ux * node_box_w // 2, b[1] - uy * node_box_h // 2)
        draw.line([s, t], fill=INK, width=4)
        # arrowhead at t
        ah = 16
        ang = 0.55
        ax1 = (t[0] - ah * (ux * math_cos(ang) - uy * math_sin(ang)),
               t[1] - ah * (ux * math_sin(ang) + uy * math_cos(ang)))
        ax2 = (t[0] - ah * (ux * math_cos(-ang) - uy * math_sin(-ang)),
               t[1] - ah * (ux * math_sin(-ang) + uy * math_cos(-ang)))
        draw.polygon([t, ax1, ax2], fill=INK)
        if e.get("label"):
            mx, my = (s[0] + t[0]) / 2, (s[1] + t[1]) / 2 - _font_size(edge_font)
            lw = draw.textlength(e["label"], font=edge_font)
            # keep the label from colliding with either box: push it toward
            # the midpoint offset perpendicular to the line
            px, py = -uy, ux  # perpendicular
            mx += px * node_box_h * 0.55
            my += py * node_box_h * 0.55
            my -= _font_size(edge_font) * 0.4
            draw.rectangle([mx - lw / 2 - 6, my - 4, mx + lw / 2 + 6, my + _font_size(edge_font) + 4],
                           fill=BG)
            draw.text((mx - lw / 2, my), e["label"], font=edge_font, fill=ACCENT)

    img.save(out_path, "PNG")
    print(f"OK -> {out_path} ({W}x{H})")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", required=True, help="Diagram spec JSON path.")
    parser.add_argument("--out", required=True, help="Output PNG path.")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.exists():
        sys.exit(f"No existe el spec: {spec_path}")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    render(spec, out)


# tiny math helpers to avoid importing math at module load
import math as _m
math_cos = _m.cos
math_sin = _m.sin

if __name__ == "__main__":
    main()
