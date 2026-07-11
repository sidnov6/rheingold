"""Pure wind-resource helpers for Path B (GWA + windpowerlib), spec §7.4.

Functions
---------
- ``sample_gwa(lat, lon)``      -> mean wind speed at 100 m [m/s] from the GWA 4.0
  Germany GeoTIFF (download via ``gwa_download.py`` first).
- ``shear_to_hub(v100, hub_height, alpha)`` -> power-law shear to hub height.
- ``weibull_cf(v_hub, turbine_type, k)``    -> annual P50 *gross* capacity factor,
  integrating the windpowerlib oedb power curve over a Weibull density with
  shape k and scale chosen so the Weibull mean equals ``v_hub``.
- ``select_turbine(typenbezeichnung, rotor_d, mw)`` -> windpowerlib turbine_type
  via ``data/manual/turbine_map.csv`` patterns, kW-refined within the model
  family, with a specific-power (W/m²) class fallback.

NOTE: net losses (wake, availability, electrical, curtailment) are NOT applied
here — that is the engine's job (§8). These are gross P50 figures.

No network access. Raises on missing data — never fabricates.
Attribution: Global Wind Atlas 4.0 (DTU), CC BY 4.0; oedb turbine library via
windpowerlib 0.2.2.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path

import numpy as np
import rasterio
from scipy.stats import weibull_min
from windpowerlib import WindTurbine, get_turbine_types

_DATA_DIR = Path(__file__).resolve().parents[1]
GWA_TIF = _DATA_DIR / "raw" / "gwa" / "DEU_wind-speed_100m.tif"
TURBINE_MAP_CSV = _DATA_DIR / "manual" / "turbine_map.csv"

# Specific-power [W/m²] class boundaries for the fallback rows in turbine_map.csv.
SPECIFIC_POWER_LOW_MAX = 300.0
SPECIFIC_POWER_MEDIUM_MAX = 400.0


# --------------------------------------------------------------------------- GWA


@lru_cache(maxsize=1)
def _gwa_dataset(path: str) -> rasterio.DatasetReader:
    if not Path(path).exists():
        raise FileNotFoundError(
            f"GWA raster not found at {path} — run data/pipelines/gwa_download.py first"
        )
    return rasterio.open(path)


def sample_gwa(lat: float, lon: float, tif_path: Path = GWA_TIF) -> float:
    """Mean wind speed at 100 m [m/s] at (lat, lon) from the GWA 4.0 raster.

    Raises ValueError if the point is outside the raster or falls on nodata
    (e.g. outside German territory) — never fabricates a value.
    """
    src = _gwa_dataset(str(tif_path))
    b = src.bounds
    if not (b.left <= lon <= b.right and b.bottom <= lat <= b.top):
        raise ValueError(f"({lat:.4f}, {lon:.4f}) outside GWA raster bounds {tuple(b)}")
    (value,) = (v[0] for v in src.sample([(lon, lat)]))
    v = float(value)
    # GWA uses nan as nodata outside the country clip (incl. some border areas).
    if not math.isfinite(v) or (src.nodata is not None and v == src.nodata):
        raise ValueError(f"GWA nodata at ({lat:.4f}, {lon:.4f}) — outside Germany coverage")
    if not (0.0 < v < 30.0):
        raise ValueError(f"implausible GWA wind speed {v!r} at ({lat:.4f}, {lon:.4f})")
    return v


# ------------------------------------------------------------------------- shear


def shear_to_hub(v100: float, hub_height: float, alpha: float = 0.2) -> float:
    """Power-law shear from 100 m reference to hub height: v * (h/100)^alpha."""
    if v100 <= 0:
        raise ValueError(f"v100 must be positive, got {v100}")
    if hub_height <= 0:
        raise ValueError(f"hub_height must be positive, got {hub_height}")
    return v100 * (hub_height / 100.0) ** alpha


# ---------------------------------------------------------------- Weibull P50 CF


@cache
def _power_curve(turbine_type: str) -> tuple[np.ndarray, np.ndarray, float]:
    """(wind_speeds [m/s], power [W], nominal_power [W]) for a library type."""
    t = WindTurbine(turbine_type=turbine_type, hub_height=100.0)
    if t.power_curve is None:
        raise ValueError(f"windpowerlib type {turbine_type!r} has no power curve")
    ws = t.power_curve["wind_speed"].to_numpy(dtype=float)
    p = t.power_curve["value"].to_numpy(dtype=float)
    return ws, p, float(t.nominal_power)


def weibull_cf(v_hub: float, turbine_type: str, k: float = 2.0) -> float:
    """Annual P50 gross capacity factor at mean hub-height wind speed ``v_hub``.

    Integrates the turbine power curve against a Weibull(k, scale) density with
    scale = v_hub / Γ(1 + 1/k), i.e. the Weibull mean equals v_hub. Gross CF —
    no wake/availability/electrical/curtailment losses (engine's job).
    """
    if v_hub <= 0:
        raise ValueError(f"v_hub must be positive, got {v_hub}")
    if k <= 0:
        raise ValueError(f"Weibull shape k must be positive, got {k}")
    curve_ws, curve_p, p_nominal = _power_curve(turbine_type)
    scale = v_hub / math.gamma(1.0 + 1.0 / k)
    # Fine grid over the curve support; power is 0 outside (below cut-in /
    # above cut-out, since library curves end at cut-out).
    grid = np.linspace(0.0, float(curve_ws.max()), 2000)
    power = np.interp(grid, curve_ws, curve_p, left=0.0, right=0.0)
    density = weibull_min.pdf(grid, c=k, scale=scale)
    expected_power = float(np.trapezoid(power * density, grid))
    cf = expected_power / p_nominal
    if not (0.0 <= cf <= 1.0):
        raise ValueError(f"implausible CF {cf:.3f} for {turbine_type} at v_hub={v_hub:.2f} m/s")
    return cf


# ------------------------------------------------------------- turbine selection


@dataclass(frozen=True)
class _MapRow:
    pattern: re.Pattern | None
    windpowerlib_type: str
    match_rank: int
    substitute: bool
    fallback_class: str
    note: str


@lru_cache(maxsize=1)
def _turbine_map(csv_path: str) -> tuple[_MapRow, ...]:
    rows: list[_MapRow] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pat = r["mastr_pattern"].strip()
            rows.append(
                _MapRow(
                    pattern=re.compile(pat, re.IGNORECASE) if pat else None,
                    windpowerlib_type=r["windpowerlib_type"].strip(),
                    match_rank=int(r["match_rank"]),
                    substitute=r["substitute"].strip().lower() == "true",
                    fallback_class=r["fallback_class"].strip(),
                    note=r["note"].strip(),
                )
            )
    rows.sort(key=lambda r: r.match_rank)
    return tuple(rows)


@lru_cache(maxsize=1)
def _library_ids_by_family() -> dict[str, list[tuple[int, str]]]:
    """family (id part before '/') -> [(rated_kW, turbine_type)] for curve-backed types."""
    tt = get_turbine_types(turbine_library="local", print_out=False, filter_=True)
    fams: dict[str, list[tuple[int, str]]] = {}
    for tid in tt["turbine_type"]:
        family, _, kw = tid.rpartition("/")
        if family and kw.isdigit():
            fams.setdefault(family, []).append((int(kw), tid))
    return fams


def _refine_by_kw(base_type: str, mw: float | None) -> str:
    """Within the family of base_type, pick the rated-kW variant nearest to mw."""
    if mw is None or mw <= 0:
        return base_type
    family = base_type.rpartition("/")[0]
    variants = _library_ids_by_family().get(family)
    if not variants:
        return base_type
    target_kw = mw * 1000.0
    return min(variants, key=lambda v: abs(v[0] - target_kw))[1]


def _specific_power(rotor_d: float, mw: float) -> float:
    """Specific power [W/m²] = rated power / swept rotor area."""
    return (mw * 1e6) / (math.pi * (rotor_d / 2.0) ** 2)


def select_turbine(
    typenbezeichnung: str | None,
    rotor_d: float | None,
    mw: float | None,
    csv_path: Path = TURBINE_MAP_CSV,
) -> tuple[str, str]:
    """Map a MaStR unit to a windpowerlib turbine_type.

    Returns (turbine_type, method) with method one of:
    'pattern', 'pattern_substitute', 'fallback_low', 'fallback_medium',
    'fallback_high'. ``mw`` is per-unit rated power in MW (used to refine the
    rated-kW variant within a matched family and for the specific-power
    fallback); ``rotor_d`` is rotor diameter in m.
    """
    rows = _turbine_map(str(csv_path))

    if typenbezeichnung:
        text = " ".join(typenbezeichnung.split())
        for row in rows:
            if row.pattern is not None and row.pattern.search(text):
                chosen = (
                    row.windpowerlib_type
                    if row.substitute
                    else _refine_by_kw(row.windpowerlib_type, mw)
                )
                return chosen, "pattern_substitute" if row.substitute else "pattern"

    # Specific-power class fallback.
    if rotor_d and mw and rotor_d > 0 and mw > 0:
        sp = _specific_power(rotor_d, mw)
        cls = (
            "low"
            if sp < SPECIFIC_POWER_LOW_MAX
            else "medium"
            if sp < SPECIFIC_POWER_MEDIUM_MAX
            else "high"
        )
    else:
        cls = "medium"  # default when rotor/rating unknown (see turbine_map.csv)
    for row in rows:
        if row.pattern is None and row.fallback_class == cls:
            return row.windpowerlib_type, f"fallback_{cls}"
    raise ValueError(f"turbine_map.csv at {csv_path} has no fallback row for class {cls!r}")
