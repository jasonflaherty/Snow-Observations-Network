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
from providers.jma.importer import JmaProvider
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
                "resolution": getattr(o, "resolution", None) or "hourly",
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

    # Postgres binds max 65535 params; ~11 columns/row → keep batches under ~5000
    batch_rows = 500
    inserted = 0
    for i in range(0, len(rows), batch_rows):
        chunk = rows[i : i + batch_rows]
        stmt = insert(Observation).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_station_timestamp_resolution",
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


def prune_hourly_observations(db: Session, *, keep_hours: int = 72) -> int:
    """Drop hourly rows older than the retention window (daily rows are kept)."""
    from sqlalchemy import delete

    cutoff = datetime.now(timezone.utc) - timedelta(hours=keep_hours)
    result = db.execute(
        delete(Observation).where(
            Observation.resolution == "hourly",
            Observation.timestamp < cutoff,
        )
    )
    db.commit()
    return int(result.rowcount or 0)


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


def _downsample_to_daily(observations) -> list:
    """Keep the last observation per station per UTC calendar day as ``daily``."""
    best: dict[tuple[str, str, object], object] = {}
    for o in observations:
        day = o.timestamp.astimezone(timezone.utc).date()
        key = (o.provider_id, o.station_code, day)
        prev = best.get(key)
        if prev is None or o.timestamp > prev.timestamp:
            best[key] = o
    out = []
    for o in best.values():
        o.resolution = "daily"
        out.append(o)
    return out


def ingest_nrcs(
    *,
    hours: int | None = None,
    days: int | None = None,
    duration: str = "HOURLY",
    max_stations: int | None = None,
    refresh_stations: bool = False,
) -> dict:
    """Ingest NRCS observations for active SNTL stations only.

    ``duration=HOURLY`` (default): last ``hours`` (default 72).
    ``duration=DAILY``: last ``days`` (default 7) of AWDB daily values.
    ``max_stations=None`` means all active SNTL triplets in Postgres.
    """
    duration = duration.upper()
    if duration not in {"HOURLY", "DAILY"}:
        raise ValueError("duration must be HOURLY or DAILY")

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
        if duration == "DAILY":
            window_days = days if days is not None else 7
            start = end - timedelta(days=window_days)
            window_meta: dict = {"days": window_days}
        else:
            window_hours = hours if hours is not None else 72
            start = end - timedelta(hours=window_hours)
            window_meta = {"hours": window_hours}

        # Upsert in chunks so a mid-run failure keeps earlier progress
        chunk_size = 50
        n_obs = 0
        for i in range(0, len(triplets), chunk_size):
            chunk = triplets[i : i + chunk_size]
            observations = provider.get_observations(
                start=start,
                end=end,
                station_triplets=chunk,
                duration=duration,
            )
            n_obs += upsert_observations(db, observations)
            logger.info(
                "NRCS SNTL %s progress %d/%d stations, observations so far %d",
                duration,
                min(i + chunk_size, len(triplets)),
                len(triplets),
                n_obs,
            )
        invalidate_map_cache()
        return {
            "provider": "NRCS",
            "network": "SNTL",
            "duration": duration,
            "stations": n_stations,
            "triplets": len(triplets),
            "observations": n_obs,
            **window_meta,
        }
    finally:
        provider.close()
        db.close()


def ingest_nrcs_daily(*, days: int = 7, max_stations: int | None = None) -> dict:
    """Ongoing daily SNTL pull (default last 7 days)."""
    return ingest_nrcs(
        days=days, duration="DAILY", max_stations=max_stations, refresh_stations=False
    )


def ingest_nrcs_daily_backfill(
    *,
    days: int = 365,
    max_stations: int | None = None,
    chunk_days: int = 30,
) -> dict:
    """One-time / on-demand daily SNTL history (default 1 year), in date chunks."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    provider = NrcsProvider(timeout=180.0, batch_size=5)
    db = SessionLocal()
    try:
        triplets = _sntl_triplets_from_db(db, max_stations=max_stations)
        if not triplets:
            stations = provider.get_stations()
            upsert_stations(db, stations)
            triplets = _sntl_triplets_from_db(db, max_stations=max_stations)

        n_obs = 0
        cursor = start
        station_chunk = 50
        while cursor < end:
            window_end = min(cursor + timedelta(days=chunk_days), end)
            for i in range(0, len(triplets), station_chunk):
                chunk = triplets[i : i + station_chunk]
                observations = provider.get_observations(
                    start=cursor,
                    end=window_end,
                    station_triplets=chunk,
                    duration="DAILY",
                )
                n_obs += upsert_observations(db, observations)
            logger.info(
                "NRCS daily backfill %s → %s, observations so far %d",
                cursor.date(),
                window_end.date(),
                n_obs,
            )
            cursor = window_end
        invalidate_map_cache()
        return {
            "provider": "NRCS",
            "network": "SNTL",
            "duration": "DAILY",
            "days": days,
            "triplets": len(triplets),
            "observations": n_obs,
        }
    finally:
        provider.close()
        db.close()


def ingest_nrcs_backfill(*, max_stations: int | None = None) -> dict:
    """Deprecated alias: prefer ``ingest_nrcs_daily_backfill`` for year history.

    Keeps a 72h hourly refresh for callers that still use this name.
    """
    return ingest_nrcs(hours=72, max_stations=max_stations, refresh_stations=False)


def ingest_bc_asws(*, hours: int = 72) -> dict:
    """Ingest BC ASWS hourly CSVs (SW/SD/PC/TA), upsert last ``hours``.

    Province files already contain the water-year series; we filter locally.
    Hourly retention is 72h (see ``prune_hourly_observations``).
    """
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
        return {
            "provider": "BCASWS",
            "stations": n_stations,
            "hours": hours,
            "observations": n_obs,
        }
    finally:
        provider.close()
        db.close()


def ingest_bc_asws_daily(*, days: int = 7) -> dict:
    """Store last-of-day snapshots from BC ASWS CSVs as ``daily`` rows."""
    provider = BcAswsProvider()
    db = SessionLocal()
    try:
        stations = provider.get_stations()
        n_stations = upsert_stations(db, stations)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        hourly = provider.get_observations(start=start, end=end)
        daily = _downsample_to_daily(hourly)
        n_obs = upsert_observations(db, daily)
        invalidate_map_cache()
        return {
            "provider": "BCASWS",
            "duration": "DAILY",
            "stations": n_stations,
            "days": days,
            "observations": n_obs,
        }
    finally:
        provider.close()
        db.close()


def ingest_bc_asws_daily_backfill(*, days: int = 365) -> dict:
    """On-demand BC daily history from water-year CSVs (up to ~1 year in season)."""
    return ingest_bc_asws_daily(days=days)


def ingest_bc_asws_backfill(*, hours: int = 72) -> dict:
    """On-demand BC ASWS hourly refresh (default 72h retention window)."""
    return ingest_bc_asws(hours=hours)


def ingest_jma(*, hours: int = 72) -> dict:
    """Ingest JMA AMeDAS hourly map snapshots for snow-capable stations."""
    provider = JmaProvider()
    db = SessionLocal()
    try:
        stations = provider.get_stations()
        n_stations = upsert_stations(db, stations)
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        observations = provider.get_observations(start=start, end=end)
        n_obs = upsert_observations(db, observations)
        invalidate_map_cache()
        return {
            "provider": "JMA",
            "stations": n_stations,
            "snow_stations": sum(1 for s in stations if s.active),
            "hours": hours,
            "observations": n_obs,
        }
    finally:
        provider.close()
        db.close()


def ingest_jma_daily(*, days: int = 7) -> dict:
    """Fetch one noon-JST map snapshot per day and store as ``daily``."""
    provider = JmaProvider()
    db = SessionLocal()
    try:
        stations = provider.get_stations()
        n_stations = upsert_stations(db, stations)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        daily = provider.get_observations(start=start, end=end, cadence="daily")
        n_obs = upsert_observations(db, daily)
        invalidate_map_cache()
        return {
            "provider": "JMA",
            "duration": "DAILY",
            "stations": n_stations,
            "days": days,
            "observations": n_obs,
        }
    finally:
        provider.close()
        db.close()


def ingest_jma_backfill(*, hours: int = 72) -> dict:
    """On-demand JMA hourly refresh (default 72h retention window)."""
    return ingest_jma(hours=hours)


def ingest_all() -> dict:
    """Hourly job: 72h hourly upsert + 7d daily upsert + prune older hourly."""
    results: dict = {}
    try:
        results["nrcs_hourly"] = ingest_nrcs(hours=72, max_stations=None)
        logger.info("Ingest nrcs hourly ok: %s", results["nrcs_hourly"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingest nrcs hourly failed")
        results["nrcs_hourly"] = {"error": str(exc)}
    try:
        results["nrcs_daily"] = ingest_nrcs_daily(days=7)
        logger.info("Ingest nrcs daily ok: %s", results["nrcs_daily"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingest nrcs daily failed")
        results["nrcs_daily"] = {"error": str(exc)}
    try:
        results["bc_asws_hourly"] = ingest_bc_asws(hours=72)
        logger.info("Ingest bc_asws hourly ok: %s", results["bc_asws_hourly"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingest bc_asws hourly failed")
        results["bc_asws_hourly"] = {"error": str(exc)}
    try:
        results["bc_asws_daily"] = ingest_bc_asws_daily(days=7)
        logger.info("Ingest bc_asws daily ok: %s", results["bc_asws_daily"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingest bc_asws daily failed")
        results["bc_asws_daily"] = {"error": str(exc)}
    try:
        results["jma_hourly"] = ingest_jma(hours=72)
        logger.info("Ingest jma hourly ok: %s", results["jma_hourly"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingest jma hourly failed")
        results["jma_hourly"] = {"error": str(exc)}
    try:
        results["jma_daily"] = ingest_jma_daily(days=7)
        logger.info("Ingest jma daily ok: %s", results["jma_daily"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingest jma daily failed")
        results["jma_daily"] = {"error": str(exc)}

    db = SessionLocal()
    try:
        pruned = prune_hourly_observations(db, keep_hours=72)
        results["pruned_hourly"] = pruned
        logger.info("Pruned %d hourly observations older than 72h", pruned)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Hourly prune failed")
        results["pruned_hourly"] = {"error": str(exc)}
    finally:
        db.close()
    return results
