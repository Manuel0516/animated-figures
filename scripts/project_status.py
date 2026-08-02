#!/usr/bin/env python3
"""
Report what's ready and what's missing for a project before a full render is
attempted: narration audio, and per-scene assets (footage clips confirmed,
diagram clips rendered, still images present, text cards have text).

Exits non-zero when anything is missing, so it can gate a render step in a
longer script or agent workflow.

Usage:
    python scripts/project_status.py --dir output/homelab
"""
import argparse
import json
import sys
from pathlib import Path


def check_scene(scene, video_dir):
    """Return (ready: bool, note: str) for one scene."""
    visual = scene["visual"]
    vtype = visual.get("type")

    if vtype == "footage":
        rel_src = visual.get("src")
        if not rel_src:
            return False, "sin clip asignado"
        src = video_dir / rel_src
        if not src.exists():
            return False, f"clip no encontrado: {rel_src}"
        mark = "" if visual.get("confirmed") else " (sin confirmar, se monta igual)"
        return True, f"metraje{mark}: {rel_src} [{visual.get('in', '?')}s-{visual.get('out', '?')}s]"

    if vtype == "diagram":
        rel_spec = visual.get("spec")
        if not rel_spec or not (video_dir / rel_spec).exists():
            return False, f"spec de diagrama no encontrado: {rel_spec or '?'}"
        clip = video_dir / "diagrams" / f"scene-{scene['index']:03d}.mp4"
        if not clip.exists():
            return False, f"diagrama sin renderizar (spec listo): {rel_spec}"
        return True, f"diagrama renderizado: {clip.relative_to(video_dir)}"

    if vtype == "character":
        rel_spec = visual.get("spec")
        if not rel_spec or not (video_dir / rel_spec).exists():
            return False, f"spec de personaje no encontrado: {rel_spec or '?'}"
        clip = video_dir / "characters" / f"scene-{scene['index']:03d}.mp4"
        if not clip.exists():
            return False, f"personaje sin renderizar (spec listo): {rel_spec}"
        return True, f"personaje renderizado: {clip.relative_to(video_dir)}"

    if vtype == "still":
        rel_src = visual.get("src")
        if not rel_src or not (video_dir / rel_src).exists():
            return False, f"imagen no encontrada: {rel_src or '?'}"
        return True, f"imagen lista: {rel_src}"

    if vtype == "text-card":
        if not visual.get("text"):
            return False, "text-card sin texto"
        return True, "text-card listo (sin assets externos)"

    return False, f"visual.type desconocido: {vtype!r}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="Project folder (contains project.json).")
    args = parser.parse_args()

    video_dir = Path(args.dir)
    project_path = video_dir / "project.json"
    if not project_path.exists():
        sys.exit(f"No existe {project_path}.")
    project = json.loads(project_path.read_text(encoding="utf-8"))

    audio_path = next((video_dir / f"narration{ext}" for ext in (".mp3", ".wav")
                       if (video_dir / f"narration{ext}").exists()), None)
    print(f"{'✓' if audio_path else '✗'} narración: "
          f"{audio_path.name if audio_path else 'narration.mp3/.wav no encontrado'}")

    ready_count = 0
    lines = []
    for scene in project:
        ready, note = check_scene(scene, video_dir)
        ready_count += ready
        mark = "✓" if ready else "✗"
        lines.append(f"{mark} escena {scene['index']:02d} ({scene['visual'].get('type', '?')}): {note}")

    all_ready = audio_path is not None and ready_count == len(project)
    print(f"{'✓' if ready_count == len(project) else '✗'} {ready_count}/{len(project)} escenas listas")
    for line in lines:
        print(f"  {line}")

    if all_ready:
        print(f"\nListo para montar: python scripts/assemble_project.py --dir {video_dir}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
