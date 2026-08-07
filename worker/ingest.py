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

    # Postgres binds max 65535 params; ~10 columns/row → keep batches under ~5000
    batch_rows = 500
    inserted = 0
    for i in range(0, len(rows), batch_rows):
        chunk = rows[i : i + batch_rows]
        stmt = insert(Observation).values(chunk)
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
        inserted += len(chunk)
    db.commit()
    return inserted


def _sntl_triplets_from_db(db: Session, *, max_stations: int | None) -> list[str]:
    rows = db.scalars(
        select(Station)
        .where(
            Station.provider_id == "NRCS",
            Station.active.is_(True),
            Station.external_id.is_not(None),
            Station.external_id.like("%:SNTL"),
        )
        .order_by(Station.id)
    ).all()
    triplets = [s.external_id for s in rows if s.external_id]
    # Keep Adin Mtn first when capping / for easier smoke checks
    priority = "301:CA:SNTL"
    if priority in triplets:
        triplets = [priority] + [t for t in triplets if t != priority]
    if max_stations is None:
        return triplets
    return triplets[:max_stations]


def ingest_nrcs(
    *,
    hours: int = 48,
    max_stations: int | None = None,
    refresh_stations: bool = False,
) -> dict:
    """Ingest NRCS observations for active SNTL stations only.

    Hourly cadence uses hours=48 (overlap for gap fill). Use
    ``ingest_nrcs_backfill`` (or hours=168) for a 7-day historical pull.
    ``max_stations=None`` means all active SNTL triplets in Postgres.
    """
    provider = NrcsProvider(timeout=180.0, batch_size=5)
    db = SessionLocal()
    try:
        n_stations = 0
        if refresh_stations:
            stations = provider.get_stations()
            n_stations = upsert_stations(db, stations)

        triplets = _sntl_triplets_from_db(db, max_stations=max_stations)
        if not triplets:
            # Cold start: fetch catalog, then select SNTL
            stations = provider.get_stations()
            n_stations = upsert_stations(db, stations)
            triplets = [
                s.external_id
                for s in stations
                if s.active and s.external_id and s.external_id.endswith(":SNTL")
            ]
            if "301:CA:SNTL" in triplets:
                triplets = ["301:CA:SNTL"] + [t for t in triplets if t != "301:CA:SNTL"]
            if max_stations is not None:
                triplets = triplets[:max_stations]

        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        # Upsert in chunks so a mid-run failure keeps earlier progress
        chunk_size = 50
        n_obs = 0
        for i in range(0, len(triplets), chunk_size):
            chunk = triplets[i : i + chunk_size]
            observations = provider.get_observations(
                start=start, end=end, station_triplets=chunk
            )
            n_obs += upsert_observations(db, observations)
            logger.info(
                "NRCS SNTL progress %d/%d stations, observations so far %d",
                min(i + chunk_size, len(triplets)),
                len(triplets),
                n_obs,
            )
        invalidate_map_cache()
        return {
            "provider": "NRCS",
            "network": "SNTL",
            "stations": n_stations,
            "triplets": len(triplets),
            "hours": hours,
            "observations": n_obs,
        }
    finally:
        provider.close()
        db.close()


def ingest_nrcs_backfill(*, max_stations: int | None = None) -> dict:
    """One-time / on-demand 7-day SNTL observation backfill from AWDB."""
    return ingest_nrcs(hours=168, max_stations=max_stations, refresh_stations=False)


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
    """Hourly job: NRCS/SNTL last 48h (upsert). BC deferred until networking is reliable."""
    results: dict = {}
    try:
        results["nrcs"] = ingest_nrcs(hours=48, max_stations=None)
        logger.info("Ingest nrcs ok: %s", results["nrcs"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingest nrcs failed")
        results["nrcs"] = {"error": str(exc)}
    return results
