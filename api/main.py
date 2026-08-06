from fastapi import FastAPI

from api.middleware.rate_limit import RateLimitMiddleware
from api.routers import map as map_router
from api.routers import stations as stations_router

app = FastAPI(
    title="Snow Observations Network API",
    version="0.1.0",
    description="Open standardized API for global snowpack observations.",
)

app.add_middleware(RateLimitMiddleware)
app.include_router(stations_router.router)
app.include_router(map_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "son-api"}
