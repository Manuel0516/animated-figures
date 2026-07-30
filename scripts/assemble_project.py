#!/usr/bin/env python3
"""
Scene-type-aware assembler: composites real footage clips and still images
(Ken Burns zoom) into a single 1080p MP4, driven by project.json instead of
the legacy segments.json + NN.png convention.

Phase 1 supports `visual.type` "still" (same Ken Burns path as
assemble_video.py, reused as-is) and "footage" (real clips, trimmed and
cropped to cover, then padded or truncated to the scene's narration-driven
on-screen duration). "diagram" and "text-card" land in later phases --
assemble_project.py refuses to run on a project.json that references them so
a partially-supported render never ships silently wrong.

Footage matching is human-confirmed, not automatic: a footage scene with
`visual.confirmed` not set to true is refused, since the agent proposes a
clip/timestamp but cannot actually verify it matches the narration -- a
silent wrong guess would ship a broken video.

Usage:
    python scripts/assemble_project.py --dir output/homelab
"""
import argparse
import json
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble_video import render_frame  # noqa: E402 -- reuse the Ken Burns still renderer
from brand import BRAND  # noqa: E402
from ffmpeg_pipe import QUIET_ARGS, FfmpegSink, FfmpegSource  # noqa: E402
from timing import (  # noqa: E402
    compute_timeline,
    compute_timeline_from_words,
    ffprobe_duration,
    frame_spans,
    load_word_timings,
)

WIDTH, HEIGHT, FPS = BRAND.canvas.width, BRAND.canvas.height, BRAND.canvas.fps
FRAME_SIZE = WIDTH * HEIGHT * 3  # rgb24
SUPPORTED_VISUAL_TYPES = {"still", "footage", "diagram", "character"}


def clip_source_cmd(src: Path, in_s: float, out_s: float, assigned_duration: float):
    """ffmpeg command that decodes [in_s, out_s) from src, cover-crops it to
    the brand canvas, and pads or truncates it to exactly assigned_duration
    seconds of raw rgb24 frames -- so a scene's frame count always matches
    what frame_spans() assigned it, the same invariant still scenes already
    guarantee. Used for both real footage (a sub-range of a raw clip) and
    rendered diagram clips (the whole clip, already at canvas size -- the
    cover-crop is then a no-op, cheap to keep for one code path).
    """
    trim_duration = out_s - in_s
    # tpad extends by freezing the last decoded frame; the trailing -t clamps
    # any overshoot from this margin (or from a trim longer than assigned).
    pad = max(0.0, assigned_duration - trim_duration) + 0.5
    vf = (
        f"fps={FPS},"
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        f"setsar=1,"
        f"tpad=stop_mode=clone:stop_duration={pad:.3f}"
    )
    return ["ffmpeg", "-y", *QUIET_ARGS,
            "-ss", f"{in_s:.3f}", "-i", str(src), "-t", f"{trim_duration:.3f}",
            "-vf", vf,
            "-t", f"{assigned_duration:.3f}",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}", "-"]


def stream_clip(scene, n_frames, sink, src: Path, in_s: float, out_s: float, kind: str):
    """Decode [in_s, out_s) from src through the sink, exactly n_frames."""
    assigned_duration = n_frames / FPS
    cmd = clip_source_cmd(src, in_s, out_s, assigned_duration)
    source = FfmpegSource(cmd)
    written = 0
    try:
        for _ in range(n_frames):
            frame = source.read_frame(FRAME_SIZE)
            if frame is None:
                break
            sink.write(frame)
            written += 1
    finally:
        ret = source.close()
    if ret != 0:
        sys.exit(f"ffmpeg (lectura de {kind}) falló en escena {scene['index']:02d} ({ret}):\n"
                  f"{source.errors}")
    if written < n_frames:
        sys.exit(f"Escena {scene['index']:02d}: solo se leyeron {written}/{n_frames} frames "
                  f"de {src.name} -- el vídeo quedaría desincronizado del audio.")


def stream_footage_scene(scene, n_frames, sink, video_dir):
    visual = scene["visual"]
    if not visual.get("confirmed"):
        sys.exit(
            f"Escena {scene['index']:02d}: el clip de metraje real no está confirmado "
            f"(visual.confirmed no es true en project.json). Confirma el clip y los "
            f"timestamps antes de montar -- el matching de metraje no es automático."
        )
    src = video_dir / visual["src"]
    if not src.exists():
        sys.exit(f"Escena {scene['index']:02d}: no existe el clip {src}")
    stream_clip(scene, n_frames, sink, src, visual["in"], visual["out"], kind="metraje")


def diagram_clip_path(scene, video_dir) -> Path:
    """Where render_diagram.py writes a diagram scene's rendered clip -- same
    convention project_status.py checks for.
    """
    return video_dir / "diagrams" / f"scene-{scene['index']:03d}.mp4"


def stream_diagram_scene(scene, n_frames, sink, video_dir):
    clip = diagram_clip_path(scene, video_dir)
    if not clip.exists():
        spec = video_dir / scene["visual"].get("spec", "?")
        sys.exit(f"Escena {scene['index']:02d}: diagrama sin renderizar (falta {clip}).\n"
                 f"Renderízalo con: python scripts/render_diagram.py --spec {spec} --out {clip}")
    clip_duration = ffprobe_duration(clip)
    stream_clip(scene, n_frames, sink, clip, 0.0, clip_duration, kind="diagrama")


def character_clip_path(scene, video_dir) -> Path:
    """Where render_character.py writes a character scene's rendered clip --
    same convention project_status.py checks for.
    """
    return video_dir / "characters" / f"scene-{scene['index']:03d}.mp4"


def stream_character_scene(scene, n_frames, sink, video_dir):
    clip = character_clip_path(scene, video_dir)
    if not clip.exists():
        spec = video_dir / scene["visual"].get("spec", "?")
        sys.exit(f"Escena {scene['index']:02d}: personaje sin renderizar (falta {clip}).\n"
                 f"Renderízalo con: python scripts/render_character.py --spec {spec} --out {clip}")
    clip_duration = ffprobe_duration(clip)
    stream_clip(scene, n_frames, sink, clip, 0.0, clip_duration, kind="personaje")


def stream_still_scene(scene, n_frames, zoom, zoom_in, sink, video_dir, pool):
    img = video_dir / scene["visual"]["src"]
    if not img.exists():
        sys.exit(f"Escena {scene['index']:02d}: falta la imagen {img}")
    jobs = [(str(img), f, n_frames, zoom, zoom_in) for f in range(n_frames)]
    for raw in pool.map(render_frame, jobs, chunksize=8):
        sink.write(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="Project folder (project.json, narration.*, footage/, etc.).")
    parser.add_argument("--audio", help="Narration audio path (default: narration.mp3/.wav inside --dir).")
    parser.add_argument("--out", help="Output MP4 path (default: <dir>/final_clean.mp4).")
    parser.add_argument("--zoom", type=float, default=1.10, help="Max zoom factor for still scenes (default: 1.10).")
    parser.add_argument("--no-zoom", action="store_true", help="Disable the Ken Burns zoom on still scenes.")
    parser.add_argument("--min-duration", type=float, default=1.2, help="Minimum seconds per scene.")
    parser.add_argument("--crf", type=int, default=20, help="x264 quality, lower is better (default: 20).")
    parser.add_argument("--preset", default="veryfast", help="x264 preset (default: veryfast).")
    parser.add_argument("--encoder", choices=("libx264", "h264_videotoolbox"), default="libx264")
    parser.add_argument("--jobs", type=int, default=0, help="Parallel frame workers for still scenes (default: CPU count).")
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("ffmpeg/ffprobe no encontrados. Instala con: brew install ffmpeg")

    video_dir = Path(args.dir)
    project_path = video_dir / "project.json"
    if not project_path.exists():
        sys.exit(f"No existe {project_path}. assemble_project.py necesita project.json "
                 f"(para proyectos solo-stills, usa assemble_video.py con segments.json).")
    project = json.loads(project_path.read_text(encoding="utf-8"))

    unsupported = sorted({s["visual"]["type"] for s in project} - SUPPORTED_VISUAL_TYPES)
    if unsupported:
        sys.exit(f"assemble_project.py todavía no soporta estos visual.type: {', '.join(unsupported)} "
                 f"(fase 1 solo implementa 'still' y 'footage').")

    if args.audio:
        audio_path = Path(args.audio)
    else:
        audio_path = next((video_dir / f"narration{ext}" for ext in (".mp3", ".wav")
                           if (video_dir / f"narration{ext}").exists()), None)
        if audio_path is None:
            sys.exit(f"No encuentro narration.mp3 ni narration.wav en {video_dir}. Pasa --audio.")
    if not audio_path.exists():
        sys.exit(f"No existe el audio: {audio_path}")

    out_path = Path(args.out) if args.out else video_dir / "final_clean.mp4"

    audio_duration = ffprobe_duration(audio_path)
    word_timings = load_word_timings(video_dir)
    if word_timings:
        timeline = compute_timeline_from_words(project, word_timings, args.min_duration, audio_duration)
    else:
        timeline = compute_timeline(project, audio_duration, args.min_duration)
    spans = frame_spans(timeline, FPS)
    zoom = 1.0 if args.no_zoom else args.zoom
    total = sum(n for _, n in spans)

    cmd = ["ffmpeg", "-y", *QUIET_ARGS,
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "-",
           "-i", str(audio_path),
           "-vf", "format=yuv420p", "-map", "0:v", "-map", "1:a",
           "-c:v", args.encoder]
    if args.encoder == "libx264":
        cmd += ["-preset", args.preset, "-crf", str(args.crf)]
    else:
        cmd += ["-q:v", "60"]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out_path)]

    print(f"Renderizando {total} frames ({len(project)} escenas)...")

    sink = FfmpegSink(cmd)
    written_total = 0
    try:
        with ProcessPoolExecutor(max_workers=(args.jobs or None)) as pool:
            for i, (scene, (_, n_frames)) in enumerate(zip(project, spans)):
                vtype = scene["visual"]["type"]
                if vtype == "still":
                    stream_still_scene(scene, n_frames, zoom, i % 2 == 0, sink, video_dir, pool)
                elif vtype == "footage":
                    stream_footage_scene(scene, n_frames, sink, video_dir)
                elif vtype == "diagram":
                    stream_diagram_scene(scene, n_frames, sink, video_dir)
                elif vtype == "character":
                    stream_character_scene(scene, n_frames, sink, video_dir)
                written_total += n_frames
                print(f"  escena {scene['index']:02d} ({vtype}): {n_frames} frames "
                      f"({written_total}/{total})", flush=True)
    except BrokenPipeError:
        pass
    ret = sink.close()
    if ret != 0:
        sys.exit(f"ffmpeg falló ({ret}):\n{sink.errors}")

    print(f"OK -> {out_path} ({audio_duration:.1f}s)")


if __name__ == "__main__":
    main()
