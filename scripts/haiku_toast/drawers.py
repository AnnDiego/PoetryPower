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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .prompts import INLAND_HOME_LAT, INLAND_HOME_LON
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
RECENT_HISTORY_N = 5
# Last N calendar days of toasts/*_haiku.txt (+ sibling reports).
TOAST_ARTIFACT_LOOKBACK_DAYS = 3

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

# Soft-nature body/earth cluster Ann flagged as samey (toes + clover,
# mist + pane + clover). One of these per scrap unless the required
# tell already names more than one (hybrid pane/toes).
SOFT_NATURE_BODY = frozenset(
    {
        "mist",
        "fog",
        "clover",
        "peat",
        "pane",
        "moss",
        "tendril",
        "tendrils",
        "toe",
        "toes",
        "shroud",
        "marine",
    }
)
_SOFT_NATURE_CANON = {"toe": "toes", "tendril": "tendrils"}

# Too common to treat as a "signature noun" across mornings.
# Coffee / steam / mug / light may stay in voice after a picnic morning.
_GENERIC_SIGNATURE = frozenset(
    {
        "sun",
        "day",
        "dawn",
        "morning",
        "light",
        "sky",
        "first",
        "finds",
        "still",
        "heat",
        "gold",
        "gray",
        "grey",
        "will",
        "that",
        "this",
        "through",
        "promise",
        "considering",
        "breaking",
        "clothes",
        "coffee",
        "steam",
        "mug",
        "cup",
    }
)

# Distinctive drawer nouns banned across the recent-toast window.
# Not the whole picnic tag (that would also ban coffee).
STICKY_NOUNS = frozenset(
    {
        "brie",
        "cheese",
        "wedge",
        "checkered",
        "clover",
        "toes",
        "toe",
        "peat",
        "taco",
        "tacos",
        "gingham",
        "camembert",
        "cheddar",
    }
)
_STICKY_CANON = {
    "toe": "toes",
    "taco": "tacos",
}

# Multi-word picnic / body tells that stacked on 2026-09-10 / 09-11.
STICKY_PHRASES = (
    "gold brie",
    "brie wedge",
    "cheese wedge",
    "checkered cloth",
    "pillow-shield",
    "pillow shield",
    "palm-frond",
    "palm frond",
)

# Drawers that may stay nature-forward. Still no earth-body pile-on.
NATURE_ONLY_DRAWERS = frozenset(
    {
        DRAWER_FOG,
        DRAWER_OVERCAST,
        DRAWER_RAIN,
        DRAWER_HYBRID,
        DRAWER_STARLIT,
    }
)

# Motif tags recorded on each morning. soft_earth is samey across days.
# Picnic cheese/cloth are blocked via sticky nouns, not this whole picnic tag
# (that tag still includes coffee).
MOTIF_TAG_WORDS = {
    "soft_earth": frozenset(
        {
            "mist",
            "fog",
            "clover",
            "peat",
            "moss",
            "pane",
            "shroud",
            "marine",
            "tendril",
            "tendrils",
        }
    ),
    "body_path": frozenset({"toes", "toe", "hips", "forehead", "nape", "cheek"}),
    "picnic": frozenset({"brie", "coffee", "checkered", "cloth", "taco", "pillow"}),
    "picnic_cheese": frozenset({"brie", "cheese", "wedge", "camembert", "cheddar"}),
    "picnic_cloth": frozenset({"checkered", "gingham"}),
    "gold_light": frozenset({"buttery", "gold", "photons", "pearl", "luminous"}),
    "celestial": frozenset({"moon", "venus", "stars", "crescent", "saucer"}),
    "rain_song": frozenset({"rain", "drum", "chime", "chimes", "roof"}),
}
SAMEY_MOTIFS = frozenset({"soft_earth"})


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
    avoided_tells: Tuple[str, ...] = ()
    recent_nouns: Tuple[str, ...] = ()

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
    motifs: Tuple[str, ...] = ()
    key_words: Tuple[str, ...] = ()
    history: Tuple["LastDrawer", ...] = ()


def last_drawer_path(out_dir: Path) -> Path:
    return Path(out_dir) / STATE_FILENAME


def _memory_from_dict(data: dict) -> Optional[LastDrawer]:
    date = data.get("date")
    drawer = data.get("drawer")
    tell = data.get("tell")
    if not date or not drawer or not tell:
        return None
    motifs = data.get("motifs") or ()
    key_words = data.get("key_words") or ()
    return LastDrawer(
        date=str(date),
        drawer=str(drawer),
        tell=str(tell),
        motifs=tuple(str(m) for m in motifs),
        key_words=tuple(str(w) for w in key_words),
    )


def load_last_drawer(out_dir: Path) -> Optional[LastDrawer]:
    path = last_drawer_path(out_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    latest = _memory_from_dict(data)
    if latest is None:
        return None
    history: List[LastDrawer] = []
    for item in data.get("history") or []:
        if not isinstance(item, dict):
            continue
        mem = _memory_from_dict(item)
        if mem is not None:
            history.append(mem)
    latest.history = tuple(history)
    return latest


def _memory_to_dict(mem: LastDrawer) -> dict:
    return {
        "date": mem.date,
        "drawer": mem.drawer,
        "tell": mem.tell,
        "motifs": list(mem.motifs),
        "key_words": list(mem.key_words),
    }


def save_last_drawer(
    out_dir: Path,
    *,
    date: str,
    drawer: str,
    tell: str,
    haiku: str = "",
    previous: Optional[LastDrawer] = None,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = last_drawer_path(out_dir)
    key_words = extract_key_words(tell, haiku)
    motifs = motif_tags_for_text(f"{tell}\n{haiku}")
    history = [_memory_to_dict(mem) for mem in prior_mornings(previous, date)]
    path.write_text(
        json.dumps(
            {
                "date": date,
                "drawer": drawer,
                "tell": tell,
                "motifs": list(motifs),
                "key_words": list(key_words),
                "history": history,
            },
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


def prior_mornings(
    last: Optional[LastDrawer],
    today: str,
    *,
    n: int = RECENT_HISTORY_N,
) -> List[LastDrawer]:
    """Prior mornings (not today), newest first, capped at *n*."""
    if last is None:
        return []
    rows: List[LastDrawer] = []
    if last.date < today:
        rows.append(
            LastDrawer(
                date=last.date,
                drawer=last.drawer,
                tell=last.tell,
                motifs=last.motifs,
                key_words=last.key_words,
            )
        )
    for mem in last.history:
        if mem.date < today:
            rows.append(
                LastDrawer(
                    date=mem.date,
                    drawer=mem.drawer,
                    tell=mem.tell,
                    motifs=mem.motifs,
                    key_words=mem.key_words,
                )
            )
    seen = set()
    out: List[LastDrawer] = []
    for mem in rows:
        if mem.date in seen:
            continue
        seen.add(mem.date)
        out.append(mem)
    return out[:n]


_STAMP_NAME = re.compile(r"^(\d{8})-\d{4}_(haiku\.txt|toast\.md)$")
_REPORT_TELL = re.compile(r"^- \*\*Tell:\*\* (.+)$", re.M)
_REPORT_DRAWER = re.compile(r"^- \*\*Drawer:\*\* (.+)$", re.M)
_REPORT_HAIKU = re.compile(
    r"^## Haiku\s*\n+(.+?)(?:\n## |\n---|\Z)", re.M | re.S
)


def _iso_from_yyyymmdd(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def _iso_minus_days(today: str, days: int) -> str:
    try:
        d = datetime.strptime(today, "%Y-%m-%d").date()
    except ValueError:
        return today
    return (d - timedelta(days=days)).isoformat()


def _normalize_drawer_label(label: str) -> str:
    raw = (label or "").strip()
    if not raw or raw.lower() == "n/a":
        return "UNKNOWN"
    if raw in DRAWERS:
        return raw
    compact = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    if compact in DRAWERS:
        return compact
    for name, spec in DRAWERS.items():
        if compact == name.lower():
            return name
        spec_compact = re.sub(
            r"[^a-z0-9]+", "_", spec.display_name.lower()
        ).strip("_")
        if compact == spec_compact or spec_compact.startswith(compact + "_"):
            return name
    return "UNKNOWN"


def sticky_hits(text: str) -> List[str]:
    """Sticky picnic/body phrases and nouns found in *text*."""
    blob = re.sub(r"[-–—]", " ", (text or "").lower())
    blob = re.sub(r"\s+", " ", blob)
    hits: List[str] = []
    seen = set()
    for phrase in STICKY_PHRASES:
        needle = phrase.replace("-", " ")
        if needle in blob and phrase not in seen:
            seen.add(phrase)
            hits.append(phrase)
    for word in re.findall(r"[a-zA-Z']+", (text or "").lower()):
        word = word.replace("'", "")
        canon = _STICKY_CANON.get(word, word)
        if canon in STICKY_NOUNS and canon not in seen:
            seen.add(canon)
            hits.append(canon)
    return hits


def _memory_from_artifact(
    *,
    date: str,
    haiku: str,
    tell: str,
    drawer: str,
) -> LastDrawer:
    used_tell = tell if tell and tell.lower() != "n/a" else ""
    if not used_tell:
        hits = sticky_hits(haiku)
        used_tell = hits[0] if hits else "(from toast)"
    used_drawer = drawer if drawer and drawer != "UNKNOWN" else "UNKNOWN"
    blob = f"{used_tell}\n{haiku}"
    return LastDrawer(
        date=date,
        drawer=used_drawer,
        tell=used_tell,
        motifs=motif_tags_for_text(blob),
        key_words=extract_key_words(used_tell, haiku),
    )


def memories_from_toast_artifacts(
    out_dir: Path,
    today: str,
    *,
    days: int = TOAST_ARTIFACT_LOOKBACK_DAYS,
) -> List[LastDrawer]:
    """Rebuild prior mornings from toasts/*_haiku.txt and *_toast.md."""
    root = Path(out_dir)
    if not root.is_dir():
        return []
    cutoff = _iso_minus_days(today, days)
    by_date: Dict[str, List[Tuple[str, str, str]]] = {}
    for path in root.iterdir():
        match = _STAMP_NAME.match(path.name)
        if not match:
            continue
        date = _iso_from_yyyymmdd(match.group(1))
        if date >= today or date < cutoff:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if path.name.endswith("_haiku.txt"):
            haiku = text.strip()
            report = ""
        else:
            haiku_match = _REPORT_HAIKU.search(text)
            haiku = haiku_match.group(1).strip() if haiku_match else ""
            report = text
        by_date.setdefault(date, []).append((path.name, haiku, report))

    rows: List[LastDrawer] = []
    for date in sorted(by_date, reverse=True):
        haikus: List[str] = []
        tells: List[str] = []
        drawers: List[str] = []
        for _name, haiku, report in sorted(by_date[date]):
            if haiku:
                haikus.append(haiku)
            if not report:
                continue
            tell_m = _REPORT_TELL.search(report)
            drawer_m = _REPORT_DRAWER.search(report)
            if tell_m:
                tells.append(tell_m.group(1).strip())
            if drawer_m:
                drawers.append(_normalize_drawer_label(drawer_m.group(1).strip()))
        if not haikus and not tells:
            continue
        tell = next((t for t in tells if t and t.lower() != "n/a"), "")
        drawer = next((d for d in drawers if d != "UNKNOWN"), "UNKNOWN")
        rows.append(
            _memory_from_artifact(
                date=date,
                haiku="\n".join(haikus),
                tell=tell,
                drawer=drawer,
            )
        )
    return rows


def _prefer_real_tell(left: str, right: str) -> str:
    placeholders = {"", "(from toast)", "n/a"}
    if left and left.lower() not in placeholders:
        return left
    if right and right.lower() not in placeholders:
        return right
    return left or right


def merge_morning_memories(*groups: Sequence[LastDrawer]) -> List[LastDrawer]:
    """Union key words / motifs by date. Newest first."""
    by_date: Dict[str, LastDrawer] = {}
    for group in groups:
        for mem in group:
            existing = by_date.get(mem.date)
            if existing is None:
                by_date[mem.date] = mem
                continue
            words: List[str] = []
            seen = set()
            for word in (*existing.key_words, *mem.key_words):
                if word in seen:
                    continue
                seen.add(word)
                words.append(word)
            motifs = tuple(dict.fromkeys((*existing.motifs, *mem.motifs)))
            drawer = existing.drawer
            if drawer in {"", "UNKNOWN"} and mem.drawer not in {"", "UNKNOWN"}:
                drawer = mem.drawer
            by_date[mem.date] = LastDrawer(
                date=mem.date,
                drawer=drawer,
                tell=_prefer_real_tell(existing.tell, mem.tell),
                motifs=motifs,
                key_words=tuple(words),
            )
    return sorted(by_date.values(), key=lambda m: m.date, reverse=True)[
        :RECENT_HISTORY_N
    ]


def recent_toast_history(
    out_dir: Path,
    today: str,
    previous: Optional[LastDrawer] = None,
) -> List[LastDrawer]:
    """JSON rolling memory plus last few days of toasts/ artifacts."""
    if previous is None:
        previous = load_last_drawer(out_dir)
    return merge_morning_memories(
        prior_mornings(previous, today),
        memories_from_toast_artifacts(out_dir, today),
    )


def recent_signature_nouns(recent: Sequence[LastDrawer]) -> List[str]:
    """Distinct tell tokens + key words from recent mornings (no motif tags)."""
    out: List[str] = []
    seen = set()
    tag_names = set(MOTIF_TAG_WORDS)
    for mem in recent:
        for word in (*tell_tokens(mem.tell), *mem.key_words):
            if (
                word in seen
                or word in tag_names
                or word in _STOP
                or word in _GENERIC_SIGNATURE
            ):
                continue
            seen.add(word)
            out.append(word)
    return out


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
    lat: float = INLAND_HOME_LAT,
    lon: float = INLAND_HOME_LON,
) -> float:
    """Approximate geocentric moon altitude at inland home (zip 92128)."""
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
    recent: Optional[Sequence[LastDrawer]] = None,
    rng: Optional[random.Random] = None,
) -> str:
    """
    One tell from the drawer. Skip yesterday's tell when the drawer
    changed, and skip tells that collide with recent mornings when
    another tell in this drawer is still available.
    """
    tell, _skipped = choose_tell_filtered(
        spec,
        yesterday_drawer=yesterday_drawer,
        yesterday_tell=yesterday_tell,
        recent=recent,
        rng=rng,
    )
    return tell


def choose_tell_filtered(
    spec: DrawerSpec,
    *,
    yesterday_drawer: Optional[str] = None,
    yesterday_tell: Optional[str] = None,
    recent: Optional[Sequence[LastDrawer]] = None,
    rng: Optional[random.Random] = None,
) -> Tuple[str, List[str]]:
    """Return (tell, skipped tells) after applying anti-repetition filters."""
    chooser = rng or random.Random()
    tells = list(spec.tells)
    skipped: List[str] = []
    changed = (
        yesterday_drawer is not None
        and yesterday_drawer != spec.name
        and yesterday_tell
    )
    if changed:
        filtered = [t for t in tells if t != yesterday_tell]
        if filtered:
            if yesterday_tell in tells:
                skipped.append(yesterday_tell)
            tells = filtered
    if recent:
        kept = [t for t in tells if not tell_collides_with_recent(t, recent)]
        if kept:
            skipped.extend(t for t in tells if t not in kept)
            tells = kept
    return chooser.choice(tells), skipped


def attach_tell(
    decision: DrawerDecision,
    *,
    yesterday_drawer: Optional[str] = None,
    yesterday_tell: Optional[str] = None,
    recent: Optional[Sequence[LastDrawer]] = None,
    rng: Optional[random.Random] = None,
) -> DrawerDecision:
    tell, skipped = choose_tell_filtered(
        decision.spec,
        yesterday_drawer=yesterday_drawer,
        yesterday_tell=yesterday_tell,
        recent=recent,
        rng=rng,
    )
    decision.tell = tell
    decision.yesterday_drawer = yesterday_drawer
    decision.yesterday_tell = yesterday_tell
    decision.avoided_tells = tuple(skipped)
    decision.recent_nouns = tuple(recent_signature_nouns(recent or ()))
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


def _all_tell_words() -> frozenset:
    words: set = set()
    for spec in DRAWERS.values():
        for tell in spec.tells:
            words.update(tell_tokens(tell))
    words.update(SOFT_NATURE_BODY)
    words.update(STICKY_NOUNS)
    return frozenset(words)


_ALL_TELL_WORDS: Optional[frozenset] = None


def all_tell_words() -> frozenset:
    global _ALL_TELL_WORDS
    if _ALL_TELL_WORDS is None:
        _ALL_TELL_WORDS = _all_tell_words()
    return _ALL_TELL_WORDS


def soft_nature_hits(text: str) -> List[str]:
    """Canonical soft-nature body/earth tokens found in *text*."""
    words = re.findall(r"[a-zA-Z']+", text.lower())
    hits: List[str] = []
    seen = set()
    for word in words:
        word = word.replace("'", "")
        canon = _SOFT_NATURE_CANON.get(word, word)
        if canon in SOFT_NATURE_BODY and canon not in seen:
            seen.add(canon)
            hits.append(canon)
    return hits


def soft_nature_doubledip(haiku: str, tell: str = "") -> bool:
    """
    True when the scrap stacks two near-identical earth-body tells.

    The required tell may already name more than one (hybrid pane/toes).
    Extra cluster members beyond max(1, hits-in-tell) are a pile-on.
    """
    scrap = soft_nature_hits(haiku)
    tell_hits = soft_nature_hits(tell)
    allowed = max(1, len(tell_hits))
    return len(scrap) > allowed


def motif_tags_for_text(text: str) -> Tuple[str, ...]:
    tokens = set(tell_tokens(text))
    tokens.update(soft_nature_hits(text))
    tags = []
    for tag, words in MOTIF_TAG_WORDS.items():
        if tokens & words:
            tags.append(tag)
    return tuple(tags)


def extract_key_words(tell: str, haiku: str = "") -> Tuple[str, ...]:
    """Signature nouns: sticky picnic/body hits + tell tokens + soft-nature."""
    allowed = all_tell_words()
    blob = f"{tell}\n{haiku}"
    out: List[str] = []
    seen = set()
    for word in (
        *sticky_hits(blob),
        *tell_tokens(tell),
        *tell_tokens(haiku),
        *soft_nature_hits(haiku),
    ):
        if word in seen or word in _GENERIC_SIGNATURE:
            continue
        if (
            word in SOFT_NATURE_BODY
            or word in STICKY_NOUNS
            or word in STICKY_PHRASES
            or word in allowed
        ):
            seen.add(word)
            out.append(word)
    return tuple(out)


def _sticky_set(text: str, extra: Sequence[str] = ()) -> set:
    hits = set(sticky_hits(text))
    for word in extra:
        low = word.lower()
        if low in STICKY_NOUNS or low in STICKY_PHRASES:
            hits.add(low)
        for part in re.findall(r"[a-z]+", low):
            canon = _STICKY_CANON.get(part, part)
            if canon in STICKY_NOUNS:
                hits.add(canon)
    return hits


def tell_collides_with_recent(
    tell: str,
    recent: Sequence[LastDrawer],
) -> bool:
    """True when this tell reuses a recent tell, noun, or samey motif."""
    if not recent:
        return False
    tell_l = tell.lower()
    tokens = {w for w in tell_tokens(tell) if w not in _GENERIC_SIGNATURE}
    tell_soft = set(soft_nature_hits(tell))
    tell_sticky = _sticky_set(tell)
    recent_tokens: set = set()
    recent_sticky: set = set()
    recent_soft = False
    for mem in recent:
        if mem.tell and mem.tell.lower() == tell_l:
            return True
        recent_tokens.update(
            w for w in tell_tokens(mem.tell) if w not in _GENERIC_SIGNATURE
        )
        recent_tokens.update(
            w for w in mem.key_words if w not in _GENERIC_SIGNATURE
        )
        recent_sticky.update(_sticky_set(mem.tell, mem.key_words))
        if SAMEY_MOTIFS & set(mem.motifs) or soft_nature_hits(mem.tell):
            recent_soft = True
        if set(mem.key_words) & SOFT_NATURE_BODY:
            recent_soft = True
    if tokens & recent_tokens:
        return True
    if tell_sticky & recent_sticky:
        return True
    if recent_soft and tell_soft:
        return True
    return False


def _noun_is_protected(noun: str, protected: set) -> bool:
    low = noun.lower()
    if low in protected:
        return True
    parts = re.findall(r"[a-z]+", low)
    return bool(parts) and any(
        _STICKY_CANON.get(part, part) in protected or part in protected
        for part in parts
    )


def recent_noun_reuse(
    haiku: str,
    tell: str,
    recent_nouns: Sequence[str],
) -> List[str]:
    """Recent signature nouns that appear in the scrap but not today's tell."""
    if not recent_nouns:
        return []
    blob = haiku.lower()
    protected = (
        set(tell_tokens(tell))
        | set(soft_nature_hits(tell))
        | set(sticky_hits(tell))
    )
    allowed = all_tell_words() | STICKY_NOUNS | set(STICKY_PHRASES)
    reused: List[str] = []
    for noun in recent_nouns:
        low = noun.lower()
        if _noun_is_protected(low, protected):
            continue
        is_phrase = " " in low or "-" in low
        if low not in allowed and not is_phrase:
            continue
        if not is_phrase and low not in STICKY_NOUNS and len(low) < 4:
            continue
        if re.search(rf"\b{re.escape(low)}\b", blob):
            reused.append(noun)
    return reused


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
    *,
    recent_nouns: Optional[Sequence[str]] = None,
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
    if soft_nature_doubledip(haiku, tell):
        problems.append(
            "soft-nature body/earth double-dip "
            "(toes + clover, or mist + pane + clover pile-on)"
        )
    reused = recent_noun_reuse(haiku, tell, recent_nouns or ())
    if reused:
        problems.append(
            "repeats recent morning noun (" + ", ".join(reused) + ")"
        )
    return problems
