"""
Ann's locked voice seed + shared Imagine constants.

Imagine templates live in style_catalog.py (local toast catalog).
Voice modes live in voice_modes.py. Do not pull styles from poem_visualizer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .style_catalog import fill_imagine_prompt

# Re-export so existing imports keep working.
__all__ = [
    "VOICE_BRIEF",
    "VOICE_SEED_PATH",
    "KEEPER_SAMPLE_HAIKU",
    "WEATHER_SOURCE",
    "WEATHER_SOURCE_URL",
    "SAN_DIEGO_LAT",
    "SAN_DIEGO_LON",
    "SAN_DIEGO_TZ",
    "IMAGINE_ASPECT_RATIO",
    "FUTURE_STYLES_NOTE",
    "fill_imagine_prompt",
    "load_voice_brief",
    "writer_user_prompt",
]

VOICE_SEED_PATH = Path(__file__).with_name("VOICE_SEED.md")


def load_voice_brief(path: Optional[Path] = None) -> str:
    """Locked Poetess Ann voice seed — writer system brief."""
    return (path or VOICE_SEED_PATH).read_text(encoding="utf-8").strip()


# Loaded from VOICE_SEED.md so Ann can re-read the same text in-repo.
VOICE_BRIEF = load_voice_brief()

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
    "Plate-with-coffee and avocado are future looks, not in the "
    "enabled pool. See scripts/haiku_toast/examples/."
)


def writer_user_prompt(
    *,
    date_line: str,
    weekday_vibe: str,
    weather_seed: str,
    mode_name: str = "",
    mode_heat: str = "",
    mode_hint: str = "",
    drawer_name: str = "",
    drawer_reason: str = "",
    chosen_tell: str = "",
    avoids: str = "",
    yesterday_tell: str = "",
    drawer_changed: bool = False,
    recent_nouns: str = "",
    nature_only: bool = False,
) -> str:
    """Today's seed for the chat writer. Voice lives in the system brief."""
    lines = [
        "Today in San Diego:",
        f"- Date: {date_line}",
        f"- Weekday vibe: {weekday_vibe}",
        f"- Weather seed: {weather_seed}",
    ]
    if drawer_name:
        lines.append(f"- Weather drawer: {drawer_name}")
        if drawer_reason:
            lines.append(f"- Drawer reason: {drawer_reason}")
    if mode_name:
        heat = f" (heat {mode_heat})" if mode_heat else ""
        lines.append(f"- Voice mode for this run: {mode_name}{heat}")
        if mode_hint:
            lines.append(f"- Mode cue: {mode_hint}")
    if chosen_tell:
        lines.append(
            f"- Required tell (include this image or its key words): {chosen_tell}"
        )
    if avoids:
        lines.append(f"- Avoid: {avoids}")
    if yesterday_tell and drawer_changed:
        lines.append(f"- Do not reuse yesterday's tell: {yesterday_tell}")
    if recent_nouns:
        lines.append(
            f"- Do not repeat recent mornings' signature nouns: {recent_nouns}. "
            "Sticky picnic/body tells (brie, cheese wedge, checkered cloth, "
            "toes, clover) stay banned across this window; generic coffee "
            "or light may stay."
        )
    lines += [
        "",
        "Write in the named voice mode only. Stay at that mode's heat "
        "(ceiling is 0–2; weather drawers stay 0–1). "
        "Never raise chili because the air is warm — no embers, nape-yield, "
        "or fade-to-black. temperature_2m does not raise heat.",
        "Include the one required tell — do not invent a second drawer tell. "
        "Do not describe the toast. "
        "Do not write a generic soulmate dawn or moonbeams with no "
        "San Diego tell.",
        "Do not double-dip the soft-nature body lexicon in one scrap "
        "(toes + clover; mist + pane + clover). ",
    ]
    if nature_only:
        lines.append(
            "This drawer may stay nature-forward, but still only one "
            "earth-body tell — no clover-mist-pane pile-on."
        )
    else:
        lines.append(
            "Prefer one weather/nature tell + one other voltage "
            "(human, picnic, or light)."
        )
    lines += [
        "Reject and rewrite if you used fog lexicon on a clear/hot sky, "
        "or gray-on-the-pane on a heat-warning morning.",
        "Write one short English three-line haiku for this morning — "
        "a morning scrap. 5-7-5 or honest close is OK; do not pad; "
        "do not regenerate for syllable counts. "
        "Output ONLY the three lines. No title, no quotes, no commentary.",
    ]
    return "\n".join(lines)
