"""
Ann's approved writer brief + shared Imagine constants.

Imagine templates live in style_catalog.py (local toast catalog).
Do not pull styles from poem_visualizer.
"""

from __future__ import annotations

from .style_catalog import fill_imagine_prompt

# Re-export so existing imports keep working.
__all__ = [
    "VOICE_BRIEF",
    "KEEPER_SAMPLE_HAIKU",
    "WEATHER_SOURCE",
    "WEATHER_SOURCE_URL",
    "SAN_DIEGO_LAT",
    "SAN_DIEGO_LON",
    "SAN_DIEGO_TZ",
    "IMAGINE_ASPECT_RATIO",
    "FUTURE_STYLES_NOTE",
    "fill_imagine_prompt",
    "writer_user_prompt",
]

# Ann-approved voice brief (embed in the chat writer as-is).
VOICE_BRIEF = """\
Write her morning scrap burned into toast — not museum haiku, not coffee-shop wallpaper. Tone: sassy-tender. Concrete. One clear image + a small turn. San Diego body: marine layer, canyon heat, harbor light, Padres nights, picnic leftovers, Starship sky, ramen steam, tech residual in the crumbs. Weather seeds today’s freshness, not a forecast lecture. Do: short three lines, sensory, present tense or clean snapshot. Don’t: Hallmark zen, cherry-blossom tourism, forced broken English for syllables, merch pitch, self-help, tourist San Diego explainers, captions/watermarks.
"""

# Keeper sample used on the dry / no-key path so the Imagine
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

# Documented only — not in the enabled catalog.
FUTURE_STYLES_NOTE = (
    "Plate-with-coffee, avocado, and egg are future looks, not in the "
    "enabled pool. See scripts/haiku_toast/examples/."
)


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
        "Write one short English three-line haiku for this morning — "
        "a morning scrap, not a counted 5-7-5. "
        "Output ONLY the three lines. No title, no quotes, no commentary."
    )
