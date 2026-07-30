#!/usr/bin/env python3
"""
Turn a script into narration audio using Google Gemini's dedicated TTS models.

Why Gemini and not OpenRouter: OpenRouter's only audio-output models
(openai/gpt-audio, openai/gpt-audio-mini) are conversational voice models,
not scripted TTS -- tested with several prompting strategies and they kept
prepending chatter ("Claro, aquí va la frase...") instead of reading the
text verbatim. Gemini's *-tts models are dedicated text-to-speech engines
with no chat behavior, so they narrate exactly the text given.

Usage:
    python scripts/tts_gemini.py --text-file output/my-video/script.txt --out output/my-video/narration.wav
"""
import argparse
import base64
import os
import struct
import sys
import wave
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULT_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
DEFAULT_VOICE = os.environ.get("GEMINI_TTS_VOICE", "Kore")
API_URL_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int, channels: int = 1, sample_width: int = 2) -> bytes:
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(sample_rate)
        w.writeframes(pcm_bytes)
    return buf.getvalue()


def parse_sample_rate(mime_type: str) -> int:
    # e.g. "audio/L16;codec=pcm;rate=24000"
    for part in mime_type.split(";"):
        part = part.strip()
        if part.startswith("rate="):
            return int(part.split("=", 1)[1])
    return 24000


def synthesize(text: str, api_key: str, model: str, voice: str) -> bytes:
    resp = requests.post(
        API_URL_TMPL.format(model=model),
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
                },
            },
        },
        timeout=180,
    )
    if not resp.ok:
        sys.exit(f"Gemini TTS error {resp.status_code}: {resp.text}")

    data = resp.json()
    part = data["candidates"][0]["content"]["parts"][0]
    inline = part["inlineData"]
    pcm = base64.b64decode(inline["data"])
    sample_rate = parse_sample_rate(inline.get("mimeType", "audio/L16;rate=24000"))
    return pcm_to_wav_bytes(pcm, sample_rate)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-file", required=True, help="Path to the script text file (e.g. script.txt).")
    parser.add_argument("--out", required=True, help="Output WAV path, e.g. output/my-video/narration.wav")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini TTS model id (default: {DEFAULT_MODEL})")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help=f"Gemini prebuilt voice name (default: {DEFAULT_VOICE})")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("Falta GEMINI_API_KEY (ponla en .env, la sacas gratis en https://aistudio.google.com/apikey).")

    text = Path(args.text_file).read_text(encoding="utf-8").strip()
    wav_bytes = synthesize(text, api_key, args.model, args.voice)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(wav_bytes)
    print(f"OK -> {out_path}")


if __name__ == "__main__":
    main()
