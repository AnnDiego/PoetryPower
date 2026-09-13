"""
Morning weather snapshot for Daily Haiku Toast.

Pulled for Ann's inland home zip 92128 (Rancho Bernardo), not
downtown / coastal San Diego — see SAN_DIEGO_LAT / SAN_DIEGO_LON.

Source: Open-Meteo free forecast API (no key).
  https://open-meteo.com/
  https://api.open-meteo.com/v1/forecast

We pull hourly fields at the run hour (live path is ~6:15–6:45am PDT)
plus daily sunrise. Drawer selection uses sky + moisture + light at
that hour — not the daily high, and never temperature to raise chili.

On any failure the runner still writes; the seed just says weather
was unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from .prompts import (
    SAN_DIEGO_LAT,
    SAN_DIEGO_LON,
    SAN_DIEGO_TZ,
    WEATHER_SOURCE,
    WEATHER_SOURCE_URL,
)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_FIELDS = (
    "weather_code",
    "cloud_cover",
    "cloud_cover_low",
    "visibility",
    "relative_humidity_2m",
    "temperature_2m",
    "precipitation",
    "precipitation_probability",
    "is_day",
)
DAILY_FIELDS = (
    "sunrise",
    "temperature_2m_max",
    "temperature_2m_min",
)

# WMO weather interpretation codes → one condition word (report only).
# https://open-meteo.com/en/docs#weathervariables
_WMO_WORD = {
    0: "clear",
    1: "mainly-clear",
    2: "partly-cloudy",
    3: "overcast",
    45: "fog",
    48: "rime-fog",
    51: "drizzle",
    53: "drizzle",
    55: "drizzle",
    56: "freezing-drizzle",
    57: "freezing-drizzle",
    61: "rain",
    63: "rain",
    65: "rain",
    66: "freezing-rain",
    67: "freezing-rain",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow-grains",
    80: "showers",
    81: "showers",
    82: "showers",
    85: "snow-showers",
    86: "snow-showers",
    95: "thunderstorm",
    96: "thunderstorm",
    99: "thunderstorm",
}

WEEKDAY_VIBES = {
    "Monday": "slow start, leftover weekend crumbs",
    "Tuesday": "midweek quiet, desk-adjacent",
    "Wednesday": "hump-day stubbornness, marine or canyon",
    "Thursday": "almost-Friday lean",
    "Friday": "harbor light stretching, Padres-night possibility",
    "Saturday": "picnic leftovers, canyon walk",
    "Sunday": "soft reset, ramen steam or late coffee",
}


def _tz() -> ZoneInfo:
    return ZoneInfo(SAN_DIEGO_TZ)


def _as_local(when: datetime) -> datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=_tz())
    return when.astimezone(_tz())


def _parse_iso_local(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return _as_local(parsed)


def _num(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _intish(value: Any) -> Optional[int]:
    number = _num(value)
    if number is None:
        return None
    return int(round(number))


@dataclass
class WeatherSeed:
    """Morning hourly snapshot + daily sunrise. High/low are context only."""

    ok: bool
    high_f: Optional[int] = None
    low_f: Optional[int] = None
    condition: str = "unknown"
    weather_code: Optional[int] = None
    cloud_cover: Optional[float] = None
    cloud_cover_low: Optional[float] = None
    visibility_m: Optional[float] = None
    relative_humidity_2m: Optional[float] = None
    temperature_2m: Optional[float] = None
    precipitation: Optional[float] = None
    precipitation_probability: Optional[float] = None
    is_day: Optional[int] = None
    sunrise: Optional[datetime] = None
    pull_at: Optional[datetime] = None
    bodies_up: Optional[bool] = None  # test override for moon/Venus
    source: str = WEATHER_SOURCE
    source_url: str = WEATHER_SOURCE_URL
    error: Optional[str] = None

    def seed_line(self) -> str:
        if not self.ok:
            return (
                "weather unavailable — write from San Diego body memory, "
                "not a forecast lecture"
                + (f" ({self.error})" if self.error else "")
            )
        hour = self.pull_at.strftime("%H:%M") if self.pull_at else "??:??"
        temp = (
            f"{int(round(self.temperature_2m))}°F"
            if self.temperature_2m is not None
            else "?°F"
        )
        cloud = (
            f"{int(round(self.cloud_cover))}%"
            if self.cloud_cover is not None
            else "?"
        )
        vis = (
            f"{int(round(self.visibility_m))}m"
            if self.visibility_m is not None
            else "?"
        )
        rh = (
            f"{int(round(self.relative_humidity_2m))}%"
            if self.relative_humidity_2m is not None
            else "?"
        )
        precip = (
            f"{self.precipitation:g}"
            if self.precipitation is not None
            else "?"
        )
        code = self.weather_code if self.weather_code is not None else "?"
        return (
            f"{hour} PT hourly · code {code} {self.condition} · {temp} · "
            f"cloud {cloud} · vis {vis} · RH {rh} · precip {precip}"
        )

    def hourly_report_line(self) -> str:
        if not self.ok:
            return self.seed_line()
        sunrise = self.sunrise.strftime("%H:%M") if self.sunrise else "?"
        is_day = self.is_day if self.is_day is not None else "?"
        pop = (
            f"{int(round(self.precipitation_probability))}%"
            if self.precipitation_probability is not None
            else "?"
        )
        return (
            f"{self.seed_line()} · is_day {is_day} · sunrise {sunrise} · "
            f"precip chance {pop}"
        )

    def daily_context_line(self) -> str:
        if self.high_f is None and self.low_f is None:
            return "daily high/low unused (not fetched)"
        high = f"{self.high_f}°F" if self.high_f is not None else "?"
        low = f"{self.low_f}°F" if self.low_f is not None else "?"
        return (
            f"high {high} / low {low} — context only; not used for the "
            "drawer or chili"
        )


def condition_word(code: Any) -> str:
    try:
        return _WMO_WORD.get(int(code), "mixed")
    except (TypeError, ValueError):
        return "mixed"


def pick_hourly_index(times: List[Any], when: datetime) -> Optional[int]:
    """Use the slot whose local hour matches the pull (morning signal)."""
    when = _as_local(when)
    parsed: List[datetime] = []
    for raw in times:
        dt = _parse_iso_local(raw)
        if dt is None:
            return None
        parsed.append(dt)
    if not parsed:
        return None
    for i, dt in enumerate(parsed):
        if dt.date() == when.date() and dt.hour == when.hour:
            return i
    # Same calendar day, nearest hour; else nearest overall.
    same_day = [
        (i, dt) for i, dt in enumerate(parsed) if dt.date() == when.date()
    ]
    pool = same_day or list(enumerate(parsed))
    return min(pool, key=lambda item: abs((item[1] - when).total_seconds()))[0]


def parse_open_meteo(
    data: Dict[str, Any],
    *,
    when: Optional[datetime] = None,
) -> WeatherSeed:
    """Parse forecast JSON. Drawer path needs hourly at pull hour."""
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return WeatherSeed(ok=False, error="Open-Meteo JSON missing hourly")

    pull = _as_local(when) if when is not None else datetime.now(_tz())
    idx = pick_hourly_index(times, pull)
    if idx is None:
        return WeatherSeed(ok=False, error="Open-Meteo hourly times unreadable")

    pull_slot = _parse_iso_local(times[idx]) or pull.replace(
        minute=0, second=0, microsecond=0
    )

    def _at(field: str) -> Optional[float]:
        values = hourly.get(field) or []
        if idx >= len(values):
            return None
        return _num(values[idx])

    code = _intish(_at("weather_code"))
    cloud = _at("cloud_cover")
    cloud_low = _at("cloud_cover_low")
    if cloud is None:
        cloud = cloud_low

    daily = data.get("daily") or {}
    sunrises = daily.get("sunrise") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    is_day_raw = _at("is_day")
    is_day = int(is_day_raw) if is_day_raw is not None else None

    return WeatherSeed(
        ok=True,
        high_f=_intish(highs[0]) if highs else None,
        low_f=_intish(lows[0]) if lows else None,
        condition=condition_word(code),
        weather_code=code,
        cloud_cover=cloud,
        cloud_cover_low=cloud_low,
        visibility_m=_at("visibility"),
        relative_humidity_2m=_at("relative_humidity_2m"),
        temperature_2m=_at("temperature_2m"),
        precipitation=_at("precipitation"),
        precipitation_probability=_at("precipitation_probability"),
        is_day=is_day,
        sunrise=_parse_iso_local(sunrises[0]) if sunrises else None,
        pull_at=pull_slot,
    )


def fetch_san_diego_weather(
    *,
    when: Optional[datetime] = None,
    timeout: float = 12.0,
) -> WeatherSeed:
    """GET inland-home (zip 92128) hourly + sunrise. Never raises."""
    try:
        import requests
    except ImportError:
        return WeatherSeed(ok=False, error="requests not installed")

    pull = _as_local(when) if when is not None else datetime.now(_tz())
    day = pull.date().isoformat()
    params = {
        "latitude": SAN_DIEGO_LAT,
        "longitude": SAN_DIEGO_LON,
        "hourly": ",".join(HOURLY_FIELDS),
        "daily": ",".join(DAILY_FIELDS),
        "temperature_unit": "fahrenheit",
        "timezone": SAN_DIEGO_TZ,
        "start_date": day,
        "end_date": day,
    }
    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — seed; any failure is a skip
        return WeatherSeed(ok=False, error=str(exc))

    if resp.status_code >= 400:
        return WeatherSeed(
            ok=False, error=f"Open-Meteo HTTP {resp.status_code}"
        )
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return WeatherSeed(ok=False, error=f"Open-Meteo JSON: {exc}")
    if not isinstance(data, dict):
        return WeatherSeed(ok=False, error="Open-Meteo returned a non-object")
    return parse_open_meteo(data, when=pull)


def weekday_vibe(weekday_name: str) -> str:
    return WEEKDAY_VIBES.get(weekday_name, "ordinary San Diego morning")
