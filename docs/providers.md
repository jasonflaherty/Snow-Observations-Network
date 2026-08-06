# Provider notes

## NRCS AWDB

- Stations: `GET https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations`
- Data: `GET https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data`
- Networks ingested: SNTL, SCAN, MSTL
- Hourly ingest currently fetches a capped batch of active triplets for reliability

## BC ASWS

- Live CSVs: `https://www.env.gov.bc.ca/wsd/data_searches/snow/asws/data/{SW,SD,PC,TA}.csv`
- Requires a browser-like `User-Agent` (`SON_USER_AGENT`)
- Station catalog: `providers/bc_asws/stations_seed.json` (seeded from SnoTel Mapper’s BC catalog; refresh from DataBC WFS when updating)
