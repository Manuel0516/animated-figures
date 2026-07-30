#!/usr/bin/env python3
"""
Generate one stickman-style image via Gemini's "Nano Banana" image model
(gemini-2.5-flash-image), called directly against the Gemini API (not
OpenRouter). This is the free/cheap path: Google AI Studio's free tier
covers this model with a generous daily quota, using the same GEMINI_API_KEY
already needed for TTS -- see scripts/tts_gemini.py.

For the paid/higher-quality path (OpenRouter + seedream-4.5 or FLUX), use
scripts/gen_image.py instead.

Usage:
    python scripts/gen_image_gemini.py --prompt "A stick figure yawning on a couch" --out output/my-video/01.png
"""
import argparse
import base64
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULT_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
API_URL_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
STYLE = (ROOT / "prompts" / "image_style.txt").read_text(encoding="utf-8").strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True, help="Visual description of this segment (content only, no style instructions).")
    parser.add_argument("--out", required=True, help="Output image path, e.g. output/my-video/01.png")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini image model id (default: {DEFAULT_MODEL})")
    parser.add_argument("--no-style", action="store_true", help="Skip appending the stickman/MS-Paint style block.")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("Falta GEMINI_API_KEY (ponla en .env, la sacas gratis en https://aistudio.google.com/apikey).")

    full_prompt = args.prompt if args.no_style else f"{args.prompt}\n\n{STYLE}"

    resp = requests.post(
        API_URL_TMPL.format(model=args.model),
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": "16:9"},
            },
        },
        timeout=120,
    )
    if not resp.ok:
        sys.exit(f"Gemini image error {resp.status_code}: {resp.text}")

    data = resp.json()
    parts = data["candidates"][0]["content"]["parts"]
    image_part = next((p for p in parts if "inlineData" in p), None)
    if image_part is None:
        sys.exit(f"No se recibió imagen en la respuesta: {data}")

    image_bytes = base64.b64decode(image_part["inlineData"]["data"])
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(image_bytes)
    print(f"OK -> {out_path}")


if __name__ == "__main__":
    main()
