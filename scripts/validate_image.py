#!/usr/bin/env python3
"""
Validate a generated still image and, when needed, build an improved prompt
for regeneration. Used by run_all.py so every still is verified after
generation and ONLY the broken ones are regenerated (with a fix instruction).

Checks:
- file exists and is non-trivial in size (a failed generation often writes
  a tiny or corrupt file)
- decodes as a real image (PIL verify)
- roughly 16:9 aspect (the pipeline requests 16:9)
- not blank: enough colour variance (a solid white/black/one-colour image
  means the model produced an empty frame)

Usage (as a module):
    from validate_image import check_image, improve_prompt
    ok, reason = check_image(Path("04.png"))
    fixed = improve_prompt(original_prompt, reason, attempt=1)

Usage (standalone check of a project folder):
    python scripts/validate_image.py --dir output/<slug>
"""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageStat

MIN_SIZE_BYTES = 8_000
MIN_WIDTH = 480
MIN_HEIGHT = 270
ASPECT_MIN = 1.70          # strict 16:9 (1.777): post-crop keeps 1.70-1.85
ASPECT_MAX = 1.85
MIN_STDDEV = 6.0           # grey-level stddev; blank frames are ~0-3
MAX_MEAN_EDGE = 8.0        # a fully saturated frame (mean 0 or 255) is blank


def check_prompt(prompt: str) -> tuple[bool, str]:
    """Validate that a still/diagram prompt follows the quality rubric:
    at least 80 words (target 100-160) — short one-liners produce bad images.
    """
    if not prompt or not prompt.strip():
        return False, "prompt vacío"
    words = len(prompt.split())
    if words < 80:
        return False, f"prompt demasiado corto ({words} palabras < 80): añade encuadre, máquina, pose del ingeniero, objetos, fondo"
    return True, f"ok ({words} palabras)"


def check_image(path: Path, aspect: str = "16:9") -> tuple[bool, str]:
    """Return (ok, reason). ok=True means the image is usable as a still.
    aspect: "16:9" (landscape) or "9:16" (vertical Shorts)."""
    target = 16 / 9 if aspect == "16:9" else 9 / 16
    tol = 0.09
    if not path.exists():
        return False, "no existe"
    size = path.stat().st_size
    if size < MIN_SIZE_BYTES:
        return False, f"demasiado pequeño ({size} bytes < {MIN_SIZE_BYTES})"
    try:
        with Image.open(path) as img:
            img.verify()
    except Exception as exc:
        return False, f"archivo corrupto o no es imagen: {exc}"

    try:
        with Image.open(path) as img:
            w, h = img.size
            if w < MIN_WIDTH or h < MIN_HEIGHT:
                return False, f"resolución demasiado baja ({w}x{h})"
            aspect_ratio = w / h
            if not (target - tol <= aspect_ratio <= target + tol):
                return False, f"aspecto fuera de rango ({w}x{h} = {aspect_ratio:.2f})"
            # blank check on a small downscaled greyscale version
            small = img.convert("L").resize((64, 36))
    except Exception as exc:
        return False, f"no se pudo analizar: {exc}"

    stat = ImageStat.Stat(small)
    stddev = stat.stddev[0]
    mean = stat.mean[0]
    if stddev < MIN_STDDEV:
        return False, f"imagen en blanco/sólida (stddev={stddev:.1f})"
    if mean < MAX_MEAN_EDGE or mean > 255 - MAX_MEAN_EDGE:
        return False, f"imagen casi saturada (media={mean:.1f})"
    return True, "ok"


def improve_prompt(original: str, reason: str, attempt: int) -> str:
    """Append a targeted fix instruction to the original scene prompt."""
    hint = {
        "blanco": "The image came out blank or nearly solid. Redraw the full scene: "
                  "visible stick figure engineer with yellow hard hat, clear objects, "
                  "white background with flat colored shapes, nothing empty.",
        "saturada": "The image came out almost all black or all white. Redraw with "
                    "normal contrast: dark outlines, white background, flat colours.",
        "resoluci": "The image was too small. Redraw at full 16:9 canvas, filling the "
                    "whole frame with the scene.",
        "aspecto": "The image had the wrong aspect ratio. Redraw strictly 16:9 landscape.",
        "corrupto": "The file was corrupt. Redraw the scene completely from scratch.",
        "pequeño": "The image file was nearly empty. Redraw the complete scene.",
    }
    for key, text in hint.items():
        if key in reason.lower():
            fix = text
            break
    else:
        fix = "Redraw the scene cleanly and completely, fixing whatever was wrong."
    urgency = "Be extra careful with composition and completeness this time." if attempt >= 2 else ""
    return f"{original}\n\nFIX ({attempt+1}): {fix} {urgency}".strip()


def _check_project(video_dir: Path) -> int:
    project_path = video_dir / "project.json"
    if not project_path.exists():
        print(f"No existe {project_path}")
        return 2
    scenes = json.loads(project_path.read_text(encoding="utf-8"))
    bad = 0
    for scene in scenes:
        visual = scene.get("visual", {})
        if visual.get("type") != "still":
            continue
        src = video_dir / visual.get("src", "")
        ok, reason = check_image(src)
        mark = "✓" if ok else "✗"
        print(f"{mark} escena {scene['index']:02d} {src.name}: {reason}")
        if not ok:
            bad += 1
    print(f"\n{len(scenes) - bad}/{len(scenes)} escenas OK, {bad} problemáticas")
    return 0 if bad == 0 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="Project folder (project.json + NN.png files).")
    args = parser.parse_args()
    sys.exit(_check_project(Path(args.dir)))


if __name__ == "__main__":
    main()
