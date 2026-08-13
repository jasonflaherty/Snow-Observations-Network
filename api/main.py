from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware.rate_limit import RateLimitMiddleware
from api.routers import map as map_router
from api.routers import stations as stations_router
from son_core import __version__
from son_core.config import get_settings

settings = get_settings()
cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app = FastAPI(
    title="Snow Observations Network API",
    version=__version__,
    description="Open standardized API for global snowpack observations.",
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(stations_router.router)
app.include_router(map_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "son-api", "version": __version__}
