#!/usr/bin/env python3
"""
Combine numbered images + narration audio into a single 1080p MP4, with a
smooth Ken Burns zoom on each image and an optional animated subtitle overlay.

Each image is on screen for a slice of the narration proportional to its
segment's word count (see timing.py).

The zoom is rendered in Pillow rather than with ffmpeg's `zoompan` filter.
zoompan rounds its crop window to whole source pixels, and at the slow rates
this style needs (~0.25 px of drift per frame) that quantization shows up as a
visible shake -- the motion advances 0 px, 0 px, 1 px, 0 px... Measured on a
real frame, zoompan gave 8 direction reversals and 1.64 px peak jerk over 60
frames against a measurement noise floor of 0 reversals / 0.32 px. Pillow's
`resize(box=...)` takes float coordinates, so the motion is geometrically
exact, and smoothstep easing removes the dead-stop at each cut.

Usage:
    python scripts/assemble_video.py --dir output/my-video
    python scripts/assemble_video.py --dir output/my-video --subtitles
    python scripts/assemble_video.py --dir output/my-video --no-zoom
"""
import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand import BRAND  # noqa: E402
from ffmpeg_pipe import QUIET_ARGS, FfmpegSink, alpha_decoder_args  # noqa: E402
from timing import (  # noqa: E402
    compute_timeline,
    compute_timeline_from_words,
    ffprobe_duration,
    frame_spans,
    load_word_timings,
    smoothstep,
)

WIDTH, HEIGHT = BRAND.canvas.width, BRAND.canvas.height
FPS = BRAND.canvas.fps

_SOURCES: dict[str, Image.Image] = {}


def source_size(zoom):
    """Working size for the stills before cropping.

    Just enough headroom that the most zoomed-in frame still has ~1:1 pixels;
    anything more is wasted resampling work.
    """
    factor = max(1.15, zoom + 0.05)
    return (int(WIDTH * factor) // 2 * 2, int(HEIGHT * factor) // 2 * 2)


def load_source(path, zoom):
    """Fit an image onto a white 16:9 canvas at working resolution, cached."""
    key = str(path)
    if key not in _SOURCES:
        src_w, src_h = source_size(zoom)
        img = Image.open(path).convert("RGB")
        scale = min(src_w / img.width, src_h / img.height)
        fitted = img.resize((max(int(img.width * scale), 1), max(int(img.height * scale), 1)),
                            Image.LANCZOS)
        # White, not black: the art is line work on white, so any letterboxing
        # should vanish into the background.
        canvas = Image.new("RGB", (src_w, src_h), (255, 255, 255))
        canvas.paste(fitted, ((src_w - fitted.width) // 2, (src_h - fitted.height) // 2))
        _SOURCES[key] = canvas
    return _SOURCES[key]


def render_frame(args):
    """One output frame: float-precision centred crop, scaled to 1080p."""
    path, index, n_frames, zoom, zoom_in = args
    src = load_source(path, zoom)

    if zoom <= 1.0:
        return src.resize((WIDTH, HEIGHT), Image.BICUBIC).tobytes()

    progress = smoothstep(index / max(n_frames - 1, 1))
    z = 1.0 + (zoom - 1.0) * (progress if zoom_in else 1.0 - progress)

    crop_w = src.width / z
    crop_h = src.height / z
    left = (src.width - crop_w) / 2.0
    top = (src.height - crop_h) / 2.0
    return src.resize((WIDTH, HEIGHT), Image.BICUBIC,
                      box=(left, top, left + crop_w, top + crop_h)).tobytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="Video assets folder (segments.json, NN.png, narration.*).")
    parser.add_argument("--audio", help="Narration audio path (default: narration.mp3/.wav inside --dir).")
    parser.add_argument("--out", help="Output MP4 path (default: <dir>/final_clean.mp4, "
                                     "or <dir>/final.mp4 when --subtitles is used).")
    parser.add_argument("--subtitles", nargs="?", const="__auto__",
                        help="Burn subtitles in this same pass (auto-detects subtitles.webm/.mov). "
                             "Usually better to leave this off and run burn_subtitles.py after, "
                             "so you keep both a clean and a subtitled version without "
                             "re-rendering the zoom.")
    parser.add_argument("--zoom", type=float, default=1.10,
                        help="Max zoom factor per image (default: 1.10 = 10%% travel).")
    parser.add_argument("--no-zoom", action="store_true", help="Disable the Ken Burns zoom.")
    parser.add_argument("--min-duration", type=float, default=1.2, help="Minimum seconds per image.")
    parser.add_argument("--crf", type=int, default=20, help="x264 quality, lower is better (default: 20).")
    parser.add_argument("--preset", default="veryfast",
                        help="x264 preset (default: veryfast). 'medium'/'slow' shrink the file "
                             "but cost a lot of time on a long video.")
    parser.add_argument("--encoder", choices=("libx264", "h264_videotoolbox"), default="libx264",
                        help="h264_videotoolbox uses the Mac's hardware encoder: much faster, "
                             "slightly larger for the same quality. Default: libx264.")
    parser.add_argument("--jobs", type=int, default=0, help="Parallel frame workers (default: CPU count).")
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("ffmpeg/ffprobe no encontrados. Instala con: brew install ffmpeg")

    video_dir = Path(args.dir)
    segments = json.loads((video_dir / "segments.json").read_text(encoding="utf-8"))

    if args.audio:
        audio_path = Path(args.audio)
    else:
        audio_path = next((video_dir / f"narration{ext}" for ext in (".mp3", ".wav")
                           if (video_dir / f"narration{ext}").exists()), None)
        if audio_path is None:
            sys.exit(f"No encuentro narration.mp3 ni narration.wav en {video_dir}. Pasa --audio.")
    if not audio_path.exists():
        sys.exit(f"No existe el audio: {audio_path}")

    subtitles_path = None
    if args.subtitles:
        if args.subtitles == "__auto__":
            subtitles_path = next((video_dir / f"subtitles{ext}" for ext in (".webm", ".mov")
                                   if (video_dir / f"subtitles{ext}").exists()), None)
            if subtitles_path is None:
                sys.exit(f"No encuentro subtitles.webm ni subtitles.mov en {video_dir}.\n"
                         f"Genéralos con: python scripts/gen_subtitles.py --dir {video_dir}")
        else:
            subtitles_path = Path(args.subtitles)
            if not subtitles_path.exists():
                sys.exit(f"No existe el vídeo de subtítulos: {subtitles_path}")

    # Without subtitles this is the clean master that burn_subtitles.py consumes;
    # with --subtitles it's the finished video, so the names differ.
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = video_dir / ("final.mp4" if subtitles_path else "final_clean.mp4")

    audio_duration = ffprobe_duration(audio_path)

    word_timings = load_word_timings(video_dir)
    if word_timings:
        timeline = compute_timeline_from_words(segments, word_timings, args.min_duration, audio_duration)
    else:
        timeline = compute_timeline(segments, audio_duration, args.min_duration)
    spans = frame_spans(timeline, FPS)
    zoom = 1.0 if args.no_zoom else args.zoom

    images = []
    for seg in segments:
        img = video_dir / f"{seg['index']:02d}.png"
        if not img.exists():
            sys.exit(f"Falta la imagen: {img}")
        images.append(img)

    # One work item per output frame, in presentation order.
    jobs = []
    for img, (_, n_frames), i in zip(images, spans, range(len(images))):
        for f in range(n_frames):
            # Alternate direction so consecutive stills don't all drift the same way.
            jobs.append((str(img), f, n_frames, zoom, i % 2 == 0))
    total = len(jobs)

    cmd = ["ffmpeg", "-y", *QUIET_ARGS,
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "-",
           "-i", str(audio_path)]
    if subtitles_path:
        cmd += [*alpha_decoder_args(subtitles_path),
                "-i", str(subtitles_path),
                "-filter_complex", "[0:v][2:v]overlay=0:0:eof_action=pass:shortest=0,"
                                   "format=yuv420p[v]",
                "-map", "[v]", "-map", "1:a"]
    else:
        cmd += ["-vf", "format=yuv420p", "-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", args.encoder]
    if args.encoder == "libx264":
        cmd += ["-preset", args.preset, "-crf", str(args.crf)]
    else:
        # videotoolbox ignores crf; -q:v is its quality scale (1-100).
        cmd += ["-q:v", "60"]
    cmd += ["-c:a", "aac", "-b:a", "192k",
            "-shortest",
            # moov up front so streaming players find the audio track without
            # downloading the whole file.
            "-movflags", "+faststart",
            str(out_path)]

    print(f"Renderizando {total} frames "
          f"({'zoom ' + format(zoom, 'g') + 'x suavizado' if zoom > 1.0 else 'sin zoom'}"
          f"{', con subtítulos' if subtitles_path else ''})...")

    sink = FfmpegSink(cmd)
    workers = args.jobs if args.jobs > 0 else None
    try:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            # pool.map preserves order -- frames must reach ffmpeg in sequence.
            for i, raw in enumerate(pool.map(render_frame, jobs, chunksize=8), start=1):
                sink.write(raw)
                if i % 300 == 0 or i == total:
                    print(f"  {i}/{total} frames", flush=True)
    except BrokenPipeError:
        pass
    ret = sink.close()
    if ret != 0:
        sys.exit(f"ffmpeg falló ({ret}):\n{sink.errors}")

    extras = []
    if zoom > 1.0:
        extras.append(f"zoom {zoom:g}x")
    if subtitles_path:
        extras.append("subtítulos")
    suffix = f", {' + '.join(extras)}" if extras else ""
    print(f"OK -> {out_path} ({audio_duration:.1f}s{suffix})")


if __name__ == "__main__":
    main()
