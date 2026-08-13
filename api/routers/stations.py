from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.schemas import (
    CurrentObservationOut,
    ObservationOut,
    StationListOut,
    StationOut,
)
from database.models import Observation, Station
from database.session import get_db

router = APIRouter(prefix="/v1", tags=["stations"])


def _to_station(st: Station) -> StationOut:
    return StationOut(
        id=st.id,
        name=st.name,
        lat=st.latitude,
        lon=st.longitude,
        elevation=st.elevation_m,
        provider=st.provider_id,
        station_code=st.station_code,
        external_id=st.external_id,
        country=st.country,
        region=st.region,
        active=st.active,
    )


def _to_current(st: Station, obs: Observation) -> CurrentObservationOut:
    return CurrentObservationOut(
        station_id=st.id,
        name=st.name,
        provider=st.provider_id,
        station_code=st.station_code,
        timestamp=obs.timestamp,
        resolution=obs.resolution,
        swe_mm=obs.swe_mm,
        snow_depth_cm=obs.snow_depth_cm,
        snowfall_cm=obs.snowfall_cm,
        temperature_c=obs.temperature_c,
        precipitation_mm=obs.precipitation_mm,
        wind_speed_ms=obs.wind_speed_ms,
        humidity=obs.humidity,
        quality_flag=obs.quality_flag,
    )


@router.get("/stations", response_model=StationListOut)
def list_stations(
    provider: str | None = None,
    country: str | None = None,
    active: bool | None = True,
    bbox: str | None = Query(
        default=None, description="min_lon,min_lat,max_lon,max_lat"
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> StationListOut:
    stmt = select(Station)
    count_stmt = select(func.count()).select_from(Station)

    if provider:
        stmt = stmt.where(Station.provider_id == provider.upper())
        count_stmt = count_stmt.where(Station.provider_id == provider.upper())
    if country:
        stmt = stmt.where(Station.country == country.upper())
        count_stmt = count_stmt.where(Station.country == country.upper())
    if active is not None:
        stmt = stmt.where(Station.active.is_(active))
        count_stmt = count_stmt.where(Station.active.is_(active))
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = [float(x) for x in bbox.split(",")]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid bbox") from exc
        stmt = stmt.where(
            Station.longitude >= min_lon,
            Station.longitude <= max_lon,
            Station.latitude >= min_lat,
            Station.latitude <= max_lat,
        )
        count_stmt = count_stmt.where(
            Station.longitude >= min_lon,
            Station.longitude <= max_lon,
            Station.latitude >= min_lat,
            Station.latitude <= max_lat,
        )

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Station.name).limit(limit).offset(offset)).all()
    return StationListOut(
        items=[_to_station(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stations/{station_id}", response_model=StationOut)
def get_station(station_id: str, db: Session = Depends(get_db)) -> StationOut:
    st = db.get(Station, station_id)
    if not st:
        raise HTTPException(status_code=404, detail="Station not found")
    return _to_station(st)


@router.get("/stations/{station_id}/current", response_model=CurrentObservationOut)
def get_current(station_id: str, db: Session = Depends(get_db)) -> CurrentObservationOut:
    st = db.get(Station, station_id)
    if not st:
        raise HTTPException(status_code=404, detail="Station not found")
    # Prefer latest hourly; fall back to daily if hourly not yet ingested
    obs = db.scalars(
        select(Observation)
        .where(
            Observation.station_id == station_id,
            Observation.resolution == "hourly",
        )
        .order_by(Observation.timestamp.desc())
        .limit(1)
    ).first()
    if not obs:
        obs = db.scalars(
            select(Observation)
            .where(Observation.station_id == station_id)
            .order_by(Observation.timestamp.desc())
            .limit(1)
        ).first()
    if not obs:
        raise HTTPException(status_code=404, detail="No observations")
    return _to_current(st, obs)


@router.get("/stations/{station_id}/observations", response_model=list[ObservationOut])
def get_observations(
    station_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
    resolution: str | None = Query(
        default=None,
        description="hourly | daily. Omit for both. Hourly retained ~72h; daily up to ~1y.",
    ),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[ObservationOut]:
    if not db.get(Station, station_id):
        raise HTTPException(status_code=404, detail="Station not found")
    if resolution is not None:
        resolution = resolution.lower()
        if resolution not in {"hourly", "daily"}:
            raise HTTPException(
                status_code=400, detail="resolution must be hourly or daily"
            )
    stmt = select(Observation).where(Observation.station_id == station_id)
    if resolution:
        stmt = stmt.where(Observation.resolution == resolution)
    if start:
        stmt = stmt.where(Observation.timestamp >= start)
    if end:
        stmt = stmt.where(Observation.timestamp <= end)
    rows = db.scalars(stmt.order_by(Observation.timestamp.asc()).limit(limit)).all()
    return [ObservationOut.model_validate(r) for r in rows]
