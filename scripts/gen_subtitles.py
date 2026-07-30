#!/usr/bin/env python3
"""
Build an ANIMATED SUBTITLE VIDEO as a standalone file with a transparent
background, plus a plain .srt for YouTube.

Words appear ONE BY ONE, each with its own pop-in animation (fade + scale +
slide, with a colour accent that settles to white). The line layout is
computed up front from the full segment text, so revealing a word never
reflows the ones already on screen.

Frames are rasterized with Pillow and piped straight into ffmpeg. Pillow does
the text work because Homebrew's default ffmpeg ships without libass and
libfreetype (no `subtitles`/`drawtext` filters), and per-word animation needs
per-frame control that subtitle formats can't express anyway.

Usage:
    python scripts/gen_subtitles.py --dir output/my-video
    python scripts/gen_subtitles.py --dir output/my-video --format mov
"""
import argparse
import json
import math
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ffmpeg_pipe import QUIET_ARGS, FfmpegSink  # noqa: E402
from timing import (  # noqa: E402
    compute_timeline,
    compute_timeline_from_words,
    ffprobe_duration,
    frame_spans,
    load_word_timings,
    match_words_to_timings,
    smoothstep,
)

WIDTH, HEIGHT = 1920, 1080
FPS = 30
# Subtitles occupy a band near the bottom, so only that band is rasterized and
# it gets padded out to full frame once, in ffmpeg.
STRIP_HEIGHT = 400
SIDE_MARGIN = 120

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

VIDEO_FORMATS = {
    "webm": {
        "suffix": ".webm",
        "args": ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                 "-b:v", "0", "-crf", "32", "-deadline", "good", "-cpu-used", "4",
                 "-auto-alt-ref", "0", "-row-mt", "1"],
    },
    "mov": {
        "suffix": ".mov",
        "args": ["-c:v", "qtrle", "-pix_fmt", "argb"],
    },
    "prores": {
        "suffix": ".mov",
        "args": ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"],
    },
}


@dataclass
class Word:
    tile: Image.Image        # final look: white fill, black outline
    accent: Image.Image      # same glyphs in the accent colour
    x: int                   # resting position within the strip
    y: int
    reveal: float            # seconds after the segment starts


def find_font(explicit):
    if explicit:
        if not Path(explicit).exists():
            sys.exit(f"No existe la fuente: {explicit}")
        return explicit
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    sys.exit("No se encontró una fuente bold. Pasa una con --font /ruta/a/fuente.ttf")


def render_word_tile(word, font, stroke, fill):
    """One word on its own transparent tile, with the outline baked in.

    The tile is sized from the FONT METRICS (ascent/descent + advance width),
    never from the word's own ink bbox. Ink bboxes vary per word -- "Sabías"
    starts 11 px down, "casa" 23 px down -- so tiles cut to ink and aligned by
    their tops put words on different baselines, and short words float visibly
    high. Uniform metric-based tiles mean aligning tile tops == aligning
    baselines.
    """
    ascent, descent = font.getmetrics()
    width = int(math.ceil(font.getlength(word))) + 2 * stroke
    height = ascent + descent + 2 * stroke
    tile = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text(
        (stroke, stroke), word, font=font,
        fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0, 255),
        anchor="la",  # left / ascender: same reference line for every word
    )
    return tile


def layout_words(text, font, stroke, line_spacing, accent, duration, reveal_fraction,
                 slide=0, word_reveals=None):
    """Wrap the segment into lines and assign each word a resting spot + cue time.

    If *word_reveals* is provided (a list of per-word start times in seconds
    relative to the segment start), those are used instead of the character-
    count-based approximation.  This lets edge-tts word boundaries drive the
    subtitle animation, keeping it in perfect sync with the audio.
    """
    words = text.split()
    if not words:
        return []

    space = font.getlength(" ")
    widths = [font.getlength(w) for w in words]
    max_width = WIDTH - 2 * SIDE_MARGIN

    lines, current, current_w = [], [], 0.0
    for i, w in enumerate(words):
        extra = widths[i] + (space if current else 0)
        if current and current_w + extra > max_width:
            lines.append(current)
            current, current_w = [i], widths[i]
        else:
            current.append(i)
            current_w += extra
    if current:
        lines.append(current)

    ascent, descent = font.getmetrics()
    line_height = ascent + descent + line_spacing
    block_height = line_height * len(lines)
    base_y = STRIP_HEIGHT - block_height - stroke - int(math.ceil(slide))

    if word_reveals is not None:
        reveal_window = duration
        weights = [1] * len(words)
    else:
        weights = [len(words[i]) + 1 for i in range(len(words))]
        reveal_window = duration * reveal_fraction
    total_weight = sum(weights)

    out, cumulative = [], 0.0
    for line_index, line in enumerate(lines):
        line_w = sum(widths[i] for i in line) + space * (len(line) - 1)
        x = (WIDTH - line_w) / 2
        y = base_y + line_index * line_height
        for i in line:
            if word_reveals is not None and i < len(word_reveals):
                reveal = word_reveals[i]
            else:
                reveal = reveal_window * (cumulative / total_weight)
            cumulative += weights[i]
            out.append(Word(
                tile=render_word_tile(words[i], font, stroke, (255, 255, 255, 255)),
                accent=render_word_tile(words[i], font, stroke, accent),
                x=int(round(x)) - stroke,
                y=int(round(y)) - stroke,
                reveal=reveal,
            ))
            x += widths[i] + space
    return out


def scaled(tile, scale, alpha):
    """Tile scaled about its own centre, with its alpha attenuated."""
    w = max(int(round(tile.width * scale)), 1)
    h = max(int(round(tile.height * scale)), 1)
    out = tile.resize((w, h), Image.BICUBIC)
    if alpha < 1.0:
        out.putalpha(out.getchannel("A").point(lambda a: int(a * alpha)))
    return out


def paste_centered(canvas, tile, word, dy=0):
    """Composite a (possibly rescaled) tile keeping the word's centre fixed."""
    cx = word.x + word.tile.width / 2
    cy = word.y + word.tile.height / 2
    canvas.alpha_composite(tile, (int(round(cx - tile.width / 2)),
                                  int(round(cy - tile.height / 2 + dy))))


def render_segment_frames(words, n_frames, pop, slide, fade, duration):
    """Yield one RGBA strip per frame for a single segment."""
    # Words that have finished animating are baked into `base` once, so the
    # per-frame cost stays flat no matter how many words are on screen.
    base = Image.new("RGBA", (WIDTH, STRIP_HEIGHT), (0, 0, 0, 0))
    baked = 0
    order = sorted(range(len(words)), key=lambda i: words[i].reveal)

    for f in range(n_frames):
        t = f / FPS
        while baked < len(order) and t >= words[order[baked]].reveal + pop:
            w = words[order[baked]]
            base.alpha_composite(w.tile, (w.x, w.y))
            baked += 1

        in_flight = [i for i in order[baked:] if words[i].reveal <= t]
        if in_flight:
            frame = base.copy()
            for i in in_flight:
                w = words[i]
                p = smoothstep((t - w.reveal) / pop)
                scale = 0.72 + 0.28 * p
                dy = slide * (1.0 - p)
                # Cross-fade accent -> white so the newest word catches the eye.
                paste_centered(frame, scaled(w.tile, scale, p), w, dy)
                if p < 1.0:
                    paste_centered(frame, scaled(w.accent, scale, (1.0 - p) * 0.9), w, dy)
        else:
            frame = base

        # Whole-strip fade at the very end of the segment.
        remaining = duration - t
        if remaining < fade:
            factor = max(remaining / fade, 0.0)
            frame = frame.copy() if frame is base else frame
            frame.putalpha(frame.getchannel("A").point(lambda a: int(a * factor)))

        yield frame


def seconds_to_srt(t):
    hours, rem = divmod(t, 3600)
    minutes, seconds = divmod(rem, 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis == 1000:
        seconds += 1
        millis = 0
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d},{millis:03d}"


def write_srt(segments, timeline, out_path):
    blocks = []
    for i, (seg, (start, end, _)) in enumerate(zip(segments, timeline), start=1):
        blocks.append(f"{i}\n{seconds_to_srt(start)} --> {seconds_to_srt(end)}\n{seg['text'].strip()}\n")
    out_path.write_text("\n".join(blocks), encoding="utf-8")


def parse_color(text):
    text = text.lstrip("#")
    if len(text) != 6:
        sys.exit(f"Color inválido: {text} (usa formato hex, p.ej. FFD24A)")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="Video assets folder (contains segments.json and the narration).")
    parser.add_argument("--audio", help="Narration audio path (default: narration.mp3 or narration.wav inside --dir).")
    parser.add_argument("--out", help="Output subtitle video path (default: <dir>/subtitles.<ext>).")
    parser.add_argument("--srt", help="Output SRT path (default: <dir>/subtitles.srt).")
    parser.add_argument("--format", choices=sorted(VIDEO_FORMATS), default="webm",
                        help="Alpha video format: webm (VP9, small, Chrome/VLC), "
                             "mov (qtrle lossless, large), prores (QuickTime/FCP). Default: webm.")
    parser.add_argument("--font", help="Path to a bold .ttf font.")
    parser.add_argument("--font-size", type=int, default=64, help="Font size in px (default: 64).")
    parser.add_argument("--stroke", type=int, default=8, help="Black outline thickness in px (default: 8).")
    parser.add_argument("--line-spacing", type=int, default=10, help="Extra px between wrapped lines (default: 10).")
    parser.add_argument("--pop", type=float, default=0.18, help="Seconds each word takes to animate in (default: 0.18).")
    parser.add_argument("--slide", type=float, default=14, help="Px each word rises as it pops in (default: 14).")
    parser.add_argument("--fade", type=float, default=0.18, help="Seconds the block fades out at segment end (default: 0.18).")
    parser.add_argument("--accent", default="FFD24A", help="Hex colour flashed on the newest word (default: FFD24A).")
    parser.add_argument("--reveal-fraction", type=float, default=0.7,
                        help="Fraction of each segment used to reveal all its words (default: 0.7).")
    parser.add_argument("--margin-bottom", type=int, default=70, help="Px from strip bottom to frame bottom (default: 70).")
    parser.add_argument("--min-duration", type=float, default=1.2, help="Minimum seconds per subtitle.")
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

    video_format = VIDEO_FORMATS[args.format]
    out_path = Path(args.out) if args.out else video_dir / f"subtitles{video_format['suffix']}"
    srt_path = Path(args.srt) if args.srt else video_dir / "subtitles.srt"

    audio_duration = ffprobe_duration(audio_path)

    word_timings = load_word_timings(video_dir)
    matched_word_timings = None
    if word_timings:
        matched_word_timings = match_words_to_timings(segments, word_timings)
        if matched_word_timings is None:
            print("  La sincronización palabra a palabra no está disponible "
                  "(los timings de Edge TTS no coinciden con el guión). "
                  "Usando temporización aproximada por conteo de caracteres.", file=sys.stderr)

    if matched_word_timings:
        timeline = compute_timeline_from_words(segments, word_timings, args.min_duration, audio_duration)
    else:
        timeline = compute_timeline(segments, audio_duration, args.min_duration)
    spans = frame_spans(timeline, FPS)

    write_srt(segments, timeline, srt_path)
    print(f"OK -> {srt_path}")

    font = ImageFont.truetype(find_font(args.font), args.font_size)
    accent = parse_color(args.accent)
    strip_top = HEIGHT - STRIP_HEIGHT - args.margin_bottom

    cmd = ["ffmpeg", "-y", *QUIET_ARGS,
           "-f", "rawvideo", "-pix_fmt", "rgba",
           "-s", f"{WIDTH}x{STRIP_HEIGHT}", "-r", str(FPS), "-i", "-",
           "-vf", f"pad=w={WIDTH}:h={HEIGHT}:x=0:y={strip_top}:color=0x00000000",
           "-frames:v", str(sum(n for _, n in spans))]
    cmd += video_format["args"]
    cmd += [str(out_path)]

    sink = FfmpegSink(cmd)
    total = sum(n for _, n in spans)
    written = 0
    try:
        for seg, (_, _, dur), (_, n_frames) in zip(segments, timeline, spans):
            word_reveals = None
            if matched_word_timings:
                matched = matched_word_timings[seg["index"] - 1]["words"]
                wr = [w["reveal"] for w in matched]
                if len(wr) == len(seg["text"].split()):
                    word_reveals = wr
            words = layout_words(seg["text"].strip(), font, args.stroke, args.line_spacing,
                                 accent, dur, args.reveal_fraction, args.slide,
                                 word_reveals=word_reveals)
            for frame in render_segment_frames(words, n_frames, args.pop, args.slide,
                                               args.fade, dur):
                sink.write(frame.tobytes())
                written += 1
            print(f"  [{seg['index']:02d}] {len(words)} palabras, {n_frames} frames "
                  f"({'sync' if word_reveals else 'approx'}) "
                  f"({written}/{total})", flush=True)
    except BrokenPipeError:
        pass
    ret = sink.close()
    if ret != 0:
        sys.exit(f"ffmpeg falló ({ret}):\n{sink.errors}")

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"OK -> {out_path} ({audio_duration:.1f}s, {len(segments)} subtítulos, {size_mb:.1f} MB)")
    print("Nota: vídeo con canal alfa. El fondo transparente se ve negro (o no abre) "
          "en algunos reproductores; es normal. El resultado real es final.mp4.")


if __name__ == "__main__":
    main()
