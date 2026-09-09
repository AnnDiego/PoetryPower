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
Daily Haiku Toast MVP. San Diego date + a thin weather seed → one English 5-7-5 in Ann’s voice → Grok Imagine still of toast with the haiku burned into the crust (board default).

Run from the repo root (with venv activated):
python -m scripts.haiku_toast
python -m scripts.haiku_toast --dry-run

- No `XAI_API_KEY`: prompt-only (writer seed + locked Imagine template, keeper sample haiku).
- With `XAI_API_KEY`: live xAI chat/completions write, then Imagine via the shared `scripts.poem_visualizer.imagine_client.ImagineClient`.
- Weather: Open-Meteo (https://open-meteo.com/) high/low °F + one condition word for downtown San Diego. Not a weather product.
- Artifacts land in `toasts/` (`*_haiku.txt`, `*_toast.md`, and `*_toast.jpg` when Imagine succeeds). Generated images are gitignored.
- Board style is v1. Plate-with-coffee is a later A/B only (`scripts/haiku_toast/examples/`).
- Site posting, daily auto-X, Notion, and a physical toaster are follow-ups — not in this runner.

Locked Imagine template (replace `{HAIKU}` only) lives in `scripts/haiku_toast/prompts.py`.

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
