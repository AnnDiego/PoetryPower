"""
Voice modes for Morning Haiku Toast.

Separate from Imagine style roulette (buttered / toaster_popup).
Maps the thin Open-Meteo seed onto one of five locked modes.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .weather import WeatherSeed

# Cool San Diego morning: low at or under this prefers starlit_dawn early.
COOL_LOW_MAX_F = 60
# Chance, after the weather primary, to slip in tender or picnic_wink
# so love/breakfast days still happen.
ALTERNATE_P = 0.18
EARLY_HOUR = 8


@dataclass(frozen=True)
class VoiceMode:
    name: str
    display_name: str
    heat: str
    hint: str


MODES: Sequence[VoiceMode] = (
    VoiceMode(
        name="verdant",
        display_name="Verdant",
        heat="0–1",
        hint="Mist, May gray / June gloom, peat, clover, sun creeping toes → heart",
    ),
    VoiceMode(
        name="starlit_dawn",
        display_name="Starlit dawn",
        heat="0–1",
        hint="Moon surrendering to sun; Venus still up; wet grass; last stars",
    ),
    VoiceMode(
        name="tender",
        display_name="Tender",
        heat="1",
        hint="Face on the next pillow, hands that stay, a small vow",
    ),
    VoiceMode(
        name="picnic_wink",
        display_name="Picnic wink",
        heat="0–1",
        hint="Brie, coffee, checkered cloth — one concrete pleasure, optional wink",
    ),
    VoiceMode(
        name="soft_weather_soul",
        display_name="Soft weather soul",
        heat="0–1",
        hint="Rain’s promise, wind chimes, “I’ll bring you rain,” green enduring",
    ),
)

MODE_NAMES = [m.name for m in MODES]
_BY_NAME: Dict[str, VoiceMode] = {m.name: m for m in MODES}
ALTERNATES = ("tender", "picnic_wink")

_GRAY_MIST = (
    "fog",
    "mist",
    "overcast",
    "cloud",
    "gray",
    "drizzle",
    "rime",
)
_RAIN = ("rain", "shower", "thunder", "snow")
_CLEAR = ("clear", "sunny", "fair")
_WINDY = ("wind",)


@dataclass
class ModePick:
    mode: VoiceMode
    reason: str
    selection: str  # cli | weather | random
    seed: Optional[int] = None


def _normalize(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def get_mode(name: str) -> Optional[VoiceMode]:
    key = _normalize(name)
    if key in _BY_NAME:
        return _BY_NAME[key]
    for mode in MODES:
        if _normalize(mode.display_name) == key:
            return mode
    return None


def _condition_blob(weather: WeatherSeed) -> str:
    return (weather.condition or "unknown").strip().lower().replace("_", "-")


def primary_pool(
    weather: WeatherSeed,
    *,
    hour: Optional[int] = None,
) -> Tuple[List[str], Dict[str, float], str]:
    """
    Return (names, weights, reason) for the weather-primary pool.

    Weights are used when a pool has a preferred member (cool-clear early
    hours weight starlit_dawn). Equal weights otherwise.
    """
    if not weather.ok:
        names = list(MODE_NAMES)
        weights = {n: 1.0 for n in names}
        return names, weights, "weather unavailable — random among all five modes"

    cond = _condition_blob(weather)
    low = weather.low_f
    high = weather.high_f

    if any(token in cond for token in _RAIN):
        names = ["soft_weather_soul"]
        return names, {n: 1.0 for n in names}, f"{cond} → soft_weather_soul"

    if any(token in cond for token in _GRAY_MIST):
        names = ["verdant", "soft_weather_soul"]
        return (
            names,
            {n: 1.0 for n in names},
            f"{cond} → verdant or soft_weather_soul",
        )

    if any(token in cond for token in _CLEAR):
        cool = low is not None and low <= COOL_LOW_MAX_F
        warm = low is not None and high is not None and low > COOL_LOW_MAX_F
        if cool:
            early = hour is not None and hour < EARLY_HOUR
            if early:
                names = ["starlit_dawn", "verdant"]
                weights = {"starlit_dawn": 0.7, "verdant": 0.3}
                reason = (
                    f"{cond}, cool morning (low {low}°F), hour {hour} "
                    f"< {EARLY_HOUR} — starlit_dawn weighted, else verdant"
                )
            else:
                names = ["verdant", "starlit_dawn"]
                weights = {"verdant": 0.7, "starlit_dawn": 0.3}
                hour_bit = f"hour {hour}" if hour is not None else "hour unknown"
                reason = (
                    f"{cond}, cool morning (low {low}°F), {hour_bit} — "
                    "verdant preferred, starlit_dawn still possible"
                )
            return names, weights, reason
        if warm:
            names = ["verdant", "picnic_wink"]
            return (
                names,
                {n: 1.0 for n in names},
                f"{cond}, warm (low {low}°F / high {high}°F) → verdant or picnic_wink",
            )
        names = ["verdant", "starlit_dawn"]
        return names, {n: 1.0 for n in names}, f"{cond} → verdant or starlit_dawn"

    if any(token in cond for token in _WINDY):
        names = ["soft_weather_soul", "verdant"]
        return (
            names,
            {n: 1.0 for n in names},
            f"{cond} → soft_weather_soul or verdant",
        )

    names = list(MODE_NAMES)
    return (
        names,
        {n: 1.0 for n in names},
        f"{cond} unmatched — random among all five modes",
    )


def _weighted_pick(weights: Dict[str, float], rng: random.Random) -> str:
    names = list(weights)
    vals = [weights[n] for n in names]
    return rng.choices(names, weights=vals, k=1)[0]


def choose_mode(
    weather: WeatherSeed,
    *,
    name: Optional[str] = None,
    hour: Optional[int] = None,
    seed: Optional[int] = None,
    rng: Optional[random.Random] = None,
    allow_alternate: bool = True,
) -> ModePick:
    """
    Pick a voice mode.

    --mode name  → that mode
    otherwise    → weather map, then a low-weight tender/picnic_wink alternate
    """
    if name:
        found = get_mode(name)
        if found is None:
            known = ", ".join(MODE_NAMES)
            raise ValueError(f"Unknown voice mode {name!r}. Known: {known}")
        return ModePick(
            mode=found,
            reason=f"`--mode {found.name}`",
            selection="cli",
            seed=None,
        )

    if rng is not None:
        chooser = rng
    elif seed is not None:
        chooser = random.Random(seed)
    else:
        chooser = random.Random()

    names, weights, reason = primary_pool(weather, hour=hour)
    picked = _weighted_pick(weights, chooser)
    selection = "random" if not weather.ok else "weather"

    if allow_alternate and chooser.random() < ALTERNATE_P:
        alt = chooser.choice(list(ALTERNATES))
        if alt != picked:
            reason = f"{reason}; low-weight love/breakfast alternate → {alt}"
            picked = alt

    mode = _BY_NAME[picked]
    return ModePick(mode=mode, reason=reason, selection=selection, seed=seed)
