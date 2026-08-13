from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    lat: float
    lon: float
    elevation: float | None = None
    provider: str
    station_code: str
    external_id: str | None = None
    country: str
    region: str | None = None
    active: bool


class ObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    resolution: str = "hourly"
    swe_mm: float | None = None
    snow_depth_cm: float | None = None
    snowfall_cm: float | None = None
    temperature_c: float | None = None
    precipitation_mm: float | None = None
    wind_speed_ms: float | None = None
    humidity: float | None = None
    quality_flag: str | None = None


class CurrentObservationOut(ObservationOut):
    """Latest reading with station identity for app convenience."""

    station_id: str
    name: str
    provider: str
    station_code: str


class StationListOut(BaseModel):
    items: list[StationOut]
    total: int
    limit: int
    offset: int
