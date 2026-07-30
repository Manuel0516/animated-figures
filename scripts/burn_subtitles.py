#!/usr/bin/env python3
"""
Overlay the animated subtitle video onto an already-rendered clean video.

This is the cheap second pass: assemble_video.py does the expensive part
(per-frame Ken Burns zoom rendered in Pillow) once and writes a clean,
subtitle-free master. Burning subtitles then only costs a video re-encode --
no zoom recomputation -- so you keep both deliverables:

    final_clean.mp4   images + zoom + narration, no text
    final.mp4         the same, with animated word-by-word subtitles

Audio is stream-copied, so the narration is bit-identical between the two.

Usage:
    python scripts/burn_subtitles.py --dir output/my-video
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ffmpeg_pipe import QUIET_ARGS, alpha_decoder_args  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="Video assets folder.")
    parser.add_argument("--video", help="Clean input video (default: <dir>/final_clean.mp4).")
    parser.add_argument("--subtitles", help="Subtitle video (default: <dir>/subtitles.webm or .mov).")
    parser.add_argument("--out", help="Output path (default: <dir>/final.mp4).")
    parser.add_argument("--crf", type=int, default=20, help="x264 quality, lower is better (default: 20).")
    parser.add_argument("--preset", default="veryfast", help="x264 preset (default: veryfast).")
    parser.add_argument("--encoder", choices=("libx264", "h264_videotoolbox"), default="libx264",
                        help="h264_videotoolbox uses the Mac hardware encoder (faster).")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg no encontrado. Instala con: brew install ffmpeg")

    video_dir = Path(args.dir)
    video_path = Path(args.video) if args.video else video_dir / "final_clean.mp4"
    if not video_path.exists():
        sys.exit(f"No existe el vídeo limpio: {video_path}\n"
                 f"Genéralo primero con: python scripts/assemble_video.py --dir {video_dir}")

    if args.subtitles:
        subs_path = Path(args.subtitles)
    else:
        subs_path = next((video_dir / f"subtitles{ext}" for ext in (".webm", ".mov")
                          if (video_dir / f"subtitles{ext}").exists()), None)
        if subs_path is None:
            sys.exit(f"No encuentro subtitles.webm ni subtitles.mov en {video_dir}.\n"
                     f"Genéralos con: python scripts/gen_subtitles.py --dir {video_dir}")
    if not subs_path.exists():
        sys.exit(f"No existe el vídeo de subtítulos: {subs_path}")

    out_path = Path(args.out) if args.out else video_dir / "final.mp4"

    cmd = ["ffmpeg", "-y", *QUIET_ARGS,
           "-i", str(video_path),
           *alpha_decoder_args(subs_path),
           "-i", str(subs_path),
           "-filter_complex", "[0:v][1:v]overlay=0:0:eof_action=pass:shortest=0,format=yuv420p[v]",
           "-map", "[v]", "-map", "0:a",
           "-c:v", args.encoder]
    if args.encoder == "libx264":
        cmd += ["-preset", args.preset, "-crf", str(args.crf)]
    else:
        cmd += ["-q:v", "60"]
    cmd += ["-c:a", "copy",          # narration untouched
            "-movflags", "+faststart",
            str(out_path)]

    print(f"Quemando {subs_path.name} sobre {video_path.name}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"ffmpeg falló ({result.returncode}):\n{result.stderr[-2000:]}")

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"OK -> {out_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
