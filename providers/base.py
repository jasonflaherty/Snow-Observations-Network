from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class NormalizedStation:
    provider_id: str
    station_code: str
    external_id: str
    name: str
    latitude: float
    longitude: float
    elevation_m: float | None
    country: str
    region: str | None
    active: bool


@dataclass
class NormalizedObservation:
    provider_id: str
    station_code: str
    timestamp: datetime
    swe_mm: float | None = None
    snow_depth_cm: float | None = None
    snowfall_cm: float | None = None
    temperature_c: float | None = None
    precipitation_mm: float | None = None
    wind_speed_ms: float | None = None
    humidity: float | None = None
    quality_flag: str | None = None


class SnowProvider(Protocol):
    provider_id: str

    def get_stations(self) -> list[NormalizedStation]:
        ...

    def get_observations(
        self,
        *,
        start: datetime,
        end: datetime,
        station_codes: list[str] | None = None,
    ) -> list[NormalizedObservation]:
        ...
