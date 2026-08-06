# SON Architecture (Phase 1)

## Goal

Ingest snow observations from NRCS AWDB and BC ASWS, normalize to metric units, store in PostGIS, and expose a versioned HTTP API.

## Services

| Service | Role |
|---------|------|
| `postgres` (`postgis/postgis:16-3.4`) | Canonical store |
| `redis` | Rate limits + map cache |
| `api` | FastAPI `/v1` |
| `celery-worker` | Ingestion jobs |
| `celery-beat` | Hourly schedule (`:05`) |

## Station IDs

Public: `SON-{CC}-{PROVIDER}-{CODE}`

Examples:

- `SON-US-NRCS-301`
- `SON-CA-BCASWS-2F05P`

Provider triplets are stored as `external_id` for client migration (`301:CA:SNTL`, `2F05P:BC:ASWS`).

## Units

API and database use metric:

- `swe_mm`
- `snow_depth_cm`
- `temperature_c`
- `precipitation_mm`
- `wind_speed_ms`

NRCS imperial values are converted on ingest.

## Raw archive

Every provider download is written under:

`storage/raw/YYYY/MM/DD/{provider}/...`

## Deferred (not Phase 1)

- MinIO / S3 object storage
- Caddy, Prometheus, Grafana
- SON Explorer web map
- Flutter / SnoTel Mapper integration
- Europe / Japan / satellite providers
- Climatology and ML forecasts

## Attribution

- USDA NRCS AWDB / SNOTEL
- British Columbia ASWS under the Open Government Licence – British Columbia
