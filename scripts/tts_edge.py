#!/usr/bin/env python3
"""
Turn a script into narration audio using Microsoft Edge's free neural
text-to-speech voices (via the community `edge-tts` package). No API key,
no quota, no cost -- it's the same engine behind Edge's "Read aloud"
feature. Good default when you want $0 narration and don't need Gemini's
slightly more expressive prosody.

Usage:
    python scripts/tts_edge.py --text-file output/my-video/script.txt --out output/my-video/narration.mp3
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import edge_tts
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULT_VOICE = os.environ.get("EDGE_TTS_VOICE", "es-US-PalomaNeural")

# Language -> default voice. run_all.py passes --lang; a direct call can also
# use --lang to pick the right voice without knowing voice names.
LANG_VOICES = {
    "en": os.environ.get("EDGE_TTS_VOICE_EN", "en-US-ChristopherNeural"),
    "es": os.environ.get("EDGE_TTS_VOICE_ES", "es-ES-AlvaroNeural"),
}


async def synthesize(text: str, voice: str, out_path: Path,
                     meta_path: Path | None = None) -> None:
    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    meta = None
    if meta_path:
        meta = open(meta_path, "w", encoding="utf-8")
    try:
        await communicate.save(str(out_path), meta_path)
    finally:
        if meta:
            meta.close()

    if meta_path:
        # Convert JSONL to a clean JSON array of word timings
        words = []
        with open(meta_path, encoding="utf-8") as f:
            for line in f:
                m = json.loads(line)
                if m["type"] == "WordBoundary":
                    words.append(m)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(words, f, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-file", required=True, help="Path to the script text file (e.g. script.txt).")
    parser.add_argument("--out", required=True, help="Output MP3 path, e.g. output/my-video/narration.mp3")
    parser.add_argument("--lang", choices=tuple(LANG_VOICES), default=None,
                        help="Language code: picks the default voice for that language "
                             "(overridden by --voice if both given).")
    parser.add_argument("--voice", default=None, help=f"Edge neural voice name (default: {DEFAULT_VOICE}). List all with: edge-tts --list-voices")
    args = parser.parse_args()

    voice = args.voice or (LANG_VOICES.get(args.lang) if args.lang else None) or DEFAULT_VOICE

    text = Path(args.text_file).read_text(encoding="utf-8").strip()
    if not text:
        sys.exit(f"El archivo {args.text_file} está vacío.")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    word_timings_path = out_path.with_name("word_timings.json")

    asyncio.run(synthesize(text, voice, out_path, word_timings_path))
    print(f"OK -> {out_path} (voz: {voice})")
    print(f"OK -> {word_timings_path} ({len(json.loads(word_timings_path.read_text()))} palabras)")


if __name__ == "__main__":
    main()
