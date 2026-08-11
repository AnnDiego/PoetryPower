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

## Setup
python -m venv .venv
source .venv/bin/activate
pip install -r scripts/poem_visualizer/requirements.txt

Copy scripts/poem_visualizer/.env.example to .env and add your XAI_API_KEY.
