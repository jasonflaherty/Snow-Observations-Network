# Provider notes

## NRCS AWDB

REST API (not CSV):

| Purpose | Endpoint |
|---------|----------|
| Station catalog | `GET https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations` |
| Observations | `GET https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data` |

Observation pull params: `duration=HOURLY`, `elements=WTEQ,SNWD,TOBS,PREC`, batched `stationTriplets`, `periodRef=START`.

- **Catalog networks:** SNTL, SCAN, MSTL (stored in `stations`)
- **Observation ingest:** **SNTL only**
- **Hourly job:** last **48 hours** for all active SNTL in Postgres (upsert on `(station_id, timestamp)`)
- **7-day backfill:** `ingest_nrcs_backfill()` → last **168 hours**; run once (or on demand), then rely on hourly upserts going forward
- Raw JSON archived under `storage/raw/YYYY/MM/DD/nrcs/`

## BC ASWS

- Live CSVs: `https://www.env.gov.bc.ca/wsd/data_searches/snow/asws/data/{SW,SD,PC,TA}.csv`
- Requires a browser-like `User-Agent` (`SON_USER_AGENT`)
- Station catalog: `providers/bc_asws/stations_seed.json` (seeded from SnoTel Mapper’s BC catalog; refresh from DataBC WFS when updating)
- **Hourly job:** last **48 hours** (CSV already holds water-year history; filter locally, upsert)
- **7-day backfill:** `ingest_bc_asws_backfill()` → last **168 hours**
- Station IDs: `SON-CA-BCASWS-{CODE}` (e.g. `SON-CA-BCASWS-2F05P`)
