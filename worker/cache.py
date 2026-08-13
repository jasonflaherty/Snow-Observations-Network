from __future__ import annotations

import json
from typing import Any

import redis

from son_core.config import get_settings

MAP_CACHE_KEY = "son:cache:map:stations:v2"
MAP_CACHE_TTL_SECONDS = 300


def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


def get_map_cache() -> dict[str, Any] | None:
    try:
        client = get_redis()
        raw = client.get(MAP_CACHE_KEY)
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def set_map_cache(payload: dict[str, Any]) -> None:
    try:
        client = get_redis()
        client.setex(MAP_CACHE_KEY, MAP_CACHE_TTL_SECONDS, json.dumps(payload))
    except Exception:
        return


def invalidate_map_cache() -> None:
    try:
        client = get_redis()
        client.delete(MAP_CACHE_KEY)
    except Exception:
        return
