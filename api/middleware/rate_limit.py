from __future__ import annotations

import time

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from son_core.config import get_settings
from worker.cache import get_redis


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/health", "/docs", "/openapi.json", "/redoc"}:
            return await call_next(request)

        settings = get_settings()
        api_key = request.headers.get("X-API-Key")
        keys = {
            settings.son_free_key: ("free", settings.anon_rate_limit_per_day * 5),
            settings.son_research_key: ("research", settings.anon_rate_limit_per_day * 20),
            settings.son_pro_key: ("pro", settings.anon_rate_limit_per_day * 100),
        }

        if api_key and api_key in keys:
            tier, limit = keys[api_key]
            identity = f"key:{tier}"
        else:
            if api_key:
                raise HTTPException(status_code=401, detail="Invalid API key")
            client = request.client.host if request.client else "unknown"
            identity = f"anon:{client}"
            limit = settings.anon_rate_limit_per_day

        day = time.strftime("%Y%m%d", time.gmtime())
        redis_key = f"son:ratelimit:{day}:{identity}"
        try:
            redis = get_redis()
            count = redis.incr(redis_key)
            if count == 1:
                redis.expire(redis_key, 60 * 60 * 48)
            if count > limit:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
        except HTTPException:
            raise
        except Exception:
            # Fail open if Redis is temporarily unavailable
            pass

        return await call_next(request)
