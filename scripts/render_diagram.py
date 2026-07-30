#!/usr/bin/env python3
"""
Render one diagram spec (nodes/edges/labels/reveal order, see
scripts/render/diagram_scene.py for the shape) into an MP4 clip, via the
generic manim.Scene styled entirely from brand.yaml.

Usage:
    python scripts/render_diagram.py --spec output/homelab/diagrams/scene-003.json \
        --out output/homelab/diagrams/scene-003.mp4
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand import BRAND  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCENE_FILE = ROOT / "scripts" / "render" / "diagram_scene.py"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", required=True, help="Path to the diagram's JSON spec.")
    parser.add_argument("--out", required=True, help="Output MP4 path.")
    args = parser.parse_args()

    if not shutil.which("manim"):
        sys.exit("manim no encontrado. Instala con: pip install manim "
                 "(requiere Cairo/Pango: brew install pango).")

    spec_path = Path(args.spec).resolve()
    if not spec_path.exists():
        sys.exit(f"No existe el spec de diagrama: {spec_path}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    media_dir = out_path.parent / f".manim-media-{spec_path.stem}"
    cmd = [
        "manim",
        "--resolution", f"{BRAND.canvas.width},{BRAND.canvas.height}",
        "--fps", str(BRAND.canvas.fps),
        "--media_dir", str(media_dir),
        "-o", out_path.name,
        "--disable_caching",
        str(SCENE_FILE), "DiagramScene",
    ]

    env = os.environ.copy()
    env["DIAGRAM_SPEC"] = str(spec_path)

    print(f"Renderizando diagrama: {spec_path.name} -> {out_path}")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"manim falló ({result.returncode}):\n{result.stderr[-3000:]}")

    rendered = next(media_dir.rglob(out_path.name), None)
    if rendered is None:
        sys.exit(f"manim terminó pero no encuentro {out_path.name} bajo {media_dir}")
    shutil.move(str(rendered), str(out_path))
    shutil.rmtree(media_dir, ignore_errors=True)

    print(f"OK -> {out_path}")


if __name__ == "__main__":
    main()
