"""mart/farms.parquet + GWA raster -> mart/resource.parquet (per-farm P50 CF). Spec §7.4 Path B.

Method 'gwa_windpowerlib': sample the Global Wind Atlas 4.0 mean-wind-speed
raster (100 m) at every farm centroid in one vectorized rasterio pass, shear to
hub height (power law, alpha=0.2), pick a windpowerlib turbine via
resource_lib.select_turbine (data/manual/turbine_map.csv), integrate the power
curve over a Weibull(k=2) density -> annual gross P50 capacity factor.

Hub-height fallback tiers (counts logged): own value -> fleet median of farms
with the same turbine_type -> median of the same commissioning decade -> fleet
median. Farms on GWA nodata or without any turbine match get p50_cf = NULL and
a `reason` — never an invented number.

--ninja (Path A, spec §7.4): additionally fetch hourly CF from the
renewables.ninja API for selected farms into mart/cf_hourly.parquet. Requires
RENEWABLES_NINJA_TOKEN (skipped with a note otherwise). Endpoint + params
verified 2026-07-11: GET https://www.renewables.ninja/api/data/wind with
lat, lon, date_from, date_to, capacity, height, turbine, format; header
'Authorization: Token <token>'; registered limit ~50/hour, burst 6/min ->
we sleep 12 s between uncached calls and cache raw responses in data/raw/ninja/.
License: CC BY-NC 4.0 (non-commercial) — stated in output meta and logs.

Attribution: Global Wind Atlas 4.0 (DTU), CC BY 4.0; windpowerlib oedb turbine
library; renewables.ninja (Staffell & Pfenninger), CC BY-NC 4.0.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
import resource_lib

# This file shadows the stdlib `resource` module while the script directory sits
# on sys.path. Siblings (resource_lib) are imported above; now drop the script
# dir so any lazy `import resource` inside third-party libs gets the stdlib one.
_HERE = str(Path(__file__).resolve().parent)
sys.path[:] = [p for p in sys.path if p and str(Path(p).resolve()) != _HERE]

REPO_ROOT = Path(__file__).resolve().parents[2]
FARMS_PATH = REPO_ROOT / "data" / "mart" / "farms.parquet"
RESOURCE_PATH = REPO_ROOT / "data" / "mart" / "resource.parquet"
CF_HOURLY_PATH = REPO_ROOT / "data" / "mart" / "cf_hourly.parquet"
NINJA_RAW_DIR = REPO_ROOT / "data" / "raw" / "ninja"

SHEAR_ALPHA = 0.2
WEIBULL_K = 2.0
METHOD = "gwa_windpowerlib"
SOURCE = "Global Wind Atlas 4.0 (100 m, DTU, CC BY 4.0) + windpowerlib oedb power curve"

NINJA_URL = "https://www.renewables.ninja/api/data/wind"
NINJA_CAPACITY_KW = 1000.0
NINJA_SLEEP_S = 12.0  # burst limit 6/min (docs, 2026-07-11)
NINJA_LICENSE_NOTE = "renewables.ninja data: CC BY-NC 4.0 — NON-COMMERCIAL use only"

log = logging.getLogger("resource")


# ------------------------------------------------------------- GWA sampling


def sample_gwa_batch(lats: np.ndarray, lons: np.ndarray, tif_path: Path) -> np.ndarray:
    """Mean 100 m wind speed [m/s] for all points in one rasterio sample pass.

    NaN where the point is outside the raster bounds, on nodata, or implausible
    (same validation as resource_lib.sample_gwa) — callers must treat NaN as
    'no data', never substitute a made-up speed.
    """
    if not tif_path.exists():
        raise FileNotFoundError(
            f"GWA raster not found at {tif_path} — run data/pipelines/gwa_download.py first"
        )
    out = np.full(len(lats), np.nan)
    with rasterio.open(tif_path) as src:
        b = src.bounds
        inside = (lons >= b.left) & (lons <= b.right) & (lats >= b.bottom) & (lats <= b.top)
        idx = np.flatnonzero(inside)
        if idx.size:
            coords = list(zip(lons[idx], lats[idx], strict=True))
            values = np.array([v[0] for v in src.sample(coords)], dtype=float)
            if src.nodata is not None:
                values[values == src.nodata] = np.nan
            values[~np.isfinite(values) | (values <= 0.0) | (values >= 30.0)] = np.nan
            out[idx] = values
    return out


# ------------------------------------------------------- hub-height fallback


def resolve_hub_heights(farms: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(hub_height_used, tier) per farm: own -> type median -> decade median -> fleet median.

    NaN hub + tier 'none' when the whole fleet has no hub data (never invented).
    """
    own = farms["hub_height_m"].astype(float)
    by_type = farms.groupby("turbine_type", dropna=True)["hub_height_m"].median()
    decade = (farms["commissioning_year"].astype("Float64") // 10 * 10).astype("Float64")
    by_decade = farms.assign(_dec=decade).groupby("_dec", dropna=True)["hub_height_m"].median()
    fleet_median = farms["hub_height_m"].median()

    used = own.copy()
    tier = pd.Series("own", index=farms.index)

    miss = used.isna()
    type_fill = farms.loc[miss, "turbine_type"].map(by_type)
    used.loc[miss] = type_fill.astype(float)
    tier.loc[miss & used.notna()] = "type_median"

    miss = used.isna()
    dec_fill = decade[miss].map(by_decade)
    used.loc[miss] = dec_fill.astype(float)
    tier.loc[miss & used.notna()] = "decade_median"

    miss = used.isna()
    if not pd.isna(fleet_median):
        used.loc[miss] = float(fleet_median)
        tier.loc[miss] = "fleet_median"
    tier.loc[used.isna()] = "none"

    log.info("hub-height tiers: %s", tier.value_counts().to_dict())
    return used, tier


# ------------------------------------------------------------- Path B (GWA)


def build_resource(farms: pd.DataFrame, tif_path: Path) -> pd.DataFrame:
    lats = farms["lat"].to_numpy(dtype=float)
    lons = farms["lon"].to_numpy(dtype=float)
    v100 = sample_gwa_batch(lats, lons, tif_path)
    log.info("GWA sampled: %d/%d farms with data", int(np.isfinite(v100).sum()), len(farms))

    hub_used, hub_tier = resolve_hub_heights(farms)
    mw_unit = (farms["mw_total"] / farms["n_units"].clip(lower=1)).astype(float)

    rows: list[dict] = []
    reason_counts: dict[str, int] = {}
    for i, farm in enumerate(farms.itertuples()):
        hub = hub_used.iloc[i]
        reason: str | None = None
        cf: float | None = None
        source = SOURCE

        if not np.isfinite(v100[i]):
            reason = "gwa_nodata"
        elif pd.isna(hub):
            reason = "no_hub_height"
        else:
            try:
                ttype, match_method = resource_lib.select_turbine(
                    None if pd.isna(farm.turbine_type) else str(farm.turbine_type),
                    None if pd.isna(farm.rotor_d_m) else float(farm.rotor_d_m),
                    float(mw_unit.iloc[i]),
                )
                v_hub = resource_lib.shear_to_hub(float(v100[i]), float(hub), SHEAR_ALPHA)
                cf = resource_lib.weibull_cf(v_hub, ttype, k=WEIBULL_K)
                source = (
                    f"{SOURCE}; turbine {ttype} ({match_method}), "
                    f"hub {hub:.0f} m ({hub_tier.iloc[i]}), shear a={SHEAR_ALPHA}, "
                    f"Weibull k={WEIBULL_K:g}"
                )
            except ValueError as exc:
                reason = f"no_turbine_match: {exc}"
        if reason:
            key = reason.split(":")[0]
            reason_counts[key] = reason_counts.get(key, 0) + 1
        rows.append(
            {
                "farm_id": farm.farm_id,
                "p50_cf": cf,
                "method": METHOD,
                "hub_height_used": None if pd.isna(hub) else float(hub),
                "source": source,
                "reason": reason,
            }
        )

    out = pd.DataFrame(rows).astype(
        {
            "farm_id": "string",
            "p50_cf": "float64",
            "method": "string",
            "hub_height_used": "float64",
            "source": "string",
            "reason": "string",
        }
    )
    ok = out["p50_cf"].notna()
    log.info(
        "p50_cf: %d/%d farms (null reasons: %s); mean %.3f, min %.3f, max %.3f",
        int(ok.sum()),
        len(out),
        reason_counts or "none",
        out.loc[ok, "p50_cf"].mean() if ok.any() else float("nan"),
        out.loc[ok, "p50_cf"].min() if ok.any() else float("nan"),
        out.loc[ok, "p50_cf"].max() if ok.any() else float("nan"),
    )
    return out


# ---------------------------------------------------------- Path A (ninja)


def ninja_fetch_farm(
    session: requests.Session,
    farm: pd.Series,
    hub_height: float,
    turbine: str,
    year: int,
) -> pd.DataFrame:
    """Hourly CF for one farm-year from renewables.ninja (raw response cached)."""
    cache = NINJA_RAW_DIR / f"{farm['farm_id']}_{year}.json"
    if cache.exists():
        log.info("ninja %s %d: using cached %s", farm["farm_id"], year, cache.name)
        payload = json.loads(cache.read_text(encoding="utf-8"))
    else:
        params = {
            "lat": round(float(farm["lat"]), 5),
            "lon": round(float(farm["lon"]), 5),
            "date_from": f"{year}-01-01",
            "date_to": f"{year}-12-31",
            "capacity": NINJA_CAPACITY_KW,
            "height": round(float(hub_height), 1),
            "turbine": turbine,
            "format": "json",
        }
        log.info("ninja GET %s for %s (%s)", NINJA_URL, farm["farm_id"], params)
        resp = session.get(NINJA_URL, params=params, timeout=120)
        if resp.status_code == 429:
            raise RuntimeError(
                f"renewables.ninja rate limit hit (HTTP 429) at {farm['farm_id']}: "
                f"{resp.text[:200]} — re-run later; cached farms are kept"
            )
        if not resp.ok:
            raise RuntimeError(
                f"renewables.ninja HTTP {resp.status_code} for {farm['farm_id']}: {resp.text[:300]}"
            )
        payload = resp.json()
        NINJA_RAW_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload), encoding="utf-8")
        time.sleep(NINJA_SLEEP_S)

    data = payload.get("data")
    if not data:
        raise RuntimeError(f"renewables.ninja returned no data for {farm['farm_id']} {year}")
    ts = pd.to_datetime(list(data.keys()))
    cf = np.array([row["electricity"] for row in data.values()], dtype=float) / NINJA_CAPACITY_KW
    if cf.min() < -1e-9 or cf.max() > 1.0 + 1e-9:
        raise RuntimeError(
            f"implausible ninja CF range [{cf.min():.3f}, {cf.max():.3f}] "
            f"for {farm['farm_id']} {year}"
        )
    frame = pd.DataFrame({"farm_id": farm["farm_id"], "ts": ts, "cf": np.clip(cf, 0.0, 1.0)})
    return frame.sort_values("ts").reset_index(drop=True)


def run_ninja(
    farms: pd.DataFrame,
    hub_used: pd.Series,
    farm_ids: list[str],
    year: int,
    turbine: str,
) -> None:
    token = os.environ.get("RENEWABLES_NINJA_TOKEN")
    if not token:
        log.warning("--ninja requested but RENEWABLES_NINJA_TOKEN is not set — skipping Path A")
        return
    log.warning("%s", NINJA_LICENSE_NOTE)

    selected = farms[farms["farm_id"].isin(farm_ids)]
    missing = set(farm_ids) - set(selected["farm_id"])
    if missing:
        raise RuntimeError(f"--ninja-farms ids not in farms.parquet: {sorted(missing)}")

    session = requests.Session()
    session.headers.update({"Authorization": f"Token {token}"})

    frames: list[pd.DataFrame] = []
    for idx, farm in selected.iterrows():
        hub = hub_used.loc[idx]
        if pd.isna(hub):
            log.warning("ninja: skipping %s — no hub height at any tier", farm["farm_id"])
            continue
        frames.append(ninja_fetch_farm(session, farm, float(hub), turbine, year))

    if not frames:
        log.warning("ninja: nothing fetched")
        return
    fetched = pd.concat(frames, ignore_index=True)

    if CF_HOURLY_PATH.exists():  # idempotent: replace fetched farms, keep the rest
        existing = pd.read_parquet(CF_HOURLY_PATH)
        existing = existing[~existing["farm_id"].isin(fetched["farm_id"].unique())]
        fetched = pd.concat([existing, fetched], ignore_index=True)
    fetched = fetched.sort_values(["farm_id", "ts"]).reset_index(drop=True)
    fetched.to_parquet(CF_HOURLY_PATH, index=False)
    log.info(
        "wrote %s: %d rows, %d farms (%s)",
        CF_HOURLY_PATH,
        len(fetched),
        fetched["farm_id"].nunique(),
        NINJA_LICENSE_NOTE,
    )


# --------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--farms", type=Path, default=FARMS_PATH)
    parser.add_argument("--gwa-tif", type=Path, default=resource_lib.GWA_TIF)
    parser.add_argument("--out", type=Path, default=RESOURCE_PATH)
    parser.add_argument(
        "--ninja", action="store_true", help="also fetch hourly CF from renewables.ninja (Path A)"
    )
    parser.add_argument(
        "--ninja-farms",
        type=str,
        default=None,
        help="comma-separated farm_ids for --ninja (default: top 5 by mw_total)",
    )
    parser.add_argument("--ninja-year", type=int, default=2019)
    parser.add_argument(
        "--ninja-turbine",
        type=str,
        default="Vestas V90 2000",
        help="renewables.ninja turbine model name (live-verified default)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if not args.farms.exists():
        raise FileNotFoundError(f"{args.farms} not found — run data/pipelines/build_fleet.py first")
    farms = pd.read_parquet(args.farms)
    if farms.empty:
        raise RuntimeError(f"{args.farms} is empty")

    out = build_resource(farms, args.gwa_tif)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    log.info("wrote %s (%d rows)", args.out, len(out))

    meta = {
        "method": METHOD,
        "shear_alpha": SHEAR_ALPHA,
        "weibull_k": WEIBULL_K,
        "gwa_tif": str(args.gwa_tif),
        "n_farms": int(len(out)),
        "n_with_cf": int(out["p50_cf"].notna().sum()),
        "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "attribution": [
            "Global Wind Atlas 4.0 (DTU), CC BY 4.0",
            "windpowerlib oedb turbine library",
        ],
    }
    if args.ninja:
        meta["ninja_license"] = NINJA_LICENSE_NOTE
    meta_path = args.out.with_name("resource_meta.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    if args.ninja:
        hub_used, _ = resolve_hub_heights(farms)
        if args.ninja_farms:
            ids = [s.strip() for s in args.ninja_farms.split(",") if s.strip()]
        else:
            ids = list(farms.nlargest(5, "mw_total")["farm_id"])
            log.info("--ninja-farms not given; defaulting to top 5 by MW: %s", ids)
        run_ninja(farms, hub_used, ids, args.ninja_year, args.ninja_turbine)
    return 0


if __name__ == "__main__":
    sys.exit(main())
