# Changelog

All notable changes to Snow Observations Network (SON) are documented here.

## [1.0.0] — 2026-08-13

First public release of the Phase 1 data platform.

### Platform

- PostGIS storage with Alembic migrations
- FastAPI `/v1` stations, current, observations, and GeoJSON map endpoints
- Celery beat/worker hourly ingest (`:05` UTC)
- Redis rate limiting and map cache

### Providers

- **NRCS SNOTEL (SNTL)** — USDA AWDB REST (hourly + daily)
- **BC ASWS** — province CSV feeds
- **JMA AMeDAS** — Bosai map JSON (snow-capable stations)

### History tiers

- **Hourly** — last 72 hours (older hourly pruned)
- **Daily** — last 7 days ongoing; up to 1 year via daily backfill
- Observations unique on `(station_id, timestamp, resolution)`

### Explorer

- GitHub Pages map UI with provider layers, search, Metric/US units
- Station modal with current readings and temp / snow-depth chart (72h ↔ 7d)

### Links

- API: https://api.psithurismlabs.com
- Docs: https://api.psithurismlabs.com/docs
- Explorer: https://jasonflaherty.github.io/Snow-Observations-Network/
