from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from providers.base import NormalizedObservation, NormalizedStation
from providers.raw_archive import archive_raw
from son_core.config import get_settings
from son_core.units import fahrenheit_to_celsius, inches_to_cm, inches_to_mm

AWDB_BASE = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"
NETWORKS = {"SNTL", "SCAN", "MSTL"}
logger = logging.getLogger(__name__)


class NrcsProvider:
    provider_id = "NRCS"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        timeout: float = 180.0,
        batch_size: int = 5,
    ) -> None:
        self._owns_client = client is None
        self.batch_size = batch_size
        settings = get_settings()
        self._client = client or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": settings.son_user_agent},
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_stations(self) -> list[NormalizedStation]:
        resp = self._client.get(
            f"{AWDB_BASE}/stations",
            params={
                "stationTriplets": "*:*:*",
                "activeOnly": "true",
                "returnStationElements": "false",
            },
        )
        resp.raise_for_status()
        archive_raw(self.provider_id, "stations.json", resp.text)
        payload = resp.json()
        stations: list[NormalizedStation] = []
        for row in payload:
            network = (row.get("networkCode") or "").upper()
            if network not in NETWORKS:
                continue
            station_id = str(row.get("stationId") or "").strip()
            state = str(row.get("stateCode") or "").strip().upper()
            if not station_id or not state:
                continue
            lat = row.get("latitude")
            lon = row.get("longitude")
            if lat is None or lon is None:
                continue
            elev_ft = row.get("elevation")
            elev_m = float(elev_ft) * 0.3048 if elev_ft is not None else None
            stations.append(
                NormalizedStation(
                    provider_id=self.provider_id,
                    station_code=station_id,
                    external_id=f"{station_id}:{state}:{network}",
                    name=str(row.get("name") or station_id),
                    latitude=float(lat),
                    longitude=float(lon),
                    elevation_m=elev_m,
                    country="US",
                    region=state,
                    active=bool(row.get("activeFlag", True) in (True, "Y", "y", 1, "1")),
                )
            )
        return stations

    def get_observations(
        self,
        *,
        start: datetime,
        end: datetime,
        station_codes: list[str] | None = None,
        station_triplets: list[str] | None = None,
        duration: str = "HOURLY",
    ) -> list[NormalizedObservation]:
        if not station_triplets and not station_codes:
            return []

        triplets = station_triplets or []
        # If only codes provided, caller should pass triplets; codes alone are ambiguous.
        if not triplets:
            return []

        duration = duration.upper()
        if duration not in {"HOURLY", "DAILY"}:
            raise ValueError("duration must be HOURLY or DAILY")

        observations: list[NormalizedObservation] = []
        batch_size = self.batch_size
        for i in range(0, len(triplets), batch_size):
            batch = triplets[i : i + batch_size]
            observations.extend(
                self._fetch_data_batch(
                    batch, start=start, end=end, duration=duration
                )
            )
        return observations

    def _fetch_data_batch(
        self,
        batch: list[str],
        *,
        start: datetime,
        end: datetime,
        duration: str = "HOURLY",
    ) -> list[NormalizedObservation]:
        """Fetch one AWDB batch; on 5xx, split the batch or skip a single bad station."""
        if not batch:
            return []
        params = {
            "beginDate": _fmt(start, daily=(duration == "DAILY")),
            "endDate": _fmt(end, daily=(duration == "DAILY")),
            "duration": duration,
            "elements": "WTEQ,SNWD,TOBS,PREC",
            "stationTriplets": ",".join(batch),
            "periodRef": "START",
            "returnSuspectData": "false",
        }
        try:
            resp = self._client.get(f"{AWDB_BASE}/data", params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status >= 500 and len(batch) > 1:
                mid = len(batch) // 2
                logger.warning(
                    "AWDB %s for %d stations; splitting batch", status, len(batch)
                )
                return self._fetch_data_batch(
                    batch[:mid], start=start, end=end, duration=duration
                ) + self._fetch_data_batch(
                    batch[mid:], start=start, end=end, duration=duration
                )
            if status >= 500 and len(batch) == 1:
                logger.warning("AWDB %s for station %s; skipping", status, batch[0])
                return []
            raise
        except httpx.TimeoutException:
            if len(batch) > 1:
                mid = len(batch) // 2
                logger.warning("AWDB timeout for %d stations; splitting", len(batch))
                return self._fetch_data_batch(
                    batch[:mid], start=start, end=end, duration=duration
                ) + self._fetch_data_batch(
                    batch[mid:], start=start, end=end, duration=duration
                )
            logger.warning("AWDB timeout for station %s; skipping", batch[0])
            return []

        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        archive_raw(
            self.provider_id,
            f"data_{duration.lower()}_{stamp}_{batch[0].replace(':', '_')}.json",
            resp.text,
        )
        resolution = "daily" if duration == "DAILY" else "hourly"
        return _parse_awdb_data(resp.json(), resolution=resolution)


def _fmt(dt: datetime, *, daily: bool = False) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc = dt.astimezone(timezone.utc)
    if daily:
        return utc.strftime("%Y-%m-%d")
    return utc.strftime("%Y-%m-%d %H:%M")


def _parse_awdb_data(
    payload: Any, *, resolution: str = "hourly"
) -> list[NormalizedObservation]:
    """Parse AWDB /data JSON into metric NormalizedObservation rows."""
    by_key: dict[tuple[str, datetime], NormalizedObservation] = {}

    rows = payload if isinstance(payload, list) else []
    for station_block in rows:
        triplet = str(station_block.get("stationTriplet") or "")
        parts = triplet.split(":")
        if len(parts) < 1:
            continue
        station_code = parts[0]
        for element in station_block.get("data") or []:
            code = str(element.get("stationElement", {}).get("elementCode") or "").upper()
            unit = str(element.get("stationElement", {}).get("storedUnitCode") or "").lower()
            for value in element.get("values") or []:
                raw = value.get("value")
                if raw is None or raw == "":
                    continue
                try:
                    num = float(raw)
                except (TypeError, ValueError):
                    continue
                ts = _parse_ts(value.get("date"))
                if ts is None:
                    continue
                key = (station_code, ts)
                obs = by_key.get(key)
                if obs is None:
                    obs = NormalizedObservation(
                        provider_id="NRCS",
                        station_code=station_code,
                        timestamp=ts,
                        resolution=resolution,
                    )
                    by_key[key] = obs
                _apply_element(obs, code, unit, num)
    return list(by_key.values())


def _apply_element(obs: NormalizedObservation, code: str, unit: str, num: float) -> None:
    if code == "WTEQ":
        obs.swe_mm = inches_to_mm(num) if unit in {"in", "inch", "inches"} else num
    elif code == "SNWD":
        obs.snow_depth_cm = inches_to_cm(num) if unit in {"in", "inch", "inches"} else num
    elif code == "TOBS":
        obs.temperature_c = (
            fahrenheit_to_celsius(num) if unit in {"degf", "f", "fahrenheit"} else num
        )
    elif code == "PREC":
        obs.precipitation_mm = inches_to_mm(num) if unit in {"in", "inch", "inches"} else num


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_awdb_data_json(text: str, *, resolution: str = "hourly") -> list[NormalizedObservation]:
    return _parse_awdb_data(json.loads(text), resolution=resolution)
