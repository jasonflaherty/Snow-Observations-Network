# Snow Observations Network (SON)

Free, open, standardized API for global snowpack observations.

SON is a **data platform**: ingest snow observations from multiple providers, normalize units, store them in PostGIS, and expose them through a versioned HTTP API.

## Status

Phase 1 foundation is in progress (Docker, PostGIS, FastAPI, NRCS + BC ASWS adapters).

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Mission

> Provide a free, open, standardized API for global snowpack observations.

## License

MIT — see [LICENSE](LICENSE).

## Attribution

Upstream data providers retain their own terms. Planned Phase 1 sources include:

- USDA NRCS AWDB / SNOTEL
- British Columbia ASWS (Open Government Licence – British Columbia)
