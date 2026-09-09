"""
Locked Imagine template + Ann's approved writer brief.

Do not redesign. The Imagine template replaces {HAIKU} only.
Board-on-wood is the v1 default. Plate-with-coffee is a later A/B
(see examples/README.md) and is not wired into the runner.
"""

from __future__ import annotations

# Ann-approved voice brief (embed in the chat writer as-is).
VOICE_BRIEF = """\
Write her morning scrap burned into toast — not museum haiku, not coffee-shop wallpaper. Tone: sassy-tender. Concrete. One clear image + a small turn. San Diego body: marine layer, canyon heat, harbor light, Padres nights, picnic leftovers, Starship sky, ramen steam, tech residual in the crumbs. Weather seeds today’s freshness, not a forecast lecture. Do: short three lines, sensory, present tense or clean snapshot. Don’t: Hallmark zen, cherry-blossom tourism, forced broken English for syllables, merch pitch, self-help, tourist San Diego explainers, captions/watermarks.
"""

# Locked Grok Imagine prompt. Replace {HAIKU} only.
IMAGINE_TEMPLATE = """\
Photorealistic close-up of a single slice of freshly toasted artisan bread on a rustic wooden board, warm morning sidelight, faint steam. A three-line haiku is burned into the golden crust in darker toasted-brown letters, clearly readable, following the crumb texture:

{HAIKU}

Letters look like selective Maillard browning, not printed ink. Small melting butter at one corner. Shallow depth of field, food-photography realism, no extra captions, no watermark.
"""

# Board-keeper sample used on the dry / no-key path so the Imagine
# prompt is complete and reviewable. Not a live write.
KEEPER_SAMPLE_HAIKU = (
    "Crisp slice, quiet dawn\n"
    "ink of heat writes seventeen\n"
    "syllables of gold"
)

# Open-Meteo, downtown San Diego. Documented in weather.py + reports.
WEATHER_SOURCE = "Open-Meteo"
WEATHER_SOURCE_URL = "https://open-meteo.com/"
SAN_DIEGO_LAT = 32.7157
SAN_DIEGO_LON = -117.1611
SAN_DIEGO_TZ = "America/Los_Angeles"

# Food-photography still (not the visualizer's 9:16 vertical).
IMAGINE_ASPECT_RATIO = "4:3"

# Later A/B only — not used by the v1 runner.
PLATE_COFFEE_NOTE = (
    "Plate-with-coffee is a later A/B alternative, not the v1 default. "
    "See scripts/haiku_toast/examples/toast-plate.jpg."
)


def fill_imagine_prompt(haiku: str) -> str:
    """Substitute {HAIKU} only. Leave the rest of the locked template intact."""
    return IMAGINE_TEMPLATE.replace("{HAIKU}", haiku.strip())


def writer_user_prompt(
    *,
    date_line: str,
    weekday_vibe: str,
    weather_seed: str,
) -> str:
    """Today's seed for the chat writer. Voice lives in the system brief."""
    return (
        f"Today in San Diego:\n"
        f"- Date: {date_line}\n"
        f"- Weekday vibe: {weekday_vibe}\n"
        f"- Weather seed: {weather_seed}\n"
        "\n"
        "Write one English 5-7-5 haiku for this morning. "
        "Output ONLY the three lines. No title, no quotes, no commentary."
    )


def rewrite_user_prompt(previous: str, counts_label: str) -> str:
    """One-shot regenerate when the syllable heuristic is way off."""
    return (
        f"Your last haiku was not close to English 5-7-5 "
        f"(heuristic counted {counts_label}):\n\n"
        f"{previous}\n\n"
        "Rewrite once as English 5-7-5. Output ONLY the three lines."
    )
