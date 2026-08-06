from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.schemas import ObservationOut, StationListOut, StationOut
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


@router.get("/stations/{station_id}/current", response_model=ObservationOut)
def get_current(station_id: str, db: Session = Depends(get_db)) -> ObservationOut:
    if not db.get(Station, station_id):
        raise HTTPException(status_code=404, detail="Station not found")
    obs = db.scalars(
        select(Observation)
        .where(Observation.station_id == station_id)
        .order_by(Observation.timestamp.desc())
        .limit(1)
    ).first()
    if not obs:
        raise HTTPException(status_code=404, detail="No observations")
    return ObservationOut.model_validate(obs)


@router.get("/stations/{station_id}/observations", response_model=list[ObservationOut])
def get_observations(
    station_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[ObservationOut]:
    if not db.get(Station, station_id):
        raise HTTPException(status_code=404, detail="Station not found")
    stmt = select(Observation).where(Observation.station_id == station_id)
    if start:
        stmt = stmt.where(Observation.timestamp >= start)
    if end:
        stmt = stmt.where(Observation.timestamp <= end)
    rows = db.scalars(stmt.order_by(Observation.timestamp.asc()).limit(limit)).all()
    return [ObservationOut.model_validate(r) for r in rows]
