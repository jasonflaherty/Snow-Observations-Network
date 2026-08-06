from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from database.models import Observation, Station
from database.session import SessionLocal
from providers.bc_asws.importer import BcAswsProvider
from providers.nrcs.importer import NrcsProvider
from son_core.ids import make_son_id
from worker.cache import invalidate_map_cache

logger = logging.getLogger(__name__)


def upsert_stations(db: Session, stations) -> int:
    count = 0
    for s in stations:
        son_id = make_son_id(s.country, s.provider_id, s.station_code)
        geom = WKTElement(f"POINT({s.longitude} {s.latitude})", srid=4326)
        existing = db.get(Station, son_id)
        if existing is None:
            db.add(
                Station(
                    id=son_id,
                    provider_id=s.provider_id,
                    station_code=s.station_code,
                    external_id=s.external_id,
                    name=s.name,
                    latitude=s.latitude,
                    longitude=s.longitude,
                    elevation_m=s.elevation_m,
                    country=s.country,
                    region=s.region,
                    active=s.active,
                    geom=geom,
                )
            )
        else:
            existing.external_id = s.external_id
            existing.name = s.name
            existing.latitude = s.latitude
            existing.longitude = s.longitude
            existing.elevation_m = s.elevation_m
            existing.region = s.region
            existing.active = s.active
            existing.geom = geom
        count += 1
    db.commit()
    return count


def upsert_observations(db: Session, observations) -> int:
    if not observations:
        return 0
    # Map provider+code -> son id
    codes = {(o.provider_id, o.station_code) for o in observations}
    stations = db.scalars(
        select(Station).where(
            Station.provider_id.in_({c[0] for c in codes}),
            Station.station_code.in_({c[1] for c in codes}),
        )
    ).all()
    lookup = {(st.provider_id, st.station_code): st.id for st in stations}

    rows = []
    for o in observations:
        station_id = lookup.get((o.provider_id, o.station_code))
        if not station_id:
            continue
        rows.append(
            {
                "station_id": station_id,
                "timestamp": o.timestamp,
                "swe_mm": o.swe_mm,
                "snow_depth_cm": o.snow_depth_cm,
                "snowfall_cm": o.snowfall_cm,
                "temperature_c": o.temperature_c,
                "precipitation_mm": o.precipitation_mm,
                "wind_speed_ms": o.wind_speed_ms,
                "humidity": o.humidity,
                "quality_flag": o.quality_flag,
            }
        )
    if not rows:
        return 0

    stmt = insert(Observation).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_station_timestamp",
        set_={
            "swe_mm": stmt.excluded.swe_mm,
            "snow_depth_cm": stmt.excluded.snow_depth_cm,
            "snowfall_cm": stmt.excluded.snowfall_cm,
            "temperature_c": stmt.excluded.temperature_c,
            "precipitation_mm": stmt.excluded.precipitation_mm,
            "wind_speed_ms": stmt.excluded.wind_speed_ms,
            "humidity": stmt.excluded.humidity,
            "quality_flag": stmt.excluded.quality_flag,
        },
    )
    db.execute(stmt)
    db.commit()
    return len(rows)


def ingest_nrcs(*, hours: int = 72) -> dict:
    provider = NrcsProvider()
    db = SessionLocal()
    try:
        stations = provider.get_stations()
        n_stations = upsert_stations(db, stations)
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        # Prefer active SNTL triplets for recent data; batch subset for MVP reliability
        triplets = [s.external_id for s in stations if s.active and s.external_id][:200]
        observations = provider.get_observations(
            start=start, end=end, station_triplets=triplets
        )
        n_obs = upsert_observations(db, observations)
        invalidate_map_cache()
        return {"provider": "NRCS", "stations": n_stations, "observations": n_obs}
    finally:
        provider.close()
        db.close()


def ingest_bc_asws(*, hours: int = 72) -> dict:
    provider = BcAswsProvider()
    db = SessionLocal()
    try:
        stations = provider.get_stations()
        n_stations = upsert_stations(db, stations)
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        observations = provider.get_observations(start=start, end=end)
        n_obs = upsert_observations(db, observations)
        invalidate_map_cache()
        return {"provider": "BCASWS", "stations": n_stations, "observations": n_obs}
    finally:
        provider.close()
        db.close()


def ingest_all() -> dict:
    results = {}
    for name, fn in (("nrcs", ingest_nrcs), ("bc_asws", ingest_bc_asws)):
        try:
            results[name] = fn()
            logger.info("Ingest %s ok: %s", name, results[name])
        except Exception as exc:  # noqa: BLE001 — keep other providers running
            logger.exception("Ingest %s failed", name)
            results[name] = {"error": str(exc)}
    return results
