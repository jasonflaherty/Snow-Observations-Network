from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from providers.base import NormalizedObservation, NormalizedStation

JST = ZoneInfo("Asia/Tokyo")
PROVIDER_ID = "JMA"

# AMeDAS ``elems`` is an 8-char capability mask; index 5 is snow depth (~330 sites).
SNOW_ELEMS_INDEX = 5


def dms_pair_to_decimal(pair: list[float] | tuple[float, float]) -> float:
    """Convert JMA ``[degrees, minutes]`` (minutes may be fractional) to decimal degrees."""
    degrees = float(pair[0])
    minutes = float(pair[1])
    return degrees + minutes / 60.0


def has_snow_capability(elems: str) -> bool:
    """Return True when the station observes snow depth (``elems[5] == '1'``)."""
    return len(elems) > SNOW_ELEMS_INDEX and elems[SNOW_ELEMS_INDEX] == "1"


def parse_amedas_value(raw: Any) -> float | None:
    """Parse an AMeDAS ``[value, aqc]`` pair; require AQC == 0 and a numeric value."""
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    value, aqc = raw[0], raw[1]
    if aqc != 0:
        return None
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def jst_stamp_to_utc(stamp: str) -> datetime:
    """Parse a map filename stamp ``YYYYMMDDHHMMSS`` (JST) to an aware UTC datetime."""
    local = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=JST)
    return local.astimezone(timezone.utc)


def utc_to_jst_hour_stamp(ts: datetime) -> str:
    """Format an aware datetime as an on-the-hour JST map stamp ``YYYYMMDDHH0000``."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    local = ts.astimezone(JST).replace(minute=0, second=0, microsecond=0)
    return local.strftime("%Y%m%d%H%M%S")


def iter_hourly_jst_stamps(start: datetime, end: datetime) -> list[str]:
    """Hourly on-the-hour JST stamps covering ``[start, end]`` (UTC-aware inputs)."""
    from datetime import timedelta

    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    start_jst = start.astimezone(JST).replace(minute=0, second=0, microsecond=0)
    end_jst = end.astimezone(JST)
    stamps: list[str] = []
    t = start_jst
    while t <= end_jst:
        stamps.append(t.strftime("%Y%m%d%H%M%S"))
        t += timedelta(hours=1)
    return stamps


def parse_amedastable(payload: dict[str, Any]) -> list[NormalizedStation]:
    """Parse ``amedastable.json`` into normalized stations (all sites; snow sites active)."""
    stations: list[NormalizedStation] = []
    for code, row in payload.items():
        if not isinstance(row, dict):
            continue
        lat = row.get("lat")
        lon = row.get("lon")
        if not isinstance(lat, (list, tuple)) or len(lat) < 2:
            continue
        if not isinstance(lon, (list, tuple)) or len(lon) < 2:
            continue
        elems = str(row.get("elems") or "")
        en_name = str(row.get("enName") or "").strip()
        kj_name = str(row.get("kjName") or "").strip()
        name = en_name or kj_name or str(code)
        alt = row.get("alt")
        stations.append(
            NormalizedStation(
                provider_id=PROVIDER_ID,
                station_code=str(code),
                external_id=str(code),
                name=name,
                latitude=dms_pair_to_decimal(lat),
                longitude=dms_pair_to_decimal(lon),
                elevation_m=float(alt) if alt is not None else None,
                country="JP",
                region=None,
                active=has_snow_capability(elems),
            )
        )
    return stations


def parse_map_observation(
    station_code: str,
    row: dict[str, Any],
    *,
    timestamp: datetime,
) -> NormalizedObservation | None:
    """Map one station's AMeDAS snapshot fields to a normalized observation."""
    snow_depth = parse_amedas_value(row.get("snow"))
    snowfall = parse_amedas_value(row.get("snow1h"))
    temperature = parse_amedas_value(row.get("temp"))
    precipitation = parse_amedas_value(row.get("precipitation1h"))
    wind = parse_amedas_value(row.get("wind"))
    humidity = parse_amedas_value(row.get("humidity"))

    if all(
        v is None
        for v in (snow_depth, snowfall, temperature, precipitation, wind, humidity)
    ):
        return None

    quality_flag = None
    snow_raw = row.get("snow")
    if isinstance(snow_raw, (list, tuple)) and len(snow_raw) >= 2:
        quality_flag = str(snow_raw[1])

    return NormalizedObservation(
        provider_id=PROVIDER_ID,
        station_code=station_code,
        timestamp=timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc),
        swe_mm=None,
        snow_depth_cm=snow_depth,
        snowfall_cm=snowfall,
        temperature_c=temperature,
        precipitation_mm=precipitation,
        wind_speed_ms=wind,
        humidity=humidity,
        quality_flag=quality_flag,
    )


def parse_map_json(
    payload: dict[str, Any],
    *,
    timestamp: datetime,
    station_codes: set[str] | None = None,
) -> list[NormalizedObservation]:
    """Parse a nationwide map snapshot into observations for allowed station codes."""
    observations: list[NormalizedObservation] = []
    for code, row in payload.items():
        if station_codes is not None and code not in station_codes:
            continue
        if not isinstance(row, dict):
            continue
        obs = parse_map_observation(code, row, timestamp=timestamp)
        if obs is not None:
            observations.append(obs)
    return observations
