"""mart/units.parquet -> mart/farms.parquet + apps/web/public/fleet.json.gz. Spec §7.1.

Grouping rules (docs/MART_SCHEMA.md `farms`):
- primary: normalized `NameWindpark` (casefold + whitespace collapse); farm_id `wp-<slug>`.
- GUARD: a named group spanning > 5 km is split spatially (union-find, eps 2 km)
  into parts with " (1)", " (2)" name suffixes and `-1`, `-2` id suffixes.
- unnamed units: spatial clustering, DBSCAN-equivalent at eps 600 m / min 2 —
  implemented WITHOUT sklearn as a ~600 m grid index + union-find over neighbor
  pairs within 600 m haversine; farm_id `cl-<hash8>` (hash of member unit ids).
- remaining singletons stand alone: farm_id `u-<unit_id>`.

Farm fields: MW-weighted centroid, modal manufacturer/type/bundesland/operator
(deterministic tie-break: lexicographically smallest), mean hub/rotor of
non-null, min commissioning year, `unit_ids` JSON array.

fleet.json.gz: `[{id, name, lat(5dp), lon(5dp), mw(1dp), n, man, yr, bl}]`,
gzip level 9 (mtime=0 for reproducible bytes), warn above 4 MB. Sidecar
fleet_meta.json: {unit_count, farm_count, total_mw, mastr_snapshot_date, built_at}.

No network. Never fabricates: missing upstream files raise and stop.
Attribution: Marktstammdatenregister, Bundesnetzagentur (DL-DE/BY-2.0).
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import logging
import math
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
UNITS_PATH = REPO_ROOT / "data" / "mart" / "units.parquet"
UNITS_META_PATH = REPO_ROOT / "data" / "mart" / "units_meta.json"
FARMS_PATH = REPO_ROOT / "data" / "mart" / "farms.parquet"
FLEET_JSON_GZ = REPO_ROOT / "apps" / "web" / "public" / "fleet.json.gz"
FLEET_META_PATH = REPO_ROOT / "apps" / "web" / "public" / "fleet_meta.json"

EPS_CLUSTER_M = 600.0  # unnamed-unit clustering radius (spec: DBSCAN eps≈600 m, min 2)
EPS_SPLIT_M = 2000.0  # linkage radius when splitting an overspanned named group
SPAN_GUARD_M = 5000.0  # named group wider than this gets split spatially
EARTH_RADIUS_M = 6_371_008.8
M_PER_DEG_LAT = 111_320.0
FLEET_JSON_WARN_BYTES = 4 * 1024 * 1024

log = logging.getLogger("build_fleet")


# ------------------------------------------------------------------- geometry


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


class UnionFind:
    """Union-find with path compression + union by size."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.size = [1] * n

    def find(self, i: int) -> int:
        root = i
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[i] != root:  # path compression
            self.parent[i], i = root, self.parent[i]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]


def spatial_clusters(lats: np.ndarray, lons: np.ndarray, eps_m: float) -> list[list[int]]:
    """Connected components under 'within eps_m haversine' (single-linkage).

    Equivalent to DBSCAN(eps, min_samples=2) components + noise-as-singletons,
    without sklearn: a grid index with ~eps-sized cells restricts the pairwise
    haversine check to the 3x3 cell neighborhood of each point.
    """
    n = len(lats)
    if n == 0:
        return []
    if n == 1:
        return [[0]]
    dlat = eps_m / M_PER_DEG_LAT
    # Longitude cell size at the subset's mean latitude (Germany spans ~47-55°N,
    # cos varies ~13% across it — safe because cells only PRE-FILTER candidates;
    # the exact haversine test decides membership. Bound cos away from 0.
    mean_lat = float(np.mean(lats))
    dlon = eps_m / (M_PER_DEG_LAT * max(math.cos(math.radians(mean_lat)), 0.2))

    cells: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i in range(n):
        cells[(int(math.floor(lats[i] / dlat)), int(math.floor(lons[i] / dlon)))].append(i)

    uf = UnionFind(n)
    for (cx, cy), members in cells.items():
        # within-cell pairs
        for a in range(len(members)):
            i = members[a]
            for b in range(a + 1, len(members)):
                j = members[b]
                if haversine_m(lats[i], lons[i], lats[j], lons[j]) <= eps_m:
                    uf.union(i, j)
        # forward half of the 8-neighborhood (each unordered cell pair once)
        for ox, oy in ((1, -1), (1, 0), (1, 1), (0, 1)):
            other = cells.get((cx + ox, cy + oy))
            if not other:
                continue
            for i in members:
                for j in other:
                    if haversine_m(lats[i], lons[i], lats[j], lons[j]) <= eps_m:
                        uf.union(i, j)

    comps: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        comps[uf.find(i)].append(i)
    # deterministic order: by smallest member index
    return sorted(comps.values(), key=lambda c: min(c))


def bbox_span_m(lats: np.ndarray, lons: np.ndarray) -> float:
    """Diagonal of the bounding box — cheap upper-ish proxy for group span."""
    return haversine_m(float(lats.min()), float(lons.min()), float(lats.max()), float(lons.max()))


# ------------------------------------------------------------------ names/ids

_UMLAUTS = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}
)


def normalize_name(raw: object) -> str | None:
    """Grouping key: whitespace-collapsed, casefolded. None if effectively empty."""
    if raw is None or (pd.api.types.is_scalar(raw) and pd.isna(raw)):
        return None
    text = " ".join(str(raw).split())
    return text.casefold() or None


def slugify(name: str, max_len: int = 60) -> str:
    s = name.translate(_UMLAUTS)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    s = s[:max_len].rstrip("-")
    return s or _hash8(name)


def _hash8(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def cluster_id(unit_ids: list[str]) -> str:
    return "cl-" + _hash8("|".join(sorted(unit_ids)))


# ---------------------------------------------------------------- aggregation


def _modal(series: pd.Series) -> str | None:
    """Most frequent non-null value; ties broken by lexicographic order."""
    s = series.dropna()
    if s.empty:
        return None
    counts = s.value_counts()
    top = counts.max()
    return sorted(str(v) for v, c in counts.items() if c == top)[0]


def _mean_or_none(series: pd.Series) -> float | None:
    s = series.dropna()
    return float(s.mean()) if not s.empty else None


def farm_record(farm_id: str, name: str, group: pd.DataFrame) -> dict:
    mw = group["mw"].to_numpy(dtype=float)
    total = float(mw.sum())
    if total > 0:
        lat = float(np.average(group["lat"].to_numpy(dtype=float), weights=mw))
        lon = float(np.average(group["lon"].to_numpy(dtype=float), weights=mw))
    else:  # degenerate: all-zero ratings -> plain mean
        lat, lon = float(group["lat"].mean()), float(group["lon"].mean())

    years = pd.to_datetime(group["commissioning_date"], errors="coerce").dt.year.dropna()
    return {
        "farm_id": farm_id,
        "name": name,
        "lat": lat,
        "lon": lon,
        "mw_total": total,
        "n_units": int(len(group)),
        "manufacturer": _modal(group["manufacturer"]),
        "turbine_type": _modal(group["turbine_type"]),
        "hub_height_m": _mean_or_none(group["hub_height_m"]),
        "rotor_d_m": _mean_or_none(group["rotor_d_m"]),
        "commissioning_year": int(years.min()) if not years.empty else None,
        "bundesland": _modal(group["bundesland"]),
        "operator": _modal(group["operator"]),
        "unit_ids": json.dumps(sorted(group["unit_id"].astype(str)), ensure_ascii=False),
    }


# ------------------------------------------------------------------- grouping


def build_farms(units: pd.DataFrame) -> pd.DataFrame:
    units = units.reset_index(drop=True)
    norm = units["farm_name"].map(normalize_name)
    named = units[norm.notna()].copy()
    named["_norm"] = norm[norm.notna()]
    unnamed = units[norm.isna()]
    log.info("units: %d named, %d unnamed", len(named), len(unnamed))

    records: list[dict] = []
    slug_owner: dict[str, str] = {}  # slug -> normalized name that claimed it
    n_split_groups = 0

    # --- named groups (display name = most common raw spelling in the group)
    for norm_name_, group in sorted(named.groupby("_norm"), key=lambda kv: kv[0]):
        display = _modal(group["farm_name"]) or str(norm_name_)
        slug = slugify(str(norm_name_))
        if slug_owner.setdefault(slug, str(norm_name_)) != str(norm_name_):
            slug = f"{slug}-{_hash8(str(norm_name_))[:6]}"  # collision: disambiguate
        base_id = f"wp-{slug}"

        lats = group["lat"].to_numpy(dtype=float)
        lons = group["lon"].to_numpy(dtype=float)
        if len(group) > 1 and bbox_span_m(lats, lons) > SPAN_GUARD_M:
            parts = spatial_clusters(lats, lons, EPS_SPLIT_M)
            if len(parts) > 1:
                n_split_groups += 1
                # biggest part first, deterministic
                parts.sort(key=lambda p: (-len(p), min(p)))
                for k, part in enumerate(parts, start=1):
                    sub = group.iloc[part]
                    records.append(farm_record(f"{base_id}-{k}", f"{display} ({k})", sub))
                continue
        records.append(farm_record(base_id, display, group))

    if n_split_groups:
        log.info(
            "guard: split %d named groups spanning > %.0f km (linkage eps %.0f m)",
            n_split_groups,
            SPAN_GUARD_M / 1000,
            EPS_SPLIT_M,
        )

    # --- unnamed units: 600 m clusters (>=2) get cl- ids, singletons u-<unit_id>
    n_clusters = n_singletons = 0
    if len(unnamed):
        u = unnamed.reset_index(drop=True)
        comps = spatial_clusters(
            u["lat"].to_numpy(dtype=float), u["lon"].to_numpy(dtype=float), EPS_CLUSTER_M
        )
        for comp in comps:
            sub = u.iloc[comp]
            if len(comp) >= 2:
                n_clusters += 1
                ids = sorted(sub["unit_id"].astype(str))
                fid = cluster_id(ids)
                bl = _modal(sub["bundesland"])
                name = f"{bl + ' ' if bl else ''}Cluster {fid[3:]}"
                records.append(farm_record(fid, name, sub))
            else:
                n_singletons += 1
                (uid,) = sub["unit_id"].astype(str)
                records.append(farm_record(f"u-{uid}", f"Einzelanlage {uid}", sub))
    log.info("unnamed -> %d clusters (>=2 units) + %d singletons", n_clusters, n_singletons)

    farms = pd.DataFrame.from_records(records)
    dupes = farms[farms["farm_id"].duplicated(keep=False)]
    if not dupes.empty:
        raise RuntimeError(f"duplicate farm_ids produced: {sorted(dupes['farm_id'].unique())[:10]}")
    if int(farms["n_units"].sum()) != len(units):
        raise RuntimeError(
            f"unit conservation violated: {int(farms['n_units'].sum())} grouped vs {len(units)}"
        )
    farms = farms.astype(
        {
            "farm_id": "string",
            "name": "string",
            "mw_total": "float64",
            "n_units": "int32",
            "manufacturer": "string",
            "turbine_type": "string",
            "hub_height_m": "float64",
            "rotor_d_m": "float64",
            "commissioning_year": "Int32",
            "bundesland": "string",
            "operator": "string",
            "unit_ids": "string",
        }
    )
    return farms.sort_values("farm_id").reset_index(drop=True)


# -------------------------------------------------------------------- outputs


def write_fleet_json(farms: pd.DataFrame, out_path: Path) -> int:
    entries = [
        {
            "id": r.farm_id,
            "name": r.name,
            "lat": round(float(r.lat), 5),
            "lon": round(float(r.lon), 5),
            "mw": round(float(r.mw_total), 1),
            "n": int(r.n_units),
            "man": None if pd.isna(r.manufacturer) else str(r.manufacturer),
            "yr": None if pd.isna(r.commissioning_year) else int(r.commissioning_year),
            "bl": None if pd.isna(r.bundesland) else str(r.bundesland),
        }
        for r in farms.itertuples()
    ]
    payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", compresslevel=9, mtime=0) as gz:
            gz.write(payload)
    size = out_path.stat().st_size
    log.info("wrote %s: %d entries, %.2f MB gzipped", out_path, len(entries), size / 1e6)
    if size > FLEET_JSON_WARN_BYTES:
        log.warning(
            "fleet.json.gz is %.2f MB — above the %.0f MB map-payload target (§7.1)",
            size / 1e6,
            FLEET_JSON_WARN_BYTES / 1e6,
        )
    return size


def mastr_snapshot_date(meta_path: Path) -> str:
    if not meta_path.exists():
        raise FileNotFoundError(
            f"{meta_path} not found — run data/pipelines/download_mastr.py first"
        )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    date = meta.get("snapshot_date")
    if not date:
        raise RuntimeError(f"{meta_path} has no 'snapshot_date' key")
    return str(date)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--units", type=Path, default=UNITS_PATH)
    parser.add_argument("--units-meta", type=Path, default=UNITS_META_PATH)
    parser.add_argument("--farms-out", type=Path, default=FARMS_PATH)
    parser.add_argument("--fleet-json", type=Path, default=FLEET_JSON_GZ)
    parser.add_argument("--fleet-meta", type=Path, default=FLEET_META_PATH)
    args = parser.parse_args(argv)
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if not args.units.exists():
        raise FileNotFoundError(
            f"{args.units} not found — run data/pipelines/download_mastr.py first"
        )
    units = pd.read_parquet(args.units)
    required = {
        "unit_id",
        "farm_name",
        "lat",
        "lon",
        "mw",
        "hub_height_m",
        "rotor_d_m",
        "turbine_type",
        "manufacturer",
        "commissioning_date",
        "bundesland",
        "operator",
    }
    missing = required - set(units.columns)
    if missing:
        raise RuntimeError(f"{args.units} missing columns: {sorted(missing)}")
    snapshot = mastr_snapshot_date(args.units_meta)

    farms = build_farms(units)
    args.farms_out.parent.mkdir(parents=True, exist_ok=True)
    farms.to_parquet(args.farms_out, index=False)
    log.info(
        "wrote %s: %d farms, %.1f MW, %d units",
        args.farms_out,
        len(farms),
        farms["mw_total"].sum(),
        int(farms["n_units"].sum()),
    )

    write_fleet_json(farms, args.fleet_json)
    meta = {
        "unit_count": int(len(units)),
        "farm_count": int(len(farms)),
        "total_mw": round(float(farms["mw_total"].sum()), 3),
        "mastr_snapshot_date": snapshot,
        "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    }
    args.fleet_meta.parent.mkdir(parents=True, exist_ok=True)
    args.fleet_meta.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    log.info("wrote %s: %s", args.fleet_meta, meta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
