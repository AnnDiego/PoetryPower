# PoetryPower

Tools and automations for my poetry practice.

## Current Tools

### poem_visualizer
Turns a poem into a styled image + optional short vertical (9:16) video using Grok Imagine.

Features:
- Style matching with override
- Special direction support
- Optional video generation
- Iteration loop for the same poem

Run from the repo root (with venv activated):
python -m scripts.poem_visualizer.visualizer

### haiku_toast
Daily Haiku Toast. San Diego date + a thin weather seed → one short three-line haiku in Ann’s locked Poetess voice → Grok Imagine still of toast with the haiku burned into the crust. Prefer a nice morning scrap over a counted 5-7-5. Heat ceiling 0–2.

Each run picks one **voice mode** from the weather seed (or `--mode`) and one **Imagine style** from a small catalog local to this package (not the `styles/` visualizer catalog). Style roulette and voice mode are separate. Default style is random among enabled; pass `--seed` to reproduce random picks, or `--style` / `--mode` to force one.

Locked voice seed: `scripts/haiku_toast/VOICE_SEED.md` (loaded as the writer system brief). Modes: `verdant`, `starlit_dawn`, `tender`, `picnic_wink`, `soft_weather_soul`.

Enabled now:
- `buttered` — rustic wooden board, melting butter on the toast (board default evolution). Keeper: `scripts/haiku_toast/examples/buttered.jpg`
- `toaster_popup` — slice rising from a stainless toaster; juice or tea in the background. Keeper: `scripts/haiku_toast/examples/toaster_popup.jpg`

Plate, avocado, and egg stay out of the enabled pool (plate still: `scripts/haiku_toast/examples/toast-plate.jpg`). Add a future style by appending a `ToastStyle(enabled=True)` in `scripts/haiku_toast/style_catalog.py` — no even/odd hacks.

Run from the repo root (with venv activated):
python -m scripts.haiku_toast
python -m scripts.haiku_toast --dry-run
python -m scripts.haiku_toast --style buttered
python -m scripts.haiku_toast --style toaster_popup
python -m scripts.haiku_toast --seed 17
python -m scripts.haiku_toast --mode verdant

- No `XAI_API_KEY`: prompt-only (writer seed + chosen style template, keeper sample haiku).
- With `XAI_API_KEY`: live xAI chat/completions write, then Imagine via the shared `scripts.poem_visualizer.imagine_client.ImagineClient`. Live Imagine requests **4** stills for the same prompt (`--imagine-n`, max 10), reads the burned letters (xAI vision; optional local `tesseract` if vision cannot run), and keeps the one that best matches the haiku. If every candidate fails the check, the report says so and no `*_toast.jpg` is shipped.
- Weather: Open-Meteo (https://open-meteo.com/) high/low °F + one condition word for downtown San Diego. Not a weather product.
- Artifacts land in `toasts/` (`*_haiku.txt`, `*_toast.md`, and `*_toast.jpg` when a still passes). The report records Imagine style, voice mode, how many candidates were scored, and which was kept (or that all failed). Generated images are gitignored.
- Site posting, daily auto-X, Notion, and a physical toaster are follow-ups — not in this runner.

Imagine templates (replace `{HAIKU}` only) live in `scripts/haiku_toast/style_catalog.py`. Both enabled templates require exactly three lines and letters that follow the crumb as Maillard browning, not printed ink.

### Other tools
- poem_analyzer.py – Poem feedback / analysis
- poem_madlib.py – Turn a poem into a Mad-Lib
- poem_fortune.py – Cosmic poem fortune cookie

## Styles
The styles/ directory contains the living style catalog used by the visualizer:

- Charcoal Sketch
- Romantic Anime
- Moody Comic
- Artistic Collage
- Anime Cyberpunk
- Thick Impasto

## Setup
python -m venv .venv
source .venv/bin/activate
pip install -r scripts/poem_visualizer/requirements.txt

Copy scripts/poem_visualizer/.env.example to .env and add your XAI_API_KEY.
The same key is used by poem_visualizer (Imagine) and haiku_toast (chat + Imagine).
