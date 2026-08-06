from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from providers.base import NormalizedObservation, NormalizedStation
from providers.bc_asws.csv_parser import parse_bc_asws_csv
from providers.raw_archive import archive_raw
from son_core.config import get_settings

CSV_BASE = "https://www.env.gov.bc.ca/wsd/data_searches/snow/asws/data"
PARAMS = ("SW", "SD", "PC", "TA")
SEED_PATH = Path(__file__).with_name("stations_seed.json")


class BcAswsProvider:
    provider_id = "BCASWS"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        settings = get_settings()
        self._client = client or httpx.Client(
            timeout=120.0,
            headers={"User-Agent": settings.son_user_agent},
            follow_redirects=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_stations(self) -> list[NormalizedStation]:
        seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        stations: list[NormalizedStation] = []
        for row in seed:
            code = str(row["station_code"]).strip()
            stations.append(
                NormalizedStation(
                    provider_id=self.provider_id,
                    station_code=code,
                    external_id=f"{code}:BC:ASWS",
                    name=str(row["name"]),
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    elevation_m=(
                        float(row["elevation_m"]) if row.get("elevation_m") is not None else None
                    ),
                    country="CA",
                    region="BC",
                    active=bool(row.get("active", True)),
                )
            )
        return stations

    def get_observations(
        self,
        *,
        start: datetime,
        end: datetime,
        station_codes: list[str] | None = None,
    ) -> list[NormalizedObservation]:
        matrices = {}
        for param in PARAMS:
            resp = self._client.get(f"{CSV_BASE}/{param}.csv")
            resp.raise_for_status()
            archive_raw(self.provider_id, f"{param}.csv", resp.text)
            matrices[param] = parse_bc_asws_csv(resp.text)

        allow = set(station_codes) if station_codes else None
        # Union of all timestamps/stations
        station_ids: set[str] = set()
        for matrix in matrices.values():
            station_ids.update(matrix.values.keys())
        if allow is not None:
            station_ids &= allow

        by_key: dict[tuple[str, datetime], NormalizedObservation] = {}
        for station_id in station_ids:
            timestamps: set[datetime] = set()
            for matrix in matrices.values():
                timestamps.update(matrix.values.get(station_id, {}).keys())
            for ts in timestamps:
                if ts < start or ts > end:
                    continue
                key = (station_id, ts)
                obs = NormalizedObservation(
                    provider_id=self.provider_id,
                    station_code=station_id,
                    timestamp=ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc),
                    swe_mm=matrices["SW"].values.get(station_id, {}).get(ts),
                    snow_depth_cm=matrices["SD"].values.get(station_id, {}).get(ts),
                    precipitation_mm=matrices["PC"].values.get(station_id, {}).get(ts),
                    temperature_c=matrices["TA"].values.get(station_id, {}).get(ts),
                )
                by_key[key] = obs
        return list(by_key.values())
