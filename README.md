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
Daily Haiku Toast. San Diego date + a thin weather seed → one short three-line haiku in Ann’s voice → Grok Imagine still of toast with the haiku burned into the crust. Prefer a nice morning scrap over a counted 5-7-5.

Each run picks one **enabled Imagine style** from a small catalog local to this package (not the `styles/` visualizer catalog). Default is random among enabled styles; pass `--seed` to reproduce a pick, or `--style` to force one.

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

- No `XAI_API_KEY`: prompt-only (writer seed + chosen style template, keeper sample haiku).
- With `XAI_API_KEY`: live xAI chat/completions write, then Imagine via the shared `scripts.poem_visualizer.imagine_client.ImagineClient`.
- Weather: Open-Meteo (https://open-meteo.com/) high/low °F + one condition word for downtown San Diego. Not a weather product.
- Artifacts land in `toasts/` (`*_haiku.txt`, `*_toast.md`, and `*_toast.jpg` when Imagine succeeds). The report records which style was chosen. Generated images are gitignored.
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
