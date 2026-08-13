# Snow Observations Network (SON)

Free, open, standardized API for global snowpack observations.

SON is a **data platform**: ingest snow observations from multiple providers, normalize units, store them in PostGIS, and expose them through a versioned HTTP API.

## Status

**Release [v1.0.0](https://github.com/jasonflaherty/Snow-Observations-Network/releases/tag/v1.0.0)** — Phase 1 platform is production-ready.

| | |
|--|--|
| API | https://api.psithurismlabs.com |
| OpenAPI | https://api.psithurismlabs.com/docs |
| Explorer | https://jasonflaherty.github.io/Snow-Observations-Network/ |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |

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
# Hourly job (72h hourly + 7d daily + prune) — same as celery-beat
podman-compose exec celery-worker \
  python -c "from worker.ingest import ingest_all; print(ingest_all())"

# One-time NRCS daily year lookback (SNTL) — heavy on a small VPS; use tmux
podman-compose exec celery-worker \
  python -c "from worker.ingest import ingest_nrcs_daily_backfill; print(ingest_nrcs_daily_backfill())"

# Optional BC daily year lookback from water-year CSVs
podman-compose exec celery-worker \
  python -c "from worker.ingest import ingest_bc_asws_daily_backfill; print(ingest_bc_asws_daily_backfill())"
```

(`docker compose exec ...` works the same if you use Docker instead of Podman.)

## History tiers

| Resolution | Retention | How |
|------------|-----------|-----|
| `hourly` | Past **72 hours** | Celery ingest; older hourly rows pruned |
| `daily` | Past **7 days** ongoing; up to **1 year** after backfill | NRCS AWDB daily; BC/JMA last-of-day from hourly sources |

```bash
# Last 72h hourly
curl "http://localhost:8000/v1/stations/SON-US-NRCS-301/observations?resolution=hourly&limit=100"

# Last week / year daily
curl "http://localhost:8000/v1/stations/SON-US-NRCS-301/observations?resolution=daily&limit=400"
```

## Example endpoints

```bash
curl http://localhost:8000/v1/stations
curl http://localhost:8000/v1/stations/SON-CA-BCASWS-1A01P/current
curl "http://localhost:8000/v1/stations/SON-US-NRCS-301/observations?resolution=hourly&limit=100"
curl "http://localhost:8000/v1/stations?country=JP"
curl http://localhost:8000/v1/map/stations
```

Optional API key header:

```bash
curl -H "X-API-Key: change-me-free" http://localhost:8000/v1/stations
```

Anonymous clients are limited to 1000 requests/day (Redis-backed).

## Station IDs

`SON-{CC}-{PROVIDER}-{CODE}` — e.g. `SON-US-NRCS-301`, `SON-CA-BCASWS-2F05P`, `SON-JP-JMA-11016`.

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
| NRCS SNOTEL (SNTL) | USDA AWDB REST `/stations`, `/data` | Hourly 72h + daily 7d; optional 1y daily backfill |
| BC ASWS | Province CSVs (`SW/SD/PC/TA.csv`) + seeded catalog | Hourly 72h + daily 7d (last-of-day); optional year daily |
| JMA AMeDAS | Bosai JSON `amedastable` + hourly `map/{stamp}.json` | Hourly 72h + daily 7d (noon JST) |

See [docs/architecture.md](docs/architecture.md) and [docs/providers.md](docs/providers.md).

## Explorer (GitHub Pages)

Static map UI in [`web/`](web/) — markers from `/v1/map/stations`, click opens a modal with `/current`.

Live (after Pages deploy): https://jasonflaherty.github.io/Snow-Observations-Network/

```bash
# local preview
python3 -m http.server 8080 --directory web
# open http://127.0.0.1:8080
```

The API must allow the Pages origin via `CORS_ORIGINS` (defaults include `https://jasonflaherty.github.io`).

## Production (NixiHost 2GB VPS)

See [deploy/nixihost.md](deploy/nixihost.md) for first-time install and **GitHub → VPS** deploys (Actions + `deploy/deploy.sh`):

```bash
docker compose -f docker-compose.prod.yml up -d --build
# later updates on the box:
DEPLOY_REF=main ./deploy/deploy.sh
```

Pushes to `main` (or Actions → Deploy VPS) deploy to the VPS. Feature branches do not.

## License

MIT — see [LICENSE](LICENSE).

## Attribution

- USDA Natural Resources Conservation Service AWDB / SNOTEL
- Province of British Columbia ASWS (Open Government Licence – British Columbia)
- Japan Meteorological Agency (JMA) AMeDAS
