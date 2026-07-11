# Data sources & licenses

Every dataset used by RHEINGOLD, its license, retrieval pipeline, and mart
destination. Attribution strings appear in the web footer and on /methodology.

| Source | What | Endpoint / method | License | Pipeline | Mart table | Retrieved |
|---|---|---|---|---|---|---|
| Marktstammdatenregister (BNetzA) | Every German generation unit; onshore wind fleet (~43k wind rows, filter `WindAnLandOderAufSee='Windkraft an Land'`, `EinheitBetriebsstatus='In Betrieb'`) | `open-mastr` 0.17.x bulk download (range-download from daily Gesamtdatenexport; verified live) | DL-DE/BY-2.0 — provider Bundesnetzagentur, license link + changed-data notice required | `data/pipelines/download_mastr.py` | `units`, `farms` | <!-- fill on run --> |
| SMARD (Bundesnetzagentur) | Hourly day-ahead price DE/LU, **2018-10→** (DE/LU zone split; earlier DE-AT-LU not served under filter 4169) | chart_data JSON API, filter 4169, weekly chunks (live-verified) | CC BY 4.0 — attribution "Bundesnetzagentur \| SMARD.de" | `data/pipelines/download_smard.py` | `prices_hourly` | 2026-07-12 |
| Netztransparenz (ÜNB) | Monthly Marktwert Wind an Land, ct/kWh, 2012-01→ | unauth JSON POST per year to `GetMarketpremiumData` chart service (verified live); fallback: OAuth2 WebAPI `ds.netztransparenz.de/api/v1/data/marktpraemie` | no explicit open-data license; statutory EEG transparency publication; attribution "Quelle: netztransparenz.de" | `data/pipelines/marktwerte.py` | `marktwerte` | 2026-07-11 |
| BNetzA Ausschreibungen | Onshore wind auction results, all 41 rounds 2017-05→2026-05 | extracted programmatically from the official BNetzA statistics workbook (Statistik_Onshore.xlsx, Stand 26.06.2026), cross-checked vs press releases/BDEW | public sector information | `data/manual/bnetza_onshore_auctions.csv` | (read directly) | 2026-07-11 |
| renewables.ninja | Hourly wind CF (Path A, showcase farms; requires token — registered limit 50/h; anonymous 5/day, data ≤2019) | `GET /api/data/wind` (lat, lon, date_from/to, capacity, height, turbine; `Authorization: Token …`) — live-verified | **CC BY-NC 4.0 — non-commercial** (stated prominently) | `data/pipelines/resource.py --ninja` | `resource`, `cf_hourly` | <!-- fill on run --> |
| Global Wind Atlas 4.0 (DTU/World Bank) | Mean wind speed GeoTIFF @100 m, Germany (Path B) | `globalwindatlas.info/api/gis/country/DEU/wind-speed/100` (302 → CDN v4 tif, 30.6 MB) | CC BY 4.0 (GWA Terms of Use) | `data/pipelines/gwa_download.py` + `data/pipelines/resource_lib.py` | `resource` | 2026-07-11 |
| windpowerlib / OEP turbine library | Power curves per turbine type (67 curve-backed of 140) | bundled oedb library, windpowerlib 0.2.2 (no network at runtime) | open data (OEP) | `data/pipelines/resource_lib.py` + `data/manual/turbine_map.csv` | (in-process) | 2026-07-11 |
| Deutsche WindGuard / Fraunhofer ISE / IRENA | Cost vintages 2015–2026 (capex HIK+INK, opex, rates) | compiled from the WindGuard Kostensituation study series (2015/2019/2022/2023/2024/2025), source incl. table/page per row; interpolation documented in-file | cited studies | `data/manual/cost_vintages.csv` | (read directly) | 2026-07-11 |
| OpenFreeMap (primary basemap) | Dark GL style + tiles | `tiles.openfreemap.org/styles/dark` | free for any use, no key; attribution "OpenFreeMap © OpenMapTiles, Data from OpenStreetMap" | (web runtime) | — | 2026-07-11 |
| CARTO Dark Matter (fallback basemap) | GL style + tiles | `basemaps.cartocdn.com/gl/dark-matter-gl-style` | free tier scoped to "CARTO grantees" — used as fallback only, attribution "© OpenStreetMap contributors © CARTO" | (web runtime) | — | 2026-07-11 |

## Attribution block (rendered in web footer)

> Anlagendaten: Marktstammdatenregister, Bundesnetzagentur (DL-DE/BY-2.0) ·
> Preisdaten: Bundesnetzagentur | SMARD.de (CC BY 4.0) · Marktwerte: Quelle:
> netztransparenz.de · Wind resource: Global Wind Atlas 4.0 (CC BY 4.0) /
> renewables.ninja (CC BY-NC 4.0) · Basemap: OpenFreeMap © OpenMapTiles,
> Data from OpenStreetMap (fallback © OpenStreetMap contributors © CARTO)

**Non-commercial notice:** renewables.ninja data is CC BY-NC 4.0. RHEINGOLD is
a non-commercial portfolio/research project; commercial use would require
replacing Path A.
