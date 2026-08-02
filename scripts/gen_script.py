#!/usr/bin/env python3
"""
Generate script.txt + project.json for one engineering deep-dive video using
GPT-5.6-luna via the ChatGPT CODEX SUBSCRIPTION (chatgpt.com/backend-api/codex
OAuth) -- NOT OpenRouter. This is the "brain" step of the pipeline: it picks
the concept, writes the ~5-minute script, and emits the full scene plan the
production chain (run_all.py) executes.

Auth: reads the OAuth access token from Hermes' auth store
(~/.hermes/auth.json, providers.openai-codex.tokens.access_token) or from the
CODEX_ACCESS_TOKEN env var. The optional ChatGPT-Account-Id header is derived
from the token's JWT claims when present.

Usage:
    python scripts/gen_script.py --lang en                      # picks concept itself
    python scripts/gen_script.py --lang en --topic "why airplane windows are round"
    python scripts/gen_script.py --lang es
    python scripts/gen_script.py --lang en --model gpt-5.6-sol  # override brain model
"""
import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent

CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"
CODEX_MODEL = os.environ.get("CODEX_SCRIPT_MODEL", "gpt-5.6-luna")
DEFAULT_REASONING_EFFORT = "medium"

# The creative rules live in the master prompt (single source of truth). We
# send it verbatim plus a strict JSON output contract, so the model applies
# the channel format but returns structured data instead of creating files.
OUTPUT_CONTRACT = """

━━━ OUTPUT CONTRACT (MANDATORY) ━━━
You are NOT to create any files and NOT to run any commands. Ignore the
parts of the instructions above that tell you to write files or run
scripts. Instead, respond with ONLY ONE valid JSON object, no markdown
fences, no commentary before or after, with EXACTLY this shape:

{
  "title": "<video title, title-pattern from PART 0>",
  "slug": "<lowercase-hyphenated slug for the folder>",
  "script": "<the FULL narration text from PART 1, plain text, no numbering>",
  "scenes": [
    {
      "index": 1,
      "text": "<narration for this scene>",
      "visual": {
        "type": "still|text-card|diagram",
        ...type-specific fields as specified in PART 2...
      }
    }
  ],
  "diagram_specs": {
    "<relative spec path like diagrams/scene-003.json>": { ...diagram spec JSON... }
  }
}

Rules for the JSON:
- scenes must be the complete ordered list covering the whole script.
- for "still": visual = {"type": "still", "prompt": "<60-120 word detailed
  prompt, content only, no style words>", "src": "<NN.png>"}
- for "text-card": visual = {"type": "text-card", "text": "<short on-screen text>"}
- for "diagram": visual = {"type": "diagram", "spec": "diagrams/scene-NNN.json"}
  AND include that spec under diagram_specs.
- do NOT use "character" scenes.
- the JSON must parse with json.loads as-is.
"""


def _load_codex_token() -> str:
    """OAuth access token: env override, then Hermes auth store."""
    token = os.environ.get("CODEX_ACCESS_TOKEN", "").strip()
    if token:
        return token
    auth_path = Path.home() / ".hermes" / "auth.json"
    if auth_path.exists():
        try:
            data = json.loads(auth_path.read_text(encoding="utf-8"))
            token = (
                data.get("providers", {})
                .get("openai-codex", {})
                .get("tokens", {})
                .get("access_token", "")
            )
            if token:
                return token
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  ! aviso: no se pudo leer {auth_path}: {exc}", file=sys.stderr)
    sys.exit("No se encontró el token OAuth de Codex. Pásalo con "
             "CODEX_ACCESS_TOKEN o haz login en Hermes: hermes auth login openai-codex")


def _chatgpt_account_id(token: str) -> str:
    """Extract ChatGPT-Account-Id from the token's JWT claims, if present."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        acct = claims.get("https://api.openai.com/auth", {}).get("chatgpt_account_id")
        return acct if isinstance(acct, str) else ""
    except Exception:
        return ""


def _stream_response(headers: dict, body: dict) -> str:
    """POST to the Codex Responses API with stream=true (the backend refuses
    non-streaming). Collects output_text deltas from SSE events.
    """
    import json as _json

    resp = requests.post(CODEX_URL, headers=headers, json={**body, "stream": True},
                         timeout=(10, 900), stream=True)
    if resp.status_code != 200:
        sys.exit(f"Codex API error {resp.status_code}: {resp.text[:800]}")

    chunks: list[str] = []
    for raw in resp.iter_lines(decode_unicode=False):
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            event = _json.loads(payload)
        except _json.JSONDecodeError:
            continue
        if event.get("type") == "response.output_text.delta":
            delta = event.get("delta", "")
            if delta:
                chunks.append(delta)
        elif event.get("type") == "error":
            sys.exit(f"Codex error en stream: {_json.dumps(event)[:800]}")
    text = "".join(chunks)
    if not text:
        sys.exit("No hubo texto en la respuesta de Codex (stream vacío).")
    return text


def generate(lang: str, topic: str | None, effort: str, model: str) -> dict:
    prompt_path = ROOT / "prompts" / f"master_prompt_{lang}.txt"
    if not prompt_path.exists():
        sys.exit(f"No existe {prompt_path}")
    master = prompt_path.read_text(encoding="utf-8").strip()

    user_text = master
    if topic:
        user_text += f"\n\nUse this concept (skip PART 0's own selection): {topic}"
    user_text += OUTPUT_CONTRACT

    token = _load_codex_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    acct_id = _chatgpt_account_id(token)
    if acct_id:
        headers["ChatGPT-Account-Id"] = acct_id

    body = {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
        "store": False,
        "reasoning": {"effort": effort, "summary": "auto"},
        "include": [],
    }

    print(f"Generando guión con {model} (Codex OAuth)...")
    output_text = _stream_response(headers, body)

    # Strip markdown fences if the model wrapped the JSON anyway.
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", output_text, re.DOTALL)
    if fence:
        output_text = fence.group(1)
    try:
        return json.loads(output_text)
    except json.JSONDecodeError as exc:
        sys.exit(f"No pude parsear el JSON del guión: {exc}\n--- respuesta ---\n{output_text[:1500]}")


def write_project(payload: dict, out_root: Path) -> Path:
    slug = re.sub(r"[^a-z0-9-]+", "-", (payload.get("slug") or "video").lower()).strip("-")
    video_dir = out_root / slug
    video_dir.mkdir(parents=True, exist_ok=True)

    script = payload.get("script", "").strip()
    if not script:
        sys.exit("El guión está vacío.")
    (video_dir / "script.txt").write_text(script + "\n", encoding="utf-8")

    scenes = payload.get("scenes", [])
    if not scenes:
        sys.exit("project.json sin escenas.")
    # write diagram specs referenced by scenes
    diagram_specs = payload.get("diagram_specs", {}) or {}
    for spec_rel, spec in diagram_specs.items():
        spec_path = video_dir / spec_rel
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  spec diagrama -> {spec_path}")
    # strip diagram_specs before writing scenes (not part of project.json)
    project = scenes
    (video_dir / "project.json").write_text(
        json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  script.txt   -> {video_dir / 'script.txt'} ({len(script.split())} palabras)")
    print(f"  project.json -> {video_dir / 'project.json'} ({len(scenes)} escenas)")
    return video_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", choices=("en", "es"), default="en")
    parser.add_argument("--topic", help="Concept to deep-dive (skips PART 0 selection).")
    parser.add_argument("--effort", choices=("low", "medium", "high"), default=DEFAULT_REASONING_EFFORT)
    parser.add_argument("--model", default=CODEX_MODEL,
                        help=f"Codex brain model (default: {CODEX_MODEL}, env CODEX_SCRIPT_MODEL).")
    parser.add_argument("--out", default=str(ROOT / "output"), help="Output root (default: output/).")
    args = parser.parse_args()

    payload = generate(args.lang, args.topic, args.effort, args.model)
    video_dir = write_project(payload, Path(args.out))
    print(f"\n✅ Guión listo en {video_dir}")
    print(f"   Siguiente paso: python scripts/run_all.py --dir {video_dir} --lang {args.lang}")


if __name__ == "__main__":
    main()
