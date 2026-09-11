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
Daily Haiku Toast. San Diego date + morning hourly Open-Meteo → Ann’s weather drawer → one short three-line haiku in Ann’s locked Poetess voice → Grok Imagine still of toast with the haiku burned into the crust. Prefer a nice morning scrap over a counted 5-7-5. Heat ceiling 0–2; weather drawers stay 0–1 and never raise chili from temperature.

Each run picks one **weather drawer** (or `--mode`) and one **Imagine style** from a small catalog local to this package (not the `styles/` visualizer catalog). Style roulette and voice mode are separate. Default style is random among enabled; pass `--seed` to reproduce random picks, or `--style` / `--mode` to force one.

Locked voice seed: `scripts/haiku_toast/VOICE_SEED.md` (loaded as the writer system brief). Drawer modes: `verdant`, `soft_weather_soul`, `hybrid_burnoff`, `sun_ode`, `clear_mild`, `starlit_dawn`, `rain`. `--mode` also still accepts `tender` and `picnic_wink`.

Enabled now:
- `buttered` — rustic wooden board, melting butter on the toast (board default evolution). Keeper: `scripts/haiku_toast/examples/buttered.jpg`
- `toaster_popup` — slice rising from a stainless toaster; juice or tea in the background. Keeper: `scripts/haiku_toast/examples/toaster_popup.jpg`

Plate, avocado, and egg stay out of the enabled pool (plate still: `scripts/haiku_toast/examples/toast-plate.jpg`). The canned avocado PNG is an Imagine-fail fallback only, not a catalog style. Add a future style by appending a `ToastStyle(enabled=True)` in `scripts/haiku_toast/style_catalog.py` — no even/odd hacks.

Run from the repo root (with venv activated):
python -m scripts.haiku_toast
python -m scripts.haiku_toast --dry-run
python -m scripts.haiku_toast --style buttered
python -m scripts.haiku_toast --style toaster_popup
python -m scripts.haiku_toast --seed 17
python -m scripts.haiku_toast --mode verdant

- No `XAI_API_KEY`: prompt-only (writer seed + chosen style template, keeper sample haiku).
- With `XAI_API_KEY`: live xAI chat/completions write, then Imagine via the shared `scripts.poem_visualizer.imagine_client.ImagineClient`. Live Imagine requests **4** stills for the same prompt (`--imagine-n`, max 10), reads the burned letters (xAI vision; optional local `tesseract` if vision cannot run), and keeps the one that best matches the haiku. If Imagine fails (API/credits/error) or every candidate fails the check, the day's haiku still ships with the canned avocado still (`scripts/haiku_toast/assets/avocado-toast-4x3.png`) — no burn-in, no invented crust lettering. The report names the fallback and why.
- Weather: Open-Meteo (https://open-meteo.com/) **hourly at pull hour** + daily sunrise for coastal San Diego (`weather_code`, cloud, visibility, humidity, temperature, precipitation, `is_day`). Ann’s drawer tree maps sky + moisture + light — not the daily high. Chili is never raised by temperature. The toast report names the drawer, reason, and tell.
- Artifacts land in `toasts/` (`*_haiku.txt`, `*_toast.md`, and `*_toast.jpg` when a still passes, or `*_toast.png` on avocado fallback). The report records Imagine style, voice mode, weather drawer, how many candidates were scored, and which was kept (or that fallback was used). Generated images and `toasts/.last_drawer.json` (yesterday’s drawer/tell plus a rolling few mornings of tells/motifs) are gitignored. Recent history also rereads the last 2–3 days of `toasts/*_haiku.txt` (and sibling `*_toast.md` tells) so a missing gitignored state file cannot drop the ban. The writer skips recently used tells when the drawer has another option, retries once if a scrap double-dips the soft-nature body cluster (toes + clover, mist + pane + clover), and blocks sticky picnic/body nouns (brie, cheese wedge, checkered cloth, toes, clover) across that window. Generic coffee or light may stay.
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
