"""
Morning weather for Daily Haiku Toast — two Open-Meteo points.

Inland home (zip 92128): hourly snapshot for the drawer, haiku seed,
moon helpers, and Notion same-day weather line.

Downtown / coast (32.7157, -117.1611): multi-day high/low + condition
strip for Morning Toast → X captions only. Never seeds the scrap.

Source: Open-Meteo free forecast API (no key).
  https://open-meteo.com/
  https://api.open-meteo.com/v1/forecast

Toast path pulls hourly fields at the run hour (live ~6:15–6:45am PDT)
plus daily sunrise. Drawer selection uses sky + moisture + light at
that hour — not the daily high, and never temperature to raise chili.

On any failure the runner still writes; the seed just says weather
was unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from .prompts import (
    DOWNTOWN_LAT,
    DOWNTOWN_LOCATION,
    DOWNTOWN_LON,
    INLAND_HOME_LAT,
    INLAND_HOME_LOCATION,
    INLAND_HOME_LON,
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
# Downtown X outlook uses daily high/low + code (not hourly, not sunrise).
X_FORECAST_DAILY_FIELDS = (
    "temperature_2m_max",
    "temperature_2m_min",
    "weather_code",
)
_WEEKDAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
USE_TOAST = "toast"
USE_X_FORECAST = "x_forecast"

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
    location: str = INLAND_HOME_LOCATION
    use: str = USE_TOAST
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

    def notion_line(self) -> str:
        """Same-day Notion weather line. Inland toast seed only."""
        if not self.ok:
            return "San Diego: weather unavailable"
        high = f"{self.high_f}°F" if self.high_f is not None else "?"
        low = f"{self.low_f}°F" if self.low_f is not None else "?"
        return f"San Diego: high {high} / low {low}, {self.condition}"


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
        location=INLAND_HOME_LOCATION,
        use=USE_TOAST,
    )


@dataclass
class ForecastDay:
    """One downtown daily row for the X caption strip."""

    date: date
    weekday_short: str
    high_f: Optional[int] = None
    low_f: Optional[int] = None
    condition: str = "unknown"
    weather_code: Optional[int] = None

    def strip_line(self) -> str:
        high = f"{self.high_f}" if self.high_f is not None else "?"
        low = f"{self.low_f}" if self.low_f is not None else "?"
        return f"{self.weekday_short} {high}/{low} {self.condition}"


@dataclass
class DowntownForecast:
    """Mon–Fri or Fri–Su downtown/coast strip. X captions only."""

    ok: bool
    kind: str  # "weekday" | "weekend"
    forecast_days: int
    start_date: Optional[date] = None
    days: List[ForecastDay] = field(default_factory=list)
    location: str = DOWNTOWN_LOCATION
    lat: float = DOWNTOWN_LAT
    lon: float = DOWNTOWN_LON
    source: str = WEATHER_SOURCE
    source_url: str = WEATHER_SOURCE_URL
    use: str = USE_X_FORECAST
    error: Optional[str] = None

    def heading(self) -> str:
        if self.kind == "weekend":
            return "Weekend (SD coast)"
        return "Week ahead (SD coast)"

    def strip_text(self) -> str:
        return "\n".join(day.strip_line() for day in self.days)

    def compose_block(self) -> str:
        """Paste-ready strip for Morning Toast → X (no greeting/haiku)."""
        if not self.ok:
            return (
                "downtown X forecast unavailable"
                + (f" ({self.error})" if self.error else "")
            )
        body = self.strip_text()
        return f"{self.heading()}:\n{body}" if body else self.heading()


def x_forecast_window(when: datetime) -> Tuple[date, int, str]:
    """
    Monday–Thursday → Mon–Fri weekday strip (`forecast_days=5`).
    Friday–Sunday → Fri–Sun weekend strip (`forecast_days=3`).
    """
    local = _as_local(when)
    weekday = local.weekday()  # Mon=0
    if weekday < 4:
        start = local.date() - timedelta(days=weekday)
        return start, 5, "weekday"
    start = local.date() - timedelta(days=weekday - 4)
    return start, 3, "weekend"


def parse_downtown_daily(
    data: Dict[str, Any],
    *,
    kind: str,
    forecast_days: int,
) -> DowntownForecast:
    """Parse downtown daily JSON into an X strip. Soft on bad payloads."""
    daily = data.get("daily") or {}
    times = daily.get("time") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    codes = daily.get("weather_code") or []
    if not times:
        return DowntownForecast(
            ok=False,
            kind=kind,
            forecast_days=forecast_days,
            error="Open-Meteo JSON missing daily",
        )
    days: List[ForecastDay] = []
    for i, raw in enumerate(times[:forecast_days]):
        if not isinstance(raw, str) or len(raw) < 10:
            continue
        try:
            day = date.fromisoformat(raw[:10])
        except ValueError:
            continue
        code = _intish(codes[i]) if i < len(codes) else None
        days.append(
            ForecastDay(
                date=day,
                weekday_short=_WEEKDAY_SHORT[day.weekday()],
                high_f=_intish(highs[i]) if i < len(highs) else None,
                low_f=_intish(lows[i]) if i < len(lows) else None,
                condition=condition_word(code),
                weather_code=code,
            )
        )
    if not days:
        return DowntownForecast(
            ok=False,
            kind=kind,
            forecast_days=forecast_days,
            error="Open-Meteo daily times unreadable",
        )
    return DowntownForecast(
        ok=True,
        kind=kind,
        forecast_days=forecast_days,
        start_date=days[0].date,
        days=days,
    )


def _open_meteo_json(
    params: Dict[str, Any],
    *,
    timeout: float,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        import requests
    except ImportError:
        return None, "requests not installed"
    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — seed; any failure is a skip
        return None, str(exc)
    if resp.status_code >= 400:
        return None, f"Open-Meteo HTTP {resp.status_code}"
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return None, f"Open-Meteo JSON: {exc}"
    if not isinstance(data, dict):
        return None, "Open-Meteo returned a non-object"
    return data, None


def fetch_inland_home_weather(
    *,
    when: Optional[datetime] = None,
    timeout: float = 12.0,
) -> WeatherSeed:
    """GET inland-home (zip 92128) hourly + sunrise. Toast path. Never raises."""
    pull = _as_local(when) if when is not None else datetime.now(_tz())
    day = pull.date().isoformat()
    params = {
        "latitude": INLAND_HOME_LAT,
        "longitude": INLAND_HOME_LON,
        "hourly": ",".join(HOURLY_FIELDS),
        "daily": ",".join(DAILY_FIELDS),
        "temperature_unit": "fahrenheit",
        "timezone": SAN_DIEGO_TZ,
        "start_date": day,
        "end_date": day,
    }
    data, error = _open_meteo_json(params, timeout=timeout)
    if error:
        return WeatherSeed(
            ok=False,
            error=error,
            location=INLAND_HOME_LOCATION,
            use=USE_TOAST,
        )
    assert data is not None
    return parse_open_meteo(data, when=pull)


# Back-compat name: toast/inland path only, never downtown.
fetch_san_diego_weather = fetch_inland_home_weather


def fetch_downtown_x_forecast(
    *,
    when: Optional[datetime] = None,
    timeout: float = 12.0,
) -> DowntownForecast:
    """GET downtown daily high/low + code for the X strip. Never raises."""
    pull = _as_local(when) if when is not None else datetime.now(_tz())
    start, forecast_days, kind = x_forecast_window(pull)
    end = start + timedelta(days=forecast_days - 1)
    params = {
        "latitude": DOWNTOWN_LAT,
        "longitude": DOWNTOWN_LON,
        "daily": ",".join(X_FORECAST_DAILY_FIELDS),
        "temperature_unit": "fahrenheit",
        "timezone": SAN_DIEGO_TZ,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    data, error = _open_meteo_json(params, timeout=timeout)
    if error:
        return DowntownForecast(
            ok=False,
            kind=kind,
            forecast_days=forecast_days,
            start_date=start,
            error=error,
        )
    assert data is not None
    return parse_downtown_daily(
        data, kind=kind, forecast_days=forecast_days
    )


def skipped_morning_weather(
    *,
    when: Optional[datetime] = None,
    error: str = "--no-weather",
) -> Tuple[WeatherSeed, DowntownForecast]:
    """Both seeds skipped (offline / tests)."""
    pull = _as_local(when) if when is not None else datetime.now(_tz())
    start, forecast_days, kind = x_forecast_window(pull)
    inland = WeatherSeed(
        ok=False,
        error=error,
        location=INLAND_HOME_LOCATION,
        use=USE_TOAST,
    )
    downtown = DowntownForecast(
        ok=False,
        kind=kind,
        forecast_days=forecast_days,
        start_date=start,
        error=error,
    )
    return inland, downtown


def fetch_morning_weather(
    *,
    when: Optional[datetime] = None,
    timeout: float = 12.0,
) -> Tuple[WeatherSeed, DowntownForecast]:
    """Inland toast seed + downtown X strip. Never raises. One toast only."""
    return (
        fetch_inland_home_weather(when=when, timeout=timeout),
        fetch_downtown_x_forecast(when=when, timeout=timeout),
    )


def weekday_vibe(weekday_name: str) -> str:
    return WEEKDAY_VIBES.get(weekday_name, "ordinary San Diego morning")
