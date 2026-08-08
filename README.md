# Snow Observations Network (SON)

Free, open, standardized API for global snowpack observations.

SON is a **data platform**: ingest snow observations from multiple providers, normalize units, store them in PostGIS, and expose them through a versioned HTTP API.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000
- OpenAPI docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

Trigger an ingest manually (inside the worker container):

```bash
# Hourly-style pull (last 48h, all SNTL) — same as celery-beat
podman-compose exec celery-worker \
  python -c "from worker.ingest import ingest_all; print(ingest_all())"

# One-time 7-day SNTL backfill from AWDB REST, then rely on hourly upserts
podman-compose exec celery-worker \
  python -c "from worker.ingest import ingest_nrcs_backfill; print(ingest_nrcs_backfill())"

# One-time 7-day BC ASWS backfill from province CSVs
podman-compose exec celery-worker \
  python -c "from worker.ingest import ingest_bc_asws_backfill; print(ingest_bc_asws_backfill())"
```

(`docker compose exec ...` works the same if you use Docker instead of Podman.)

## Example endpoints

```bash
curl http://localhost:8000/v1/stations
curl http://localhost:8000/v1/stations/SON-CA-BCASWS-1A01P/current
curl "http://localhost:8000/v1/stations/SON-US-NRCS-301/observations?limit=100"
curl http://localhost:8000/v1/map/stations
```

Optional API key header:

```bash
curl -H "X-API-Key: change-me-free" http://localhost:8000/v1/stations
```

Anonymous clients are limited to 1000 requests/day (Redis-backed).

## Station IDs

`SON-{CC}-{PROVIDER}-{CODE}` — e.g. `SON-US-NRCS-301`, `SON-CA-BCASWS-2F05P`.

## Local tests

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

## Phase 1 providers

| Provider | Source | Cadence |
|----------|--------|---------|
| NRCS SNOTEL (SNTL) | USDA AWDB REST `/stations`, `/data` | Hourly 48h upsert; optional 7-day backfill |
| BC ASWS | Province CSVs (`SW/SD/PC/TA.csv`) + seeded catalog | Hourly 48h upsert; optional 7-day backfill |

See [docs/architecture.md](docs/architecture.md) and [docs/providers.md](docs/providers.md).

## License

MIT — see [LICENSE](LICENSE).

## Attribution

- USDA Natural Resources Conservation Service AWDB / SNOTEL
- Province of British Columbia ASWS (Open Government Licence – British Columbia)
