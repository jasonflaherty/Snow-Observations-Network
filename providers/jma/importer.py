from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from providers.base import NormalizedObservation, NormalizedStation
from providers.jma.parser import (
    PROVIDER_ID,
    iter_hourly_jst_stamps,
    jst_stamp_to_utc,
    parse_amedastable,
    parse_map_json,
)
from providers.raw_archive import archive_raw
from son_core.config import get_settings

logger = logging.getLogger(__name__)

BOSAI_BASE = "https://www.jma.go.jp/bosai/amedas"
AMEDAS_TABLE_URL = f"{BOSAI_BASE}/const/amedastable.json"
LATEST_TIME_URL = f"{BOSAI_BASE}/data/latest_time.txt"
MAP_URL = f"{BOSAI_BASE}/data/map/{{stamp}}.json"


class JmaProvider:
    provider_id = PROVIDER_ID

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        timeout: float = 120.0,
    ) -> None:
        self._owns_client = client is None
        settings = get_settings()
        self._client = client or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": settings.son_user_agent},
            follow_redirects=True,
        )
        self._snow_codes: set[str] | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_stations(self) -> list[NormalizedStation]:
        resp = self._client.get(AMEDAS_TABLE_URL)
        resp.raise_for_status()
        archive_raw(self.provider_id, "amedastable.json", resp.text)
        payload: dict[str, Any] = resp.json()
        stations = parse_amedastable(payload)
        self._snow_codes = {s.station_code for s in stations if s.active}
        return stations

    def _snow_station_codes(self) -> set[str]:
        if self._snow_codes is None:
            self.get_stations()
        assert self._snow_codes is not None
        return self._snow_codes

    def get_latest_time(self) -> datetime:
        resp = self._client.get(LATEST_TIME_URL)
        resp.raise_for_status()
        archive_raw(self.provider_id, "latest_time.txt", resp.text)
        text = resp.text.strip()
        # ISO like 2026-08-09T00:40:00+09:00
        return datetime.fromisoformat(text).astimezone(timezone.utc)

    def get_observations(
        self,
        *,
        start: datetime,
        end: datetime,
        station_codes: list[str] | None = None,
    ) -> list[NormalizedObservation]:
        snow_codes = self._snow_station_codes()
        if station_codes is not None:
            allow = snow_codes & set(station_codes)
        else:
            allow = snow_codes
        if not allow:
            return []

        stamps = iter_hourly_jst_stamps(start, end)
        observations: list[NormalizedObservation] = []
        for stamp in stamps:
            url = MAP_URL.format(stamp=stamp)
            try:
                resp = self._client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError:
                logger.warning("JMA map fetch failed for %s", stamp, exc_info=True)
                continue
            archive_raw(self.provider_id, f"map_{stamp}.json", resp.text)
            payload: dict[str, Any] = resp.json()
            ts = jst_stamp_to_utc(stamp)
            observations.extend(
                parse_map_json(payload, timestamp=ts, station_codes=allow)
            )
        return observations
