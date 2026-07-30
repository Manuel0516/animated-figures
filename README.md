# Vídeos Stickman Faceless — sin Magnific, con cualquier agente de código

Adaptación del sistema ["Vídeos Stickman Faceless con Claude 2026"](https://ale-ferr.notion.site/V-deos-Stickman-Faceless-con-Claude-2026-39a43d6a4e9780839821c3bdc49d1b92).

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
brew install ffmpeg   # si no lo tienes ya
cp .env.example .env
# edita .env y añade:
#   GEMINI_API_KEY      -> https://aistudio.google.com/apikey (imágenes gratis + voz)
#   OPENROUTER_API_KEY  -> https://openrouter.ai/keys (solo si quieres el camino de pago)
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

## Estructura del proyecto

```
prompts/
  master_prompt_es.txt   # prompt para pegar en tu agente (español)
  master_prompt_en.txt   # el mismo prompt en inglés
  image_style.txt        # estilo obligatorio stickman/MS Paint, aplicado a cada imagen
scripts/
  gen_image_gemini.py     # GRATIS por defecto: Gemini "Nano Banana" -> PNG
  gen_image.py             # DE PAGO: OpenRouter (seedream-4.5 por defecto) -> PNG
  tts_edge.py               # GRATIS por defecto: Microsoft Edge TTS -> MP3
  tts_gemini.py             # DE PAGO/cuota: Gemini TTS -> WAV
  gen_subtitles.py           # subtítulos palabra por palabra -> subtitles.webm (alfa) + .srt
  assemble_video.py           # imágenes con zoom + audio -> final_clean.mp4
  burn_subtitles.py            # final_clean.mp4 + subtitles.webm -> final.mp4
  timing.py                     # reparto de tiempos compartido (imágenes y subtítulos en sync)
  ffmpeg_pipe.py                 # helper para escribir frames a ffmpeg sin bloquearse
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
