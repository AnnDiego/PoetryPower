"""
Thin San Diego weather seed — not a weather product.

Source: Open-Meteo free forecast API (no key).
  https://open-meteo.com/
  https://api.open-meteo.com/v1/forecast

We ask for today's high/low (°F) plus one WMO weather-code word
for downtown San Diego, timezone America/Los_Angeles.
On any failure the runner still writes; the seed just says weather
was unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .prompts import (
    SAN_DIEGO_LAT,
    SAN_DIEGO_LON,
    SAN_DIEGO_TZ,
    WEATHER_SOURCE,
    WEATHER_SOURCE_URL,
)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes → one condition word.
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


@dataclass
class WeatherSeed:
    """One day's high/low + a single condition word."""

    ok: bool
    high_f: Optional[int] = None
    low_f: Optional[int] = None
    condition: str = "unknown"
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
        return f"high {self.high_f}°F / low {self.low_f}°F, {self.condition}"


def condition_word(code: Any) -> str:
    try:
        return _WMO_WORD.get(int(code), "mixed")
    except (TypeError, ValueError):
        return "mixed"


def parse_open_meteo(data: Dict[str, Any]) -> WeatherSeed:
    """Parse a forecast JSON body. Used by fetch and by tests."""
    daily = data.get("daily") or {}
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    codes = daily.get("weather_code") or []
    if not highs or not lows:
        current = data.get("current") or {}
        temp = current.get("temperature_2m")
        code = current.get("weather_code")
        if temp is None:
            return WeatherSeed(ok=False, error="Open-Meteo JSON missing temps")
        rounded = int(round(float(temp)))
        return WeatherSeed(
            ok=True,
            high_f=rounded,
            low_f=rounded,
            condition=condition_word(code),
        )
    return WeatherSeed(
        ok=True,
        high_f=int(round(float(highs[0]))),
        low_f=int(round(float(lows[0]))),
        condition=condition_word(codes[0] if codes else None),
    )


def fetch_san_diego_weather(*, timeout: float = 12.0) -> WeatherSeed:
    """GET today's San Diego forecast. Never raises."""
    try:
        import requests
    except ImportError:
        return WeatherSeed(ok=False, error="requests not installed")

    params = {
        "latitude": SAN_DIEGO_LAT,
        "longitude": SAN_DIEGO_LON,
        "daily": "temperature_2m_max,temperature_2m_min,weather_code",
        "current": "temperature_2m,weather_code",
        "temperature_unit": "fahrenheit",
        "timezone": SAN_DIEGO_TZ,
        "forecast_days": 1,
    }
    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — thin seed; any failure is a skip
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
    return parse_open_meteo(data)


def weekday_vibe(weekday_name: str) -> str:
    return WEEKDAY_VIBES.get(weekday_name, "ordinary San Diego morning")
