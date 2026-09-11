"""
Voice modes for Morning Haiku Toast.

Separate from Imagine style roulette (buttered / toaster_popup / egg_plate).
Maps Ann's weather → drawer tree onto a locked mode + heat 0–1.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence

from .drawers import (
    DRAWERS,
    MODE_DRAWER,
    DrawerDecision,
    LastDrawer,
    attach_tell,
    choose_tell_filtered,
    recent_signature_nouns,
    select_drawer,
)
from .weather import WeatherSeed


@dataclass(frozen=True)
class VoiceMode:
    name: str
    display_name: str
    heat: str
    hint: str


# Weather drawers stay heat 0–1. tender / picnic_wink remain for --mode.
MODES: Sequence[VoiceMode] = (
    VoiceMode(
        name="verdant",
        display_name="Verdant gloom",
        heat="0–1",
        hint=DRAWERS["FOG"].hint,
    ),
    VoiceMode(
        name="soft_weather_soul",
        display_name="Soft weather-soul",
        heat="0–1",
        hint=DRAWERS["OVERCAST"].hint,
    ),
    VoiceMode(
        name="hybrid_burnoff",
        display_name="Hybrid burnoff",
        heat="0–1",
        hint=DRAWERS["HYBRID_BURNOFF"].hint,
    ),
    VoiceMode(
        name="sun_ode",
        display_name="Sun-ode",
        heat="0–1",
        hint=DRAWERS["CLEAR_HOT"].hint,
    ),
    VoiceMode(
        name="clear_mild",
        display_name="Clear mild",
        heat="0–1",
        hint=DRAWERS["CLEAR_MILD"].hint,
    ),
    VoiceMode(
        name="starlit_dawn",
        display_name="Starlit dawn",
        heat="0–1",
        hint=DRAWERS["STARLIT_DAWN"].hint,
    ),
    VoiceMode(
        name="rain",
        display_name="Rain's promise",
        heat="0–1",
        hint=DRAWERS["RAIN"].hint,
    ),
    VoiceMode(
        name="tender",
        display_name="Tender",
        heat="0–1",
        hint="Face on the next pillow, hands that stay, a small vow",
    ),
    VoiceMode(
        name="picnic_wink",
        display_name="Picnic wink",
        heat="0–1",
        hint="Brie, coffee, checkered cloth — one concrete pleasure, optional wink",
    ),
)

MODE_NAMES = [m.name for m in MODES]
_BY_NAME: Dict[str, VoiceMode] = {m.name: m for m in MODES}
_ALIASES = {
    "fog": "verdant",
    "marine_layer": "verdant",
    "verdant_gloom": "verdant",
    "overcast": "soft_weather_soul",
    "gloom": "soft_weather_soul",
    "clear_hot": "sun_ode",
    "sunode": "sun_ode",
    "rains_promise": "rain",
    "rain_promise": "rain",
    "hybrid": "hybrid_burnoff",
    "burnoff": "hybrid_burnoff",
    "starlit": "starlit_dawn",
    "mild": "clear_mild",
}


@dataclass
class ModePick:
    mode: VoiceMode
    reason: str
    selection: str  # cli | weather | fallback
    seed: Optional[int] = None
    drawer: Optional[str] = None
    drawer_display: Optional[str] = None
    tell: Optional[str] = None
    avoids: Sequence[str] = field(default_factory=tuple)
    yesterday_tell: Optional[str] = None
    yesterday_drawer: Optional[str] = None
    avoided_tells: Sequence[str] = field(default_factory=tuple)
    recent_nouns: Sequence[str] = field(default_factory=tuple)
    decision: Optional[DrawerDecision] = None


def _normalize(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def get_mode(name: str) -> Optional[VoiceMode]:
    key = _normalize(name)
    key = _ALIASES.get(key, key)
    if key in _BY_NAME:
        return _BY_NAME[key]
    for mode in MODES:
        if _normalize(mode.display_name) == key:
            return mode
    return None


def mode_for_drawer(drawer_name: str) -> VoiceMode:
    spec = DRAWERS[drawer_name]
    return _BY_NAME[spec.mode_name]


def _pick_from_decision(
    decision: DrawerDecision,
    *,
    selection: str,
    seed: Optional[int],
    yesterday_drawer: Optional[str],
    yesterday_tell: Optional[str],
    recent: Optional[Sequence[LastDrawer]],
    rng: random.Random,
) -> ModePick:
    attach_tell(
        decision,
        yesterday_drawer=yesterday_drawer,
        yesterday_tell=yesterday_tell,
        recent=recent,
        rng=rng,
    )
    mode = _BY_NAME[decision.spec.mode_name]
    # Drawer heat is always 0–1; never lift from temperature_2m.
    return ModePick(
        mode=mode,
        reason=decision.reason,
        selection=selection,
        seed=seed,
        drawer=decision.name,
        drawer_display=decision.display_name,
        tell=decision.tell,
        avoids=decision.spec.avoids,
        yesterday_tell=yesterday_tell,
        yesterday_drawer=yesterday_drawer,
        avoided_tells=decision.avoided_tells,
        recent_nouns=decision.recent_nouns,
        decision=decision,
    )


def choose_mode(
    weather: WeatherSeed,
    *,
    name: Optional[str] = None,
    hour: Optional[int] = None,  # kept for call-site compatibility; unused
    seed: Optional[int] = None,
    rng: Optional[random.Random] = None,
    allow_alternate: bool = True,  # unused; tree is one drawer, no alternate
    yesterday_drawer: Optional[str] = None,
    yesterday_tell: Optional[str] = None,
    recent: Optional[Sequence[LastDrawer]] = None,
) -> ModePick:
    """
    Pick a voice mode.

    --mode name  → that mode (tells from its drawer if it has one)
    otherwise    → Ann's weather drawer tree (first match wins)
    """
    del hour, allow_alternate  # weather tree replaced the old pool / alternate
    if rng is not None:
        chooser = rng
    elif seed is not None:
        chooser = random.Random(seed)
    else:
        chooser = random.Random()

    if name:
        found = get_mode(name)
        if found is None:
            known = ", ".join(MODE_NAMES)
            raise ValueError(f"Unknown voice mode {name!r}. Known: {known}")
        drawer_name = MODE_DRAWER.get(found.name)
        tell = None
        avoids: Sequence[str] = ()
        drawer_display = None
        avoided: Sequence[str] = ()
        nouns: Sequence[str] = recent_signature_nouns(recent or ())
        if drawer_name:
            spec = DRAWERS[drawer_name]
            tell, skipped = choose_tell_filtered(
                spec,
                yesterday_drawer=yesterday_drawer,
                yesterday_tell=yesterday_tell,
                recent=recent,
                rng=chooser,
            )
            avoids = spec.avoids
            drawer_display = spec.display_name
            avoided = skipped
        return ModePick(
            mode=found,
            reason=f"`--mode {found.name}`",
            selection="cli",
            seed=None,
            drawer=drawer_name,
            drawer_display=drawer_display,
            tell=tell,
            avoids=avoids,
            yesterday_tell=yesterday_tell,
            yesterday_drawer=yesterday_drawer,
            avoided_tells=avoided,
            recent_nouns=nouns,
        )

    if not weather.ok:
        decision = select_drawer(weather)
        return _pick_from_decision(
            decision,
            selection="fallback",
            seed=seed,
            yesterday_drawer=yesterday_drawer,
            yesterday_tell=yesterday_tell,
            recent=recent,
            rng=chooser,
        )

    decision = select_drawer(weather)
    return _pick_from_decision(
        decision,
        selection="weather",
        seed=seed,
        yesterday_drawer=yesterday_drawer,
        yesterday_tell=yesterday_tell,
        recent=recent,
        rng=chooser,
    )
