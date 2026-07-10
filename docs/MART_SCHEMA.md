# DuckDB mart schema — `data/mart/rheingold.duckdb`

Contract between `data/pipelines/*` (writers) and `apps/api` (reader). Spec §7.
All pipelines are idempotent: `CREATE OR REPLACE TABLE`. Raw downloads live in
`data/raw/` (gitignored); the mart plus `fleet.json.gz` are the committed artifacts.

## `units` — one row per MaStR wind unit (onshore, in operation)

| column | type | from MaStR field |
|---|---|---|
| unit_id | TEXT PK | EinheitMastrNummer |
| farm_name | TEXT NULL | NameWindpark |
| lat, lon | DOUBLE | Breitengrad, Laengengrad |
| mw | DOUBLE | Nettonennleistung (kW→MW /1000) |
| hub_height_m | DOUBLE NULL | Nabenhoehe |
| rotor_d_m | DOUBLE NULL | Rotordurchmesser |
| turbine_type | TEXT NULL | Typenbezeichnung |
| manufacturer | TEXT NULL | Hersteller (resolved to name) |
| commissioning_date | DATE NULL | Inbetriebnahmedatum |
| bundesland | TEXT NULL | Bundesland |
| operator | TEXT NULL | AnlagenbetreiberName |
| status | TEXT | BetriebsStatus (filter: In Betrieb) |

## `farms` — grouped by NameWindpark, fallback DBSCAN(eps≈600m, min 2), singletons alone

| column | type | notes |
|---|---|---|
| farm_id | TEXT PK | slug: `wp-` + normalized name or `cl-` + cluster hash |
| name | TEXT | park name or synthesized "«place» cluster" |
| lat, lon | DOUBLE | MW-weighted centroid |
| mw_total | DOUBLE | |
| n_units | INTEGER | |
| manufacturer | TEXT NULL | modal manufacturer |
| turbine_type | TEXT NULL | modal type |
| hub_height_m | DOUBLE NULL | mean of non-null |
| rotor_d_m | DOUBLE NULL | mean of non-null |
| commissioning_year | INTEGER NULL | min year of units |
| bundesland | TEXT NULL | modal |
| operator | TEXT NULL | modal |
| unit_ids | TEXT | JSON array of member unit ids |

## `prices_hourly` — SMARD day-ahead DE/LU

| ts TIMESTAMP | eur_mwh DOUBLE |

## `marktwerte` — Netztransparenz MW Wind an Land

| month DATE (first of month) | mw_wind_onshore_ct_kwh DOUBLE |

## `resource` — per-farm wind resource

| farm_id TEXT | p50_cf DOUBLE | method TEXT ('ninja'\|'gwa_windpowerlib') | hub_height_used DOUBLE | source TEXT |

## `cf_hourly` — cached hourly CF (Path A farms only)

| farm_id TEXT | ts TIMESTAMP | cf DOUBLE |

## `fleet.json.gz` — map payload (also written by build_fleet.py)

Gzipped JSON array, target ≤ 4 MB:
`[{ "id", "name", "lat", "lon", "mw", "n": n_units, "man": manufacturer, "yr": commissioning_year, "bl": bundesland }]`
plus a sidecar `fleet_meta.json`: `{ "unit_count", "farm_count", "total_mw", "mastr_snapshot_date", "built_at" }`.
