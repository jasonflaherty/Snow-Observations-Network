# SON Architecture (Phase 1)

## Goal

Ingest snow observations from NRCS AWDB, BC ASWS, and JMA AMeDAS, normalize to metric units, store in PostGIS, and expose a versioned HTTP API.

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
- `SON-JP-JMA-11016`

Provider triplets are stored as `external_id` for client migration (`301:CA:SNTL`, `2F05P:BC:ASWS`). JMA uses the AMeDAS station code as `external_id`.

## Units

API and database use metric:

- `swe_mm`
- `snow_depth_cm`
- `temperature_c`
- `precipitation_mm`
- `wind_speed_ms`

NRCS imperial values are converted on ingest. JMA AMeDAS values are already metric (no SWE).

## Raw archive

Every provider download is written under:

`storage/raw/YYYY/MM/DD/{provider}/...`

## Deferred (not Phase 1)

- MinIO / S3 object storage
- Prometheus, Grafana
- Flutter / SnoTel Mapper integration
- Europe / satellite providers
- Climatology and ML forecasts

Explorer map UI: [`web/`](../web/) on GitHub Pages.

## Attribution

- USDA NRCS AWDB / SNOTEL
- British Columbia ASWS under the Open Government Licence – British Columbia
- Japan Meteorological Agency (JMA) AMeDAS
