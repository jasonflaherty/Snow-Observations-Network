from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Observation, Station
from database.session import get_db
from worker.cache import get_map_cache, set_map_cache

router = APIRouter(prefix="/v1/map", tags=["map"])


def _network_code(st: Station) -> str | None:
    """AWDB-style network from external_id (e.g. 301:CA:SNTL → SNTL)."""
    if not st.external_id:
        return None
    parts = st.external_id.split(":")
    if len(parts) >= 3:
        return parts[-1].upper()
    return None


@router.get("/stations")
def map_stations(db: Session = Depends(get_db)) -> dict:
    cached = get_map_cache()
    if cached is not None:
        return cached

    stations = db.scalars(select(Station).where(Station.active.is_(True))).all()
    # Latest observation per station via distinct-on style subquery in Python for MVP
    features = []
    for st in stations:
        obs = db.scalars(
            select(Observation)
            .where(Observation.station_id == st.id)
            .order_by(Observation.timestamp.desc())
            .limit(1)
        ).first()
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [st.longitude, st.latitude],
                },
                "properties": {
                    "id": st.id,
                    "name": st.name,
                    "provider": st.provider_id,
                    "network": _network_code(st),
                    "external_id": st.external_id,
                    "elevation_m": st.elevation_m,
                    "swe_mm": obs.swe_mm if obs else None,
                    "snow_depth_cm": obs.snow_depth_cm if obs else None,
                    "temperature_c": obs.temperature_c if obs else None,
                    "observed_at": obs.timestamp.isoformat() if obs else None,
                },
            }
        )

    payload = {"type": "FeatureCollection", "features": features}
    set_map_cache(payload)
    return payload
