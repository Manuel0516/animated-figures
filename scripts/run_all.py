#!/usr/bin/env python3
"""
FULLY AUTONOMOUS pipeline driver: takes a project folder (project.json +
script.txt, produced by any code agent reading prompts/master_prompt_*.txt)
and runs the entire production chain with zero human input:

    1. still scenes  -> generate image if missing (Gemini free, OpenRouter fallback)
    2. diagram scenes-> render manim clip if missing
    3. character scenes -> render manim clip if missing
    4. narration     -> edge-tts with a language-appropriate voice
    5. subtitles     -> word-by-word animated subs + .srt
    6. assembly      -> final_clean.mp4 (Ken Burns stills + clips)
    7. burn          -> final.mp4 (subtitles burned in)

It is idempotent: existing assets are kept (a failed image gen is retried on
re-run, a successful one is never regenerated).

Usage:
    python scripts/run_all.py --dir output/why-bridges-dont-collapse --lang en
    python scripts/run_all.py --dir output/... --lang es --image-path openrouter
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# Language -> Edge TTS voice. Override per-language in .env with
# EDGE_TTS_VOICE_EN / EDGE_TTS_VOICE_ES.
DEFAULT_VOICES = {
    "en": "en-US-ChristopherNeural",
    "es": "es-ES-AlvaroNeural",
}

IMAGE_TYPES = {"still"}
MANIM_TYPES = {"diagram", "character"}


def run(cmd, label):
    print(f"\n▶ {label}")
    print(f"  $ {' '.join(map(str, cmd))}")
    result = subprocess.run([str(c) for c in cmd], cwd=str(ROOT))
    if result.returncode != 0:
        sys.exit(f"✗ {label} falló (exit {result.returncode})")
    print(f"✓ {label}")


def scene_visual_type(scene):
    return scene.get("visual", {}).get("type", "still")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, help="Project folder (project.json, script.txt).")
    parser.add_argument("--lang", choices=("en", "es"), default="en",
                        help="Narration language: selects the TTS voice (default: en).")
    parser.add_argument("--image-path", choices=("gemini", "openrouter"), default=None,
                        help="Image backend for still scenes. Default: gemini if GEMINI_API_KEY set, else openrouter.")
    parser.add_argument("--voice", help="Force a specific Edge TTS voice (overrides --lang map).")
    parser.add_argument("--zoom", type=float, default=1.10, help="Ken Burns max zoom for still scenes.")
    parser.add_argument("--no-zoom", action="store_true", help="Disable Ken Burns zoom.")
    parser.add_argument("--image-retries", type=int, default=2,
                        help="Extra regeneration attempts per still when the image "
                             "fails validation (default: 2 = 3 tries total).")
    parser.add_argument("--no-subtitles", action="store_true", help="Skip subtitle generation + burn (clean video only).")
    parser.add_argument("--skip-render", action="store_true",
                        help="Do not render diagrams/characters (assume clips exist).")
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("ffmpeg/ffprobe no encontrados. Instala con: sudo apt install ffmpeg")

    video_dir = Path(args.dir).resolve()
    if not video_dir.exists():
        sys.exit(f"No existe el directorio del proyecto: {video_dir}")

    # Load project (project.json preferred, segments.json legacy fallback)
    project_path = video_dir / "project.json"
    if not project_path.exists():
        sys.exit(f"No existe {project_path}. El driver necesita project.json "
                 f"(genéralo con el master prompt).")
    project = json.loads(project_path.read_text(encoding="utf-8"))

    # --- 1+2+3: ensure visual assets exist -----------------------------------
    stills_needed = [s for s in project if scene_visual_type(s) in IMAGE_TYPES]
    manim_needed = [s for s in project if scene_visual_type(s) in MANIM_TYPES]

    # Pick image backend: prefer OpenRouter when its key is set (user's
    # planned path, best style match per .env.example), else Gemini free tier.
    import os
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    if args.image_path is None:
        args.image_path = "openrouter" if os.environ.get("OPENROUTER_API_KEY") else "gemini"
    image_script = SCRIPTS / ("gen_image.py" if args.image_path == "openrouter" else "gen_image_gemini.py")

    from validate_image import check_image, improve_prompt  # noqa: E402

    max_retries = args.image_retries
    for scene in stills_needed:
        src = video_dir / scene["visual"]["src"]
        prompt = scene["visual"].get("prompt")
        if not prompt:
            sys.exit(f"Escena {scene['index']:02d}: falta visual.prompt en project.json para generar la imagen.")

        # Validate the existing file first (a previous run may have left a
        # corrupt/blank image); regenerate ONLY this one if it fails.
        attempt = 0
        while True:
            ok, reason = check_image(src)
            if ok:
                if attempt == 0:
                    print(f"  = imagen OK: {src.name}")
                else:
                    print(f"  ✓ imagen regenerada y validada: {src.name}")
                break
            if attempt > 0:
                print(f"  ! imagen sigue inválida ({reason}) — intento {attempt + 1}/{max_retries + 1}")
            elif src.exists():
                print(f"  ! imagen inválida ({reason}), regenerando: {src.name}")
            if attempt >= max_retries:
                sys.exit(f"Escena {scene['index']:02d}: {src.name} inválida tras "
                         f"{max_retries + 1} intentos ({reason}). Revisa el prompt o la API.")
            prompt_final = improve_prompt(prompt, reason, attempt) if attempt > 0 else prompt
            run([sys.executable, image_script, "--prompt", prompt_final, "--out", src],
                f"imagen escena {scene['index']:02d}" + (f" (intento {attempt + 1})" if attempt > 0 else ""))
            attempt += 1

    for scene in manim_needed:
        vtype = scene_visual_type(scene)
        spec_rel = scene["visual"].get("spec")
        if not spec_rel:
            sys.exit(f"Escena {scene['index']:02d}: falta visual.spec en project.json.")
        spec = video_dir / spec_rel
        if not spec.exists():
            sys.exit(f"Escena {scene['index']:02d}: no existe el spec {spec}")
        clip_dir = video_dir / ("diagrams" if vtype == "diagram" else "characters")
        clip = clip_dir / f"scene-{scene['index']:03d}.mp4"
        if clip.exists() and clip.stat().st_size > 0:
            print(f"  = clip ya existe: {clip.name}")
            continue
        if args.skip_render:
            print(f"  ! clip no renderizado (--skip-render): {clip.name}")
            continue
        renderer = SCRIPTS / ("render_diagram.py" if vtype == "diagram" else "render_character.py")
        run([sys.executable, renderer, "--spec", spec, "--out", clip],
            f"clip {vtype} escena {scene['index']:02d}")

    # --- 4: narration ---------------------------------------------------------
    script_txt = video_dir / "script.txt"
    if not script_txt.exists():
        sys.exit(f"No existe {script_txt}")
    narration = video_dir / "narration.mp3"
    voice = args.voice or os.environ.get(f"EDGE_TTS_VOICE_{args.lang.upper()}", DEFAULT_VOICES[args.lang])
    if not narration.exists():
        run([sys.executable, SCRIPTS / "tts_edge.py",
             "--text-file", script_txt, "--out", narration, "--voice", voice],
            f"narración ({args.lang}, voz {voice})")
    else:
        print("  = narración ya existe")

    # --- 5: subtitles ---------------------------------------------------------
    if not args.no_subtitles:
        run([sys.executable, SCRIPTS / "gen_subtitles.py", "--dir", video_dir],
            "subtítulos animados + srt")

    # --- 6: assembly ----------------------------------------------------------
    assemble_cmd = [sys.executable, SCRIPTS / "assemble_project.py",
                    "--dir", video_dir, "--audio", narration]
    if args.no_zoom:
        assemble_cmd.append("--no-zoom")
    else:
        assemble_cmd += ["--zoom", str(args.zoom)]
    run(assemble_cmd, "montaje (final_clean.mp4)")

    # --- 7: burn subtitles ----------------------------------------------------
    if not args.no_subtitles:
        run([sys.executable, SCRIPTS / "burn_subtitles.py", "--dir", video_dir],
            "subtítulos quemados (final.mp4)")

    print("\n" + "=" * 60)
    print(f"✅ LISTO: {video_dir}")
    print(f"   final_clean.mp4 (sin subtítulos)")
    if not args.no_subtitles:
        print(f"   final.mp4       (con subtítulos)")
        print(f"   subtitles.srt   (para YouTube)")
    print("=" * 60)


if __name__ == "__main__":
    main()
