# Data sources & licenses

Every dataset used by RHEINGOLD, its license, retrieval pipeline, and mart
destination. Attribution strings appear in the web footer and on /methodology.

| Source | What | Endpoint / method | License | Pipeline | Mart table | Retrieved |
|---|---|---|---|---|---|---|
| Marktstammdatenregister (BNetzA) | Every German generation unit; wind onshore fleet | `open-mastr` bulk download <!-- RESEARCH: verified API surface --> | DL-DE/BY-2.0 — attribution required | `data/pipelines/download_mastr.py` | `units`, `farms` | <!-- fill on run --> |
| SMARD (Bundesnetzagentur) | Hourly day-ahead price DE/LU 2015→ | chart_data JSON API, filter 4169 <!-- RESEARCH: verify --> | CC BY 4.0 | `data/pipelines/download_smard.py` | `prices_hourly` | <!-- fill on run --> |
| Netztransparenz (ÜNB) | Monthly Marktwert Wind an Land | published CSV/XLS <!-- RESEARCH: verified URL --> | site terms, attribution | `data/pipelines/marktwerte.py` | `marktwerte` | <!-- fill on run --> |
| BNetzA Ausschreibungen | Onshore wind auction results 2017–2025 | hand-compiled, one source URL per row | public sector information | `data/manual/bnetza_onshore_auctions.csv` | (read directly) | <!-- fill on compile --> |
| renewables.ninja | Hourly wind CF (Path A, showcase farms) | `/api/data/wind` <!-- RESEARCH: verify params --> | **CC BY-NC 4.0 — non-commercial** (stated prominently) | `data/pipelines/resource.py` | `resource`, `cf_hourly` | <!-- fill on run --> |
| Global Wind Atlas 3 (DTU/World Bank) | Mean wind speed GeoTIFF @100 m (Path B) | country GeoTIFF download | CC BY 4.0 <!-- RESEARCH: verify --> | `data/pipelines/resource.py` | `resource` | <!-- fill on run --> |
| windpowerlib / OEP turbine library | Power curves per turbine type | oedb turbine library via windpowerlib | open data (OEP) | `data/pipelines/resource.py` | (in-process) | <!-- fill on run --> |
| Deutsche WindGuard / Fraunhofer ISE / IRENA | Cost vintages (capex, opex, rates) | hand-compiled from studies, source per row | cited studies | `data/manual/cost_vintages.csv` | (read directly) | <!-- fill on compile --> |
| CARTO Dark Matter | Basemap style + tiles | `basemaps.cartocdn.com/gl/dark-matter-gl-style` | free for non-commercial w/ attribution <!-- RESEARCH: verify terms --> | (web runtime) | — | — |

## Attribution block (rendered in web footer)

> Anlagendaten: Marktstammdatenregister, Bundesnetzagentur (DL-DE/BY-2.0) ·
> Preisdaten: SMARD.de, Bundesnetzagentur (CC BY 4.0) · Marktwerte:
> netztransparenz.de · Wind resource: renewables.ninja (CC BY-NC 4.0) /
> Global Wind Atlas · Basemap © OpenStreetMap contributors © CARTO

**Non-commercial notice:** renewables.ninja data is CC BY-NC 4.0. RHEINGOLD is
a non-commercial portfolio/research project; commercial use would require
replacing Path A.
