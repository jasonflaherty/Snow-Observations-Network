# Provider notes

## NRCS AWDB

REST API (not CSV):

| Purpose | Endpoint |
|---------|----------|
| Station catalog | `GET https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations` |
| Observations | `GET https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data` |

Observation pull params: `duration=HOURLY|DAILY`, `elements=WTEQ,SNWD,TOBS,PREC`, batched `stationTriplets`, `periodRef=START`.

- **Catalog networks:** SNTL, SCAN, MSTL (stored in `stations`)
- **Observation ingest:** **SNTL only**
- **Hourly job:** last **72 hours** (`duration=HOURLY`) for all active SNTL; older hourly rows pruned
- **Daily job (same beat):** last **7 days** (`duration=DAILY`)
- **Year lookback:** `ingest_nrcs_daily_backfill()` → up to **365 days** of AWDB daily (chunked)
- Unique key: `(station_id, timestamp, resolution)`
- Raw JSON archived under `storage/raw/YYYY/MM/DD/nrcs/`

## BC ASWS

- Live CSVs: `https://www.env.gov.bc.ca/wsd/data_searches/snow/asws/data/{SW,SD,PC,TA}.csv`
- Requires a browser-like `User-Agent` (`SON_USER_AGENT`)
- Station catalog: `providers/bc_asws/stations_seed.json` (seeded from SnoTel Mapper’s BC catalog; refresh from DataBC WFS when updating)
- **Hourly job:** last **72 hours** (CSV already holds water-year history; filter locally, upsert; prune older hourly)
- **Daily job:** last-of-day snapshots for **7 days** (`resolution=daily`)
- **Year lookback:** `ingest_bc_asws_daily_backfill()` from water-year CSVs (seasonal depth ~1 year)
- Station IDs: `SON-CA-BCASWS-{CODE}` (e.g. `SON-CA-BCASWS-2F05P`)

## JMA AMeDAS

Bosai JSON (no API key):

| Purpose | Endpoint |
|---------|----------|
| Station catalog | `GET https://www.jma.go.jp/bosai/amedas/const/amedastable.json` |
| Latest timestamp | `GET https://www.jma.go.jp/bosai/amedas/data/latest_time.txt` |
| Nationwide snapshot | `GET https://www.jma.go.jp/bosai/amedas/data/map/{YYYYMMDDHHMMSS}.json` |

Map timestamps are **JST**. Values are `[value, aqc]` arrays; only `aqc == 0` is kept.

Field mapping: `snow` → `snow_depth_cm`, `snow1h` → `snowfall_cm`, `temp` → `temperature_c`, `precipitation1h` → `precipitation_mm`, `wind` → `wind_speed_ms`, `humidity` → `humidity`. **No SWE** (`swe_mm` always null).

- **Catalog:** all AMeDAS sites (~1286); `active=true` only when `elems[5] == '1'` (snow depth capability, ~330 sites)
- **Observation ingest:** snow-capable stations only; **hourly on-the-hour** map snapshots (not every 10 minutes)
- **Hourly job:** last **72 hours** (then prune)
- **Daily job:** one noon-JST map snapshot per day for **7 days** (map API is not suited to a full year backfill)
- Station IDs: `SON-JP-JMA-{CODE}` (e.g. `SON-JP-JMA-11016`)
- Attribution: [JMA website terms](https://www.jma.go.jp/jma/kishou/info/coment.html)
- Raw JSON archived under `storage/raw/YYYY/MM/DD/jma/`

## API history queries

```bash
GET /v1/stations/{id}/observations?resolution=hourly   # ~72h retained
GET /v1/stations/{id}/observations?resolution=daily    # 7d ongoing; up to 1y after backfill
GET /v1/stations/{id}/current                          # prefers latest hourly
```