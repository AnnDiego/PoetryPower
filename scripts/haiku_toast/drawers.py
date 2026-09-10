"""
Ann's weather → drawer decision tree.

First match wins. Uses morning hourly fields (sky + moisture + light).
temperature_2m may pick CLEAR HOT / HYBRID BURNOFF. It never raises chili.
"""

from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .prompts import SAN_DIEGO_LAT, SAN_DIEGO_LON
from .weather import WeatherSeed

DRAWER_RAIN = "RAIN"
DRAWER_FOG = "FOG"
DRAWER_OVERCAST = "OVERCAST"
DRAWER_HYBRID = "HYBRID_BURNOFF"
DRAWER_CLEAR_HOT = "CLEAR_HOT"
DRAWER_STARLIT = "STARLIT_DAWN"
DRAWER_CLEAR_MILD = "CLEAR_MILD"

RAIN_CODES = frozenset(range(51, 68)) | frozenset(range(80, 83)) | frozenset(
    range(95, 100)
)
FOG_CODES = frozenset({45, 48})
CLEARISH_CODES = frozenset({0, 1})
PARTLY_CODES = frozenset({0, 1, 2})

DAWN_WINDOW_MIN = 40
FOG_VIS_M = 2000
FOG_RH = 85
OVERCAST_CLOUD = 85
HYBRID_CLOUD_LO = 40
HYBRID_CLOUD_HI = 84
HYBRID_TEMP_F = 72
CLEAR_HOT_TEMP_F = 75

STATE_FILENAME = ".last_drawer.json"

_STOP = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "and",
        "to",
        "that",
        "will",
        "on",
        "in",
        "as",
        "my",
        "you",
        "i",
        "ll",
        "then",
        "still",
    }
)


@dataclass(frozen=True)
class DrawerSpec:
    name: str
    display_name: str
    mode_name: str
    heat: str
    hint: str
    tells: Tuple[str, ...]
    avoids: Tuple[str, ...]


DRAWERS: Dict[str, DrawerSpec] = {
    DRAWER_FOG: DrawerSpec(
        name=DRAWER_FOG,
        display_name="FOG / MARINE LAYER",
        mode_name="verdant",
        heat="0–1",
        hint=(
            "Verdant gloom. Mist, pane, clover, peat, chimes still, "
            "shirt-to-skin chill, gray concede, white shroud."
        ),
        tells=(
            "mist",
            "pane",
            "clover",
            "peat",
            "chimes still",
            "shirt-to-skin chill",
            "gray concede",
            "white shroud",
        ),
        avoids=("blazing photons", "Palm Springs", "fierce sun"),
    ),
    DRAWER_OVERCAST: DrawerSpec(
        name=DRAWER_OVERCAST,
        display_name="OVERCAST / GLOOM",
        mode_name="soft_weather_soul",
        heat="0–1",
        hint=(
            "Soft weather-soul. May gray, June gloom, ashen stone, "
            "luminous pearl, buttery gold teased then swallowed, "
            "green cutting haze."
        ),
        tells=(
            "May gray",
            "June gloom",
            "ashen stone",
            "luminous pearl",
            "buttery gold teased then swallowed",
            "green cutting haze",
        ),
        avoids=("mist-on-clover if visibility is fine",),
    ),
    DRAWER_HYBRID: DrawerSpec(
        name=DRAWER_HYBRID,
        display_name="HYBRID BURNOFF",
        mode_name="hybrid_burnoff",
        heat="0–1",
        hint=(
            "Gray first line, sun last line. Classic coastal SD burnoff: "
            "pane still gray / sun finds the toes; clouds sashay; "
            "promise that the day will burn through."
        ),
        tells=(
            "pane still gray / sun finds the toes",
            "clouds sashay",
            "promise that the day will burn through",
        ),
        avoids=("all-day gloom with no sun", "fierce noon blaze in line one"),
    ),
    DRAWER_CLEAR_HOT: DrawerSpec(
        name=DRAWER_CLEAR_HOT,
        display_name="CLEAR HOT",
        mode_name="sun_ode",
        heat="0–1",
        hint=(
            "Sun-ode. Photons on forehead, surge of energy, heat coaxing, "
            "fierce embrace, clothes considering the shed; pool-sapphire "
            "only if you must; buttery gold that wins."
        ),
        tells=(
            "photons on forehead",
            "surge of energy",
            "heat coaxing",
            "fierce embrace",
            "clothes considering the shed",
            "buttery gold that wins",
        ),
        avoids=(
            "gray on the pane",
            "mist",
            "clover-as-weather",
            "embers / nape / yield",
        ),
    ),
    DRAWER_CLEAR_MILD: DrawerSpec(
        name=DRAWER_CLEAR_MILD,
        display_name="CLEAR MILD",
        mode_name="clear_mild",
        heat="0–1",
        hint=(
            "Tender + picnic wink. First ray, pillow-shield, coffee steam, "
            "checkered cloth, brie, wet lawn, palm-frond shadow."
        ),
        tells=(
            "first ray",
            "pillow-shield",
            "coffee steam",
            "checkered cloth",
            "brie",
            "wet lawn",
            "palm-frond shadow",
        ),
        avoids=("fierce sun", "mist-as-weather", "generic soulmate dawn"),
    ),
    DRAWER_STARLIT: DrawerSpec(
        name=DRAWER_STARLIT,
        display_name="STARLIT DAWN",
        mode_name="starlit_dawn",
        heat="0–1",
        hint=(
            "Starlit-dawn. Milk-saucer moon, crescent as glove, Venus, "
            "last stars, wet grass, moon bowing to the breaking sun. "
            "Only pre-/just-sunrise and sky clear enough."
        ),
        tells=(
            "milk-saucer moon",
            "crescent as glove",
            "Venus",
            "last stars",
            "wet grass",
            "moon bowing to the breaking sun",
        ),
        avoids=("generic moonbeams", "soulmate dawn"),
    ),
    DRAWER_RAIN: DrawerSpec(
        name=DRAWER_RAIN,
        display_name="RAIN",
        mode_name="rain",
        heat="0–1",
        hint=(
            "Rain's promise. Chime encore, I'll bring you rain, "
            "drum on the roof, tongue tasting sky, green enduring."
        ),
        tells=(
            "chime encore",
            "I'll bring you rain",
            "drum on the roof",
            "tongue tasting sky",
            "green enduring",
        ),
        avoids=("blazing photons", "fierce sun", "Palm Springs"),
    ),
}

# --mode names that still carry a drawer (tells / avoids).
MODE_DRAWER: Dict[str, str] = {
    spec.mode_name: spec.name for spec in DRAWERS.values()
}
MODE_DRAWER.update(
    {
        "tender": DRAWER_CLEAR_MILD,
        "picnic_wink": DRAWER_CLEAR_MILD,
    }
)


@dataclass
class DrawerDecision:
    spec: DrawerSpec
    reason: str
    tell: str = ""
    yesterday_tell: Optional[str] = None
    yesterday_drawer: Optional[str] = None

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def display_name(self) -> str:
        return self.spec.display_name


@dataclass
class LastDrawer:
    date: str
    drawer: str
    tell: str


def last_drawer_path(out_dir: Path) -> Path:
    return Path(out_dir) / STATE_FILENAME


def load_last_drawer(out_dir: Path) -> Optional[LastDrawer]:
    path = last_drawer_path(out_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    date = data.get("date")
    drawer = data.get("drawer")
    tell = data.get("tell")
    if not date or not drawer or not tell:
        return None
    return LastDrawer(date=str(date), drawer=str(drawer), tell=str(tell))


def save_last_drawer(
    out_dir: Path,
    *,
    date: str,
    drawer: str,
    tell: str,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = last_drawer_path(out_dir)
    path.write_text(
        json.dumps(
            {"date": date, "drawer": drawer, "tell": tell},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def yesterday_note(
    last: Optional[LastDrawer],
    today: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Return (drawer, tell) only when the note is from a previous day."""
    if last is None or last.date >= today:
        return None, None
    return last.drawer, last.tell


def _code(weather: WeatherSeed) -> Optional[int]:
    if weather.weather_code is None:
        return None
    try:
        return int(weather.weather_code)
    except (TypeError, ValueError):
        return None


def _cloud(weather: WeatherSeed) -> Optional[float]:
    if weather.cloud_cover is not None:
        return weather.cloud_cover
    return weather.cloud_cover_low


def minutes_from_sunrise(weather: WeatherSeed) -> Optional[float]:
    if weather.sunrise is None or weather.pull_at is None:
        return None
    sunrise = weather.sunrise
    pull = weather.pull_at
    if sunrise.tzinfo is None and pull.tzinfo is not None:
        sunrise = sunrise.replace(tzinfo=pull.tzinfo)
    elif pull.tzinfo is None and sunrise.tzinfo is not None:
        pull = pull.replace(tzinfo=sunrise.tzinfo)
    return (pull - sunrise).total_seconds() / 60.0


def still_dark(weather: WeatherSeed) -> bool:
    return weather.is_day == 0


def in_dawn_window(weather: WeatherSeed) -> bool:
    """Still dark, or within 40 minutes of sunrise."""
    if still_dark(weather):
        return True
    delta = minutes_from_sunrise(weather)
    if delta is None:
        return False
    return abs(delta) <= DAWN_WINDOW_MIN


def _julian_date(utc: datetime) -> float:
    y, month = utc.year, utc.month
    day = (
        utc.day
        + (utc.hour + utc.minute / 60.0 + utc.second / 3600.0) / 24.0
    )
    if month <= 2:
        y -= 1
        month += 12
    a = y // 100
    b = 2 - a + a // 4
    return (
        int(365.25 * (y + 4716))
        + int(30.6001 * (month + 1))
        + day
        + b
        - 1524.5
    )


def moon_altitude_deg(
    when: datetime,
    lat: float = SAN_DIEGO_LAT,
    lon: float = SAN_DIEGO_LON,
) -> float:
    """Approximate geocentric moon altitude. Good enough for 'is it up?'."""
    utc = when.astimezone(timezone.utc) if when.tzinfo else when.replace(
        tzinfo=timezone.utc
    )
    jd = _julian_date(utc)
    t = (jd - 2451545.0) / 36525.0

    def norm(deg: float) -> float:
        return deg % 360.0

    L = math.radians(norm(218.316 + 481267.8813 * t))
    M = math.radians(norm(134.963 + 477198.8676 * t))
    F = math.radians(norm(93.272 + 483202.0175 * t))
    lam = L + math.radians(6.289) * math.sin(M)
    beta = math.radians(5.128) * math.sin(F)
    eps = math.radians(23.439 - 0.0000004 * t)
    ra = math.atan2(
        math.cos(eps) * math.sin(lam) - math.tan(beta) * math.sin(eps),
        math.cos(lam),
    )
    dec = math.asin(
        math.sin(beta) * math.cos(eps)
        + math.cos(beta) * math.sin(eps) * math.sin(lam)
    )
    gmst = norm(280.46061837 + 360.98564736629 * (jd - 2451545.0))
    lst = math.radians(norm(gmst + lon))
    ha = lst - ra
    alt = math.asin(
        math.sin(math.radians(lat)) * math.sin(dec)
        + math.cos(math.radians(lat)) * math.cos(dec) * math.cos(ha)
    )
    return math.degrees(alt)


def moon_or_venus_likely_up(weather: WeatherSeed) -> bool:
    """
    Dark dawn: last stars / Venus are typically visible on a clear sky.
    After sunrise, require the moon above the horizon.
    """
    if weather.bodies_up is not None:
        return weather.bodies_up
    if still_dark(weather):
        return True
    if weather.pull_at is None:
        return False
    return moon_altitude_deg(weather.pull_at) > 0


def select_drawer(weather: WeatherSeed) -> DrawerDecision:
    """First match wins. Prefers the morning hourly signal."""
    if not weather.ok:
        return DrawerDecision(
            spec=DRAWERS[DRAWER_CLEAR_MILD],
            reason=(
                "weather unavailable — CLEAR MILD from San Diego "
                "body memory (not a forecast)"
            ),
        )

    code = _code(weather)
    precip = weather.precipitation
    cloud = _cloud(weather)
    temp = weather.temperature_2m
    vis = weather.visibility_m
    rh = weather.relative_humidity_2m
    hour_bit = (
        weather.pull_at.strftime("%H:%M") if weather.pull_at else "pull"
    )

    raining = (precip is not None and precip > 0) or (
        code is not None and code in RAIN_CODES
    )
    if raining:
        if precip is not None and precip > 0:
            why = f"precipitation {precip:g} > 0 at {hour_bit}"
        else:
            why = f"weather_code {code} (rain/drizzle/thunder) at {hour_bit}"
        return DrawerDecision(
            spec=DRAWERS[DRAWER_RAIN],
            reason=f"{why} → RAIN",
        )

    foggy = (code is not None and code in FOG_CODES) or (
        vis is not None
        and vis < FOG_VIS_M
        and rh is not None
        and rh >= FOG_RH
    )
    if foggy:
        if code is not None and code in FOG_CODES:
            why = f"weather_code {code}"
        else:
            why = (
                f"visibility {int(vis)}m < {FOG_VIS_M} and "
                f"RH {int(rh)}% ≥ {FOG_RH}"
            )
        return DrawerDecision(
            spec=DRAWERS[DRAWER_FOG],
            reason=f"{why} at {hour_bit} → FOG / MARINE LAYER",
        )

    overcast = (code == 3) or (
        cloud is not None and cloud >= OVERCAST_CLOUD
    )
    if overcast:
        if code == 3:
            why = "weather_code 3"
        else:
            why = f"cloud_cover {int(round(cloud))}% ≥ {OVERCAST_CLOUD}"
        return DrawerDecision(
            spec=DRAWERS[DRAWER_OVERCAST],
            reason=f"{why} at {hour_bit} (no rain, no fog) → OVERCAST / GLOOM",
        )

    hybrid = (
        code == 2
        and cloud is not None
        and HYBRID_CLOUD_LO <= cloud <= HYBRID_CLOUD_HI
        and temp is not None
        and temp >= HYBRID_TEMP_F
    )
    if hybrid:
        return DrawerDecision(
            spec=DRAWERS[DRAWER_HYBRID],
            reason=(
                f"weather_code 2, cloud_cover {int(round(cloud))}% "
                f"({HYBRID_CLOUD_LO}–{HYBRID_CLOUD_HI}), "
                f"{temp:g}°F ≥ {HYBRID_TEMP_F} at {hour_bit} → HYBRID BURNOFF"
            ),
        )

    clear_hot = (
        code in CLEARISH_CODES
        and temp is not None
        and temp >= CLEAR_HOT_TEMP_F
    )
    if clear_hot:
        return DrawerDecision(
            spec=DRAWERS[DRAWER_CLEAR_HOT],
            reason=(
                f"weather_code {code}, {temp:g}°F ≥ {CLEAR_HOT_TEMP_F} "
                f"at {hour_bit} (morning hourly; daily high unused) "
                f"→ CLEAR HOT"
            ),
        )

    starlit = (
        code in PARTLY_CODES
        and in_dawn_window(weather)
        and moon_or_venus_likely_up(weather)
    )
    if starlit:
        delta = minutes_from_sunrise(weather)
        if still_dark(weather):
            light = "still dark (is_day=0)"
        elif delta is not None:
            light = f"{abs(delta):.0f} min from sunrise"
        else:
            light = "dawn window"
        return DrawerDecision(
            spec=DRAWERS[DRAWER_STARLIT],
            reason=(
                f"weather_code {code}, {light}, moon/Venus likely up "
                f"at {hour_bit} → STARLIT DAWN"
            ),
        )

    extra = []
    if code is not None:
        extra.append(f"code {code}")
    if temp is not None:
        extra.append(f"{temp:g}°F")
    if weather.is_day is not None:
        extra.append(f"is_day {weather.is_day}")
    detail = ", ".join(extra) if extra else "unmatched morning hourly"
    return DrawerDecision(
        spec=DRAWERS[DRAWER_CLEAR_MILD],
        reason=f"else ({detail} at {hour_bit}) → CLEAR MILD",
    )


def choose_tell(
    spec: DrawerSpec,
    *,
    yesterday_drawer: Optional[str] = None,
    yesterday_tell: Optional[str] = None,
    rng: Optional[random.Random] = None,
) -> str:
    """
    One tell from the drawer. If the drawer changed, do not reuse
    yesterday's tell. Same-drawer reuse is allowed.
    """
    chooser = rng or random.Random()
    tells: Sequence[str] = spec.tells
    changed = (
        yesterday_drawer is not None
        and yesterday_drawer != spec.name
        and yesterday_tell
    )
    if changed:
        filtered = [t for t in tells if t != yesterday_tell]
        if filtered:
            tells = filtered
    return chooser.choice(list(tells))


def attach_tell(
    decision: DrawerDecision,
    *,
    yesterday_drawer: Optional[str] = None,
    yesterday_tell: Optional[str] = None,
    rng: Optional[random.Random] = None,
) -> DrawerDecision:
    tell = choose_tell(
        decision.spec,
        yesterday_drawer=yesterday_drawer,
        yesterday_tell=yesterday_tell,
        rng=rng,
    )
    decision.tell = tell
    decision.yesterday_drawer = yesterday_drawer
    decision.yesterday_tell = yesterday_tell
    return decision


def tell_tokens(tell: str) -> List[str]:
    words = re.findall(r"[a-zA-Z']+", tell.lower())
    kept = []
    for word in words:
        word = word.replace("'", "")
        if word in _STOP or len(word) < 3:
            continue
        kept.append(word)
    return kept


def haiku_has_tell(haiku: str, tell: str) -> bool:
    if not tell:
        return True
    blob = haiku.lower()
    if tell.lower() in blob:
        return True
    tokens = tell_tokens(tell)
    if not tokens:
        return True
    return any(token in blob for token in tokens)


_HEAT_BANNED = re.compile(
    r"\b(embers?|nape|yield|fade[- ]to[- ]black|soulmate|moonbeams?)\b",
    re.I,
)
_FOG_LEX = re.compile(
    r"\b(mist|fog|shroud|clover|peat|marine layer)\b",
    re.I,
)
_GRAY_PANE = re.compile(r"gray.{0,20}pane|pane.{0,20}gray", re.I)


def drawer_voice_problems(
    haiku: str,
    spec: DrawerSpec,
    tell: str,
) -> List[str]:
    """Reasons the writer should reject/regenerate this scrap."""
    problems: List[str] = []
    if tell and not haiku_has_tell(haiku, tell):
        problems.append(f"missing drawer tell ({tell})")
    if _HEAT_BANNED.search(haiku):
        problems.append("banned heat/generic lexicon (embers/nape/yield/soulmate/moonbeams)")
    if spec.name == DRAWER_CLEAR_HOT:
        if _GRAY_PANE.search(haiku):
            problems.append("CLEAR HOT + gray on the pane")
        if _FOG_LEX.search(haiku):
            problems.append("CLEAR HOT + fog lexicon")
    if spec.name in {DRAWER_CLEAR_MILD, DRAWER_STARLIT} and spec.name != DRAWER_FOG:
        # weather_code 0 + fog lexicon is the filed negative; mild/starlit
        # on a clear sky should not reach for mist-clover-as-weather.
        if spec.name == DRAWER_CLEAR_MILD and _FOG_LEX.search(haiku):
            problems.append("clear drawer + fog lexicon")
    return problems
