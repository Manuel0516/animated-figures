#!/usr/bin/env python3
"""
List every raw footage clip for a project with its real duration,
resolution, and creation time.

This exists so the agent proposes footage-to-narration matches from actual
ffprobe data instead of guessing from filenames alone -- and so the human
confirmation step (see project.json's `visual.confirmed` field) has real
numbers to confirm or correct.

Usage:
    python scripts/footage_inventory.py --dir output/homelab
    python scripts/footage_inventory.py --dir output/homelab --json
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".mkv", ".avi", ".webm"}


def ffprobe_info(path: Path) -> dict:
    """Duration, resolution and creation time of one clip, via a single ffprobe call."""
    out = subprocess.run(
        ["ffprobe", "-v", "error",
         "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration:format_tags=creation_time",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(out.stdout)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format", {})
    tags = fmt.get("tags", {})
    return {
        "file": path.name,
        "duration": round(float(fmt.get("duration", 0)), 2),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "creation_time": tags.get("creation_time"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="Project folder (must contain footage/raw/).")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a table.")
    args = parser.parse_args()

    if not shutil.which("ffprobe"):
        sys.exit("ffprobe no encontrado. Instala con: brew install ffmpeg")

    raw_dir = Path(args.dir) / "footage" / "raw"
    if not raw_dir.exists():
        sys.exit(f"No existe {raw_dir}. Copia ahí tus clips de metraje real.")

    clips = sorted(p for p in raw_dir.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS)
    if not clips:
        sys.exit(f"No hay clips de vídeo en {raw_dir}.")

    entries = []
    for clip in clips:
        try:
            entries.append(ffprobe_info(clip))
        except subprocess.CalledProcessError as e:
            print(f"  [!] No se pudo leer {clip.name}: {e.stderr.strip()}", file=sys.stderr)

    if not entries:
        sys.exit("Ningún clip se pudo leer con ffprobe.")

    if args.json:
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return

    name_w = max(len(e["file"]) for e in entries)
    print(f"{'archivo':<{name_w}}  {'duración':>9}  {'resolución':>11}  creado")
    for e in entries:
        res = f"{e['width']}x{e['height']}" if e["width"] else "?"
        created = e["creation_time"] or "-"
        print(f"{e['file']:<{name_w}}  {e['duration']:>7.2f}s  {res:>11}  {created}")


if __name__ == "__main__":
    main()
