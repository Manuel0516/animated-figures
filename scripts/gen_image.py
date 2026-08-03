#!/usr/bin/env python3
"""
Generate one stickman-style image via OpenRouter (FLUX) and save it to disk.

Meant to be called from Claude Code / Codex's own Bash tool, once per visual
segment — the agent writes the topic/script/segmentation itself (no API call
needed for that part) and just shells out to this script for each image.

Usage:
    python scripts/gen_image.py --prompt "A stick figure yawning on a couch" --out output/my-video/01.png
    python scripts/gen_image.py --prompt "..." --out 02.png --model black-forest-labs/flux.2-flex
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

OPENROUTER_URL = "https://openrouter.ai/api/v1/images"
DEFAULT_MODEL = os.environ.get("OPENROUTER_IMAGE_MODEL", "black-forest-labs/flux.2-klein-4b")
STYLE = (ROOT / "prompts" / "image_style.txt").read_text(encoding="utf-8").strip()

ASPECTS = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0}


def _crop_to_aspect(img, target: float):
    """Center-crop an image to the target aspect ratio."""
    from PIL import Image
    w, h = img.size
    if abs(w / h - target) <= 0.01:
        return img
    if w / h > target:  # too wide -> crop sides
        new_w = int(h * target)
        x0 = (w - new_w) // 2
        return img.crop((x0, 0, x0 + new_w, h))
    new_h = int(w / target)  # too tall -> crop top/bottom
    y0 = (h - new_h) // 2
    return img.crop((0, y0, w, y0 + new_h))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True, help="Visual description of this segment (content only, no style instructions).")
    parser.add_argument("--out", required=True, help="Output PNG path, e.g. output/my-video/01.png")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenRouter image model id (default: {DEFAULT_MODEL})")
    parser.add_argument("--aspect", choices=tuple(ASPECTS), default=os.environ.get("IMAGE_ASPECT", "16:9"),
                        help=f"Aspect ratio (default: 16:9, env IMAGE_ASPECT).")
    parser.add_argument("--no-style", action="store_true", help="Skip appending the stickman/MS-Paint style block (prompt already contains full styling).")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("Falta OPENROUTER_API_KEY (ponla en .env o expórtala en el entorno).")

    full_prompt = args.prompt if args.no_style else f"{args.prompt}\n\n{STYLE}"

    resp = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": args.model,
            "prompt": full_prompt,
            "aspect_ratio": args.aspect,
        },
        timeout=120,
    )
    if not resp.ok:
        sys.exit(f"OpenRouter error {resp.status_code}: {resp.text}")

    b64 = resp.json()["data"][0]["b64_json"]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw = base64.b64decode(b64)
    # Enforce the requested aspect: decode, center-crop, save as PNG.
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img = _crop_to_aspect(img, ASPECTS[args.aspect])
    img.save(out_path, "PNG")
    print(f"OK -> {out_path} ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    main()
