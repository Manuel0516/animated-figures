# Vídeos Stickman Faceless — sin Magnific, con cualquier agente de código

Adaptación del sistema ["Vídeos Stickman Faceless con Claude 2026"](https://ale-ferr.notion.site/V-deos-Stickman-Faceless-con-Claude-2026-39a43d6a4e9780839821c3bdc49d1b92).

## ⚡ MODO AUTÓNOMO (flujo recomendado)

Pipeline totalmente automático, sin intervención humana, para el nicho de
**inmersión en ingeniería (deep dive)**: UN concepto de ingeniería por
vídeo, explicado en profundidad durante **~5 minutos (700-800 palabras)**.
Formato: qué es → cómo funciona → por qué funciona → ejemplos reales →
dato final. **Idioma activo: inglés** (`--lang en`); el prompt en español
está listo pero el canal publica en inglés por ahora.

**Mascota del canal:** un **ingeniero de palo con casco amarillo brillante**
(solo en imágenes IA — NO existe versión manim). El estilo del personaje se
inyecta automáticamente en cada `still` vía `prompts/image_style.txt`;
los prompts de imagen solo describen qué está haciendo el ingeniero.

**El "cerebro" (guión):** se genera con **gpt-5.6-luna vía la suscripción de
ChatGPT Codex** (`chatgpt.com/backend-api/codex`, OAuth) — NO OpenRouter.
`scripts/gen_script.py` lee el master prompt, aplica el formato del canal y
escribe `script.txt` + `project.json` (+ specs de diagrama). El token OAuth
se lee de `~/.hermes/auth.json` (login: `hermes auth login openai-codex`) o
de la env var `CODEX_ACCESS_TOKEN`. El modelo por defecto se puede cambiar
con `--model` o la env var `CODEX_SCRIPT_MODEL`.

Flujo completo (2 comandos, 100% autónomo):

```bash
# 1) El cerebro: gpt-5.6-sol (Codex subscription) elige concepto + escribe guión
python scripts/gen_script.py --lang en                          # o --topic "..."

# 2) La fábrica: imágenes (OpenRouter), manim, narración, subtítulos, montaje
python scripts/run_all.py --dir output/<slug> --lang en
```

1. Copia `prompts/master_prompt_en.txt` (inglés) o `prompts/master_prompt_es.txt`
   (español) en tu agente de código (Claude Code, Codex, opencode, Hermes...).
   El agente elige el tema, escribe el guión (3 min) y genera `project.json`
   con escenas de DOS tipos: `still` (~85%, imagen IA 100% visual) y
   `text-card` (~15%, tipografía Pillow nítida).
2. Ejecuta el driver único que lo hace TODO:

   ```bash
   python scripts/run_all.py --dir output/<slug> --lang en   # o --lang es
   ```

   `run_all.py` genera lo que falta (imágenes, narración, subtítulos) y
   monta `final.mp4` + `final_clean.mp4` + `subtitles.srt`.
   Es **idempotente**: los assets ya generados se conservan.

**Regla de oro del diseño:** las imágenes IA son 100% visuales — NUNCA
llevan texto, etiquetas ni números (los modelos de imagen los garabatean).
Todo el texto (nombres, cifras, etiquetas) vive en las escenas `text-card`,
que se renderizan con Pillow y salen nítidas. Manim está desactivado; las
escenas `diagram`/`character` antiguas se convierten automáticamente a
text-card.

**Imágenes:** por defecto usa OpenRouter si hay `OPENROUTER_API_KEY`
(modelo `seedream-4.5`, ~$0.04/img — el mejor match del estilo garabato),
y si no, cae a Gemini `GEMINI_API_KEY` (cuota gratuita). Las escenas
`text-card` no necesitan ninguna API.

**Validación de imágenes:** cada `still` se valida tras generarse
(`scripts/validate_image.py`: tamaño, decodificación, aspecto 16:9, no en
blanco). Si una imagen falla, se regenera SOLO esa con un prompt mejorado
(instrucción de arreglo según el motivo del fallo), hasta
`--image-retries` reintentos (por defecto 2 → 3 intentos). Re-ejecutar
`run_all.py` también re-valida las imágenes existentes y regenera las que
estén corruptas o en blanco. Chequeo standalone:
`python scripts/validate_image.py --dir output/<slug>`.

**Idiomas:** `--lang en|es` elige la voz de narración automáticamente
(`EDGE_TTS_VOICE_EN` / `EDGE_TTS_VOICE_ES` en `.env`, por defecto
en-US-ChristopherNeural / es-ES-AlvaroNeural). Subtítulos y SRT salen en el
idioma del guión.

> El flujo LEGACY (imagen por segmento vía `segments.json` +
> `assemble_video.py`) sigue funcionando; el modo autónomo usa
> `project.json` + `assemble_project.py`.

---

El original usa **Claude Desktop + Magnific (vía MCP)** para las imágenes y
**Google AI Studio manual** para la voz. Aquí todo el flujo queda scriptado:

1. Un **agente de código con Bash** (Claude Code, Codex, [opencode](https://opencode.ai)
   con DeepSeek/GLM/Kimi/etc., o cualquier otro con herramientas de
   archivos + terminal) escribe el tema, el guión y la segmentación
   directamente en la conversación, leyendo `prompts/master_prompt.txt`.
   No hay llamada a ninguna API de texto para esto — nada aquí depende de
   qué agente o modelo uses.
2. Para las imágenes, el agente ejecuta un script pequeño por su cuenta
   (Bash), una vez por segmento.
3. Para la voz, otro script genera el audio de narración completo.
4. `scripts/assemble_video.py` combina imágenes + audio con `ffmpeg` en un
   único MP4.

No hace falta MCP ni API key de Anthropic.

## Dos niveles: gratis y de pago

| Paso | Gratis (por defecto) | De pago (mejor calidad / sin cuota) |
|---|---|---|
| Imágenes | `scripts/gen_image_gemini.py` — Gemini 2.5 Flash Image ("Nano Banana"), cuota diaria gratuita en Google AI Studio | `scripts/gen_image.py` — OpenRouter + `seedream-4.5` (~$0.04/imagen) |
| Voz | `scripts/tts_edge.py` — Microsoft Edge TTS, sin API key, sin cuota, gratis siempre | `scripts/tts_gemini.py` — Gemini TTS (~$0.015/min, cuota gratuita también disponible) |
| Montaje | `scripts/assemble_video.py` — ffmpeg local | (igual, siempre gratis) |

`prompts/master_prompt.txt` ya usa el camino gratis por defecto y solo cae al
de pago si la cuota se agota o si pides explícitamente más calidad.

### Sobre "Google Flow" y Nano Banana

Google Flow (labs.google/flow) es una app web de creación (basada en Veo +
Imagen) pensada para uso manual en el navegador — no tiene API pública, así
que no es automatizable desde un script. El modelo de imagen que la hace
famosa, **Nano Banana** (`gemini-2.5-flash-image`), sí es accesible
directamente por API vía Google AI Studio, y es justo lo que usa
`gen_image_gemini.py`.

### ¿Es gratis Google AI Studio para generar imágenes?

Sí: el free tier de Gemini incluye `gemini-2.5-flash-image` con una cuota
diaria generosa (los límites exactos dependen de tu cuenta — Google no
publica un número fijo en la documentación estática; compruébalos en
[aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit) una
vez tengas tu key). Para un vídeo de este tamaño (20-100 imágenes) suele
sobrar de sobra dentro de la cuota gratuita.

## Coste aproximado por vídeo

**Camino 100% gratis** (Nano Banana + Edge TTS, dentro de cuota): **$0**.

**Camino de pago** (con el guión de prueba: homelab, 442 palabras, 27 imágenes):

| Paso | Modelo | Coste |
|---|---|---|
| Imágenes (27 × $0.04) | `seedream-4.5` (OpenRouter) | ~$1.08 |
| Voz (~3 min) | `gemini-2.5-flash-preview-tts` | ~$0.05 |
| Montaje (ffmpeg local) | — | $0.00 |
| **Total** | | **~$1.13** |

Para un vídeo "completo" según la especificación original (~1.200 palabras,
~8 minutos, ~80-100 segmentos): imágenes ~$3.60 + voz ~$0.12 ≈ **~$3.70-$4.00**
en el camino de pago, o **$0** en el camino gratis.

## Compatibilidad con otros agentes (opencode + DeepSeek, etc.)

Nada en este proyecto llama a la API de Anthropic ni depende de Claude
específicamente: el "cerebro" que escribe el guión y decide qué comandos
ejecutar es el propio agente que uses. Para usarlo con
[opencode](https://opencode.ai) + DeepSeek V4 Flash (o cualquier otro
modelo/proveedor que opencode soporte):

1. Configura opencode con tu proveedor (DeepSeek, GLM, Kimi...) como de costumbre.
2. Abre opencode en esta carpeta.
3. Pega `prompts/master_prompt.txt` como mensaje inicial, igual que harías en Claude Code.

El agente necesita poder leer/escribir archivos y ejecutar comandos de Bash
— eso es todo lo que este flujo requiere.

## Instalación

```bash
cd /Users/manuel/Desktop/Animated-figures
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
brew install ffmpeg pango   # pango (+ cairo, que suele venir con él) hace falta para manim
cp .env.example .env
# edita .env y añade:
#   GEMINI_API_KEY      -> https://aistudio.google.com/apikey (imágenes gratis + voz)
#   OPENROUTER_API_KEY  -> https://openrouter.ai/keys (solo si quieres el camino de pago)
```

Los diagramas (`scripts/render_diagram.py`) usan un [Nerd Font](https://www.nerdfonts.com/)
como tipografía (`brand.yaml` → `typography.diagram_family`, por defecto
`JetBrainsMono Nerd Font`) para poder usar sus glifos de icono (portátil,
servidor, nube, candado...) como pictogramas simples en los nodos, sin
necesitar assets SVG aparte. Instálalo si no lo tienes:

```bash
brew install --cask font-jetbrains-mono-nerd-font
```

## Uso

1. Abre tu agente de código (Claude Code, Codex, opencode...) en esta carpeta.
2. Pega el contenido de [`prompts/master_prompt_es.txt`](prompts/master_prompt_es.txt)
   (o [`master_prompt_en.txt`](prompts/master_prompt_en.txt) en inglés) como tu
   mensaje (opcionalmente añade tu propio tema al final).
3. El agente escribirá el guión, lo segmentará con prompts de imagen muy
   detallados, generará las imágenes, la narración, los subtítulos animados y
   montará el vídeo final — todo ejecutando los scripts de `scripts/` por su
   cuenta.

Salida esperada en `output/<tema-en-slug>/`:

```
output/homelab-vpn-wireguard-wol/
  script.txt        # guión completo
  segments.json     # texto + prompt visual detallado de cada segmento
  01.png ... NN.png
  narration.mp3      # voz (Edge TTS, gratis) o narration.wav (Gemini TTS)
  subtitles.webm     # subtítulos animados, fondo transparente (vídeo aparte)
  subtitles.srt      # mismos subtítulos en SRT, para subir a YouTube
  final_clean.mp4    # imágenes con zoom + audio, SIN subtítulos
  final.mp4          # lo mismo, CON los subtítulos animados quemados
```

### Dos versiones: limpia y con subtítulos

El montaje va en dos pasos a propósito, así te quedan las dos versiones y el
zoom (que es la parte cara) se renderiza una sola vez:

```bash
python scripts/assemble_video.py --dir output/<tema>   # -> final_clean.mp4 (sin texto)
python scripts/burn_subtitles.py --dir output/<tema>   # -> final.mp4 (con subtítulos)
```

El segundo paso solo recodifica el vídeo y copia el audio tal cual (`-c:a copy`),
así que la narración es idéntica en las dos versiones y tarda una fracción de lo
que tardó el primero.

### Subtítulos palabra por palabra

Los subtítulos se generan como **vídeo independiente** con fondo transparente
(canal alfa). Así puedes re-estilarlos sin volver a renderizar el vídeo, o
llevarlos a CapCut/Premiere como capa aparte:

```bash
python scripts/gen_subtitles.py --dir output/<tema>
# opciones: --font-size 72 --stroke 10 --pop 0.22 --slide 20 --accent FF5555
```

Las palabras aparecen **una a una**, cada una con su propia animación de
entrada (fade + escala + slide, con un destello de color que se asienta en
blanco). La distribución de las líneas se calcula antes con el texto completo,
así que al aparecer una palabra las anteriores **no se recolocan**. El reparto
de tiempos pondera por longitud de palabra, que aproxima mejor el habla que
repartir a partes iguales.

Formatos disponibles con `--format` (los tres se superponen igual en el montaje;
cambian el tamaño y qué programas los abren):

| `--format` | Archivo | Tamaño (~160s) | Se abre en |
|---|---|---|---|
| `webm` (por defecto) | `subtitles.webm` | ~3 MB | Chrome, VLC (no QuickTime) |
| `mov` | `subtitles.mov` | ~144 MB (sin pérdidas) | ffmpeg, editores; QuickTime a veces no |
| `prores` | `subtitles.mov` | muy grande | QuickTime, Final Cut, Premiere |

> **Si te da error al abrir el vídeo de subtítulos:** comprueba primero que el
> render haya terminado. ffmpeg escribe el índice (`moov`) al final del archivo,
> así que un `.mov` a medio generar existe y ocupa MBs pero **no se puede abrir**
> hasta que el proceso acaba. Además es un vídeo con canal alfa: el fondo
> transparente se ve negro en muchos reproductores, y eso es normal — para ver
> el resultado real mira `final.mp4`.

Los tiempos salen de `scripts/timing.py`, el mismo módulo que usa
`assemble_video.py` para las imágenes — por eso nunca se desincronizan.

### Zoom suave (sin temblor)

Cada imagen lleva un **zoom tipo Ken Burns** que alterna acercamiento y
alejamiento, con easing (`smoothstep`) para que no arranque ni pare en seco:

```bash
python scripts/assemble_video.py --dir output/<tema>
# --zoom 1.15                    -> zoom más marcado (por defecto 1.10)
# --no-zoom                      -> desactivarlo
# --encoder h264_videotoolbox    -> codificar por hardware (mucho más rápido en Mac)
# --preset medium                -> archivo más pequeño, bastante más lento
```

El zoom **no** usa el filtro `zoompan` de ffmpeg, que redondea su ventana de
recorte a píxeles enteros: a las velocidades lentas de este estilo (~0,25 px de
desplazamiento por frame) eso hace que el movimiento avance «0 px, 0 px, 1 px,
0 px…», que es exactamente el temblor que se veía. Medido con un patrón de
prueba:

| Método | Error vs geometría exacta | Cambios de dirección |
|---|---|---|
| ffmpeg `zoompan` | 0,240 px (máx 0,555) | 18 de 58 |
| Pillow con caja float (actual) | **0,017 px** (máx 0,033) | **0** |

Por eso los frames se rasterizan en Pillow, cuyo `resize(box=...)` acepta
coordenadas decimales y da un movimiento geométricamente exacto.

## Identidad de marca (brand.yaml)

`brand.yaml`, en la raíz del repo, es la única fuente de verdad para el
canvas (1920×1080/30fps), la paleta (fondo casi negro `#0E0E10`, tinta
`#F5F3EC`, acento dorado `#FFD24A` — el mismo que ya usaban los subtítulos
por defecto), tipografía y timing de las animaciones (`0.18s`, `smoothstep`).
`scripts/brand.py` lo carga una sola vez (`from brand import BRAND`) y
`gen_subtitles.py`/`assemble_video.py` leen sus constantes de ahí en vez de
tener cada uno su propia copia hardcodeada.

## Vídeos con metraje real + diagramas (project.json)

Para vídeos que mezclan tu propio metraje con diagramas de ingeniería
(en vez del formato antiguo de una imagen generada por segmento),
`project.json` sustituye a `segments.json`: mismo array plano de escenas
con `index`/`text` (así `timing.py` no cambia), pero cada escena añade un
objeto `visual` que dice cómo se renderiza:

```json
{"type": "footage", "src": "footage/raw/found-parts.mov", "in": 4.0, "out": 9.5, "confirmed": true}
{"type": "diagram", "spec": "diagrams/scene-003.json"}
{"type": "character", "spec": "characters/scene-002.json"}
{"type": "still", "src": "03.png"}
{"type": "text-card", "text": "VM vs CT"}
```

Esquema completo en [`schemas/project.schema.json`](schemas/project.schema.json),
ejemplo real (vídeo de homelab) en
[`schemas/project.example.json`](schemas/project.example.json).

El matching de metraje (`footage`) es **confirmado por ti**, no automático:
el campo `confirmed` debe estar en `true` antes de montar la escena — el
agente no puede ver de verdad el contenido de un clip, así que propone
`in`/`out` y tú los confirmas o corriges.

### Flujo

```bash
python scripts/footage_inventory.py --dir output/homelab          # lista tus clips (duración/resolución) para hacer el matching
python scripts/render_diagram.py --spec output/homelab/diagrams/scene-003.json \
                                  --out output/homelab/diagrams/scene-003.mp4   # una vez por cada escena "diagram"
python scripts/project_status.py --dir output/homelab             # qué falta antes de montar
python scripts/assemble_project.py --dir output/homelab           # -> final_clean.mp4
python scripts/gen_subtitles.py --dir output/homelab              # -> subtitles.webm (lee segments.json o project.json, mismo formato)
python scripts/burn_subtitles.py --dir output/homelab             # -> final.mp4
```

### Escenas `diagram` (manim)

Cada `diagram` de `project.json` apunta a un spec JSON con nodos, conexiones
y el orden en que aparecen, renderizado por
[`scripts/render/diagram_scene.py`](scripts/render/diagram_scene.py) — un
único `manim.Scene` genérico que lee el spec en vez de tener una escena de
manim escrita a mano por diagrama. Todo el estilo (fondo, color de tinta y
acento, grosor de línea, radio de esquina, timing del pop-in) sale de
`brand.yaml`, no de constantes en el archivo:

```json
{
  "duration": 6.0,
  "nodes": [
    {"id": "laptop", "label": "Old Laptop", "icon": "2", "position": [-4.5, 1.2, 0]},
    {"id": "vps", "label": "VPS", "icon": "f", "position": [4.5, 1.2, 0]}
  ],
  "edges": [
    {"from": "laptop", "to": "vps", "label": "WireGuard", "style": "dashed", "direction": "forward"}
  ],
  "reveal": [
    {"at": 0.0, "show": ["laptop"]},
    {"at": 1.0, "show": ["vps"]},
    {"at": 1.5, "show": ["laptop->vps"]}
  ],
  "highlight": [{"at": 3.0, "id": "laptop->vps"}]
}
```

Reglas fijas, no configurables por diagrama (para que ninguno se salga del
estilo del canal):

- las conexiones siempre paran en el borde de la caja, nunca la atraviesan;
- siempre llevan al menos una punta de flecha (`direction`: `forward`
  por defecto, `both` para bidireccional, `none` solo para un enlace físico
  pasivo sin flujo de datos);
- las etiquetas de una conexión llevan un fondo opaco detrás, así nunca se
  ven superpuestas con la línea sea cual sea el ángulo;
- el campo `icon` de un nodo es opcional y usa un glifo del Nerd Font
  (`typography.diagram_family`) como pictograma simple, sin necesitar un
  SVG aparte.

`scripts/render_diagram.py` renderiza un spec a
`output/<proyecto>/diagrams/scene-NNN.mp4` (convención que
`assemble_project.py` y `project_status.py` esperan). `assemble_project.py`
decodifica ese clip y lo recorta/rellena a la duración que le tocó en el
timeline por narración, igual que hace con `footage`.

### Escenas `character` (stickman de transición)

Un recurso barato para el ritmo "primero lo general, luego entramos en
detalle": un stick figure simple y estático (sin rig, sin gestos) que
aparece brevemente antes de cortar a un diagrama — el mismo uso que le da
Ardens a su personaje. Dos poses fijas, sin más:

```json
{"pose": "overview", "duration": 3.0}
```

- `overview` — brazos abiertos, postura de "aquí está el sistema completo".
- `point-right` — un brazo extendido, para la transición justo antes de un
  diagrama a la derecha.

Esquema en [`schemas/character.schema.json`](schemas/character.schema.json).
`scripts/render_character.py` renderiza un spec a
`output/<proyecto>/characters/scene-NNN.mp4`, con el mismo tratamiento en
`assemble_project.py`/`project_status.py` que `diagram`. Estilo (color,
grosor de línea, timing del pop-in) sale de `brand.yaml`, igual que todo lo
demás.

## Estructura del proyecto

```
brand.yaml               # identidad de marca: canvas, paleta, tipografía, motion
schemas/
  project.schema.json     # esquema de project.json (footage/diagram/character/still/text-card)
  project.example.json    # ejemplo real (vídeo de homelab)
  diagram.schema.json     # esquema del spec de una escena "diagram" (nodos/edges/reveal/highlight)
  character.schema.json   # esquema del spec de una escena "character" (pose/duration)
prompts/
  master_prompt_es.txt   # prompt para pegar en tu agente (español)
  master_prompt_en.txt   # el mismo prompt en inglés
  image_style.txt        # estilo obligatorio stickman/MS Paint, aplicado a cada imagen
scripts/
  brand.py                 # carga brand.yaml una vez, expone canvas/paleta/tipografía/motion
  gen_image_gemini.py     # GRATIS por defecto: Gemini "Nano Banana" -> PNG
  gen_image.py             # DE PAGO: OpenRouter (seedream-4.5 por defecto) -> PNG
  tts_edge.py               # GRATIS por defecto: Microsoft Edge TTS -> MP3
  tts_gemini.py             # DE PAGO/cuota: Gemini TTS -> WAV
  gen_subtitles.py           # subtítulos palabra por palabra -> subtitles.webm (alfa) + .srt
  assemble_video.py           # imágenes con zoom + audio -> final_clean.mp4 (formato legacy, solo stills)
  burn_subtitles.py            # final_clean.mp4 + subtitles.webm -> final.mp4
  timing.py                     # reparto de tiempos compartido (imágenes, diagramas y subtítulos en sync)
  ffmpeg_pipe.py                 # FfmpegSink/FfmpegSource: escribir y leer frames de ffmpeg sin bloquearse
  footage_inventory.py            # ffprobe de footage/raw/ -> duración/resolución de cada clip
  project_status.py                # qué escenas de project.json están listas para montar
  assemble_project.py               # project.json (still/footage/diagram/character) -> final_clean.mp4
  render_diagram.py                  # spec de diagrama -> MP4, vía manim
  render_character.py                 # spec de personaje (pose) -> MP4, vía manim
  render/
    diagram_scene.py                  # manim.Scene genérico: construye el diagrama a partir del spec JSON
    character_scene.py                # manim.Scene genérico: stick figure estático a partir de una pose fija
output/                 # generado en cada ejecución (gitignored)
.env.example
requirements.txt
```

## Notas

- Los prompts de imagen deben ser muy específicos (encuadre, pose exacta,
  cada objeto con forma/color/posición, fondo, texto exacto entre comillas) —
  el master prompt ya exige este nivel de detalle. Prompts vagos de una frase
  producen composiciones ambiguas o con errores.
- El texto de los subtítulos se rasteriza con Pillow en vez de con los filtros
  `subtitles`/`drawtext` de ffmpeg, porque el ffmpeg de Homebrew viene compilado
  sin libass ni libfreetype. La animación y el compositing sí los hace ffmpeg.
- Los únicos modelos con salida de audio en OpenRouter
  (`openai/gpt-audio`/`gpt-audio-mini`) son conversacionales: probados con
  varias estrategias de prompt, siempre añaden muletillas antes de narrar
  ("Claro, aquí va la frase..."). Por eso la voz no pasa por OpenRouter.
- Si `assemble_video.py` falla, comprueba que el audio existe y que todas
  las imágenes `NN.png` referenciadas en `segments.json` están generadas.
