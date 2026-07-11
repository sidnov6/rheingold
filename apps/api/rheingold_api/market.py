"""MarketInputs + market chart payload built from the DuckDB mart (spec §10).

Representative year = the latest complete calendar year in mart.prices_hourly
(8760 or 8784 hourly rows). The farm's cf_shape comes from mart.cf_hourly when a
full matching year is cached (Path A farms); otherwise a FLAT normalized shape
(1/n per hour) is used and disclosed in MarketInputs.source_note.

Marktwerte: the representative year's 12 monthly rows; when that year is not
fully published yet, the latest 12 available months are used with a note.

The MarketInputs build is lru_cached on (mart path, farm_id) so a warm
/api/underwrite call stays <300ms.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import Any

import duckdb
from rheingold_engine.models import MarketInputs

from . import deps


class MarketDataError(RuntimeError):
    """The mart lacks the market data required to build MarketInputs."""


# --------------------------------------------------------------------------- helpers
def _fetch_dicts(cur: duckdb.DuckDBPyConnection, sql: str, params: list | None = None):
    res = cur.execute(sql, params or [])
    cols = [d[0] for d in res.description]
    return [dict(zip(cols, row, strict=True)) for row in res.fetchall()]


def representative_year(cur: duckdb.DuckDBPyConnection) -> int:
    """Latest calendar year with a complete hourly series in prices_hourly."""
    rows = cur.execute(
        "SELECT year(ts) AS y, count(*) AS n FROM prices_hourly GROUP BY 1 ORDER BY y DESC"
    ).fetchall()
    for y, n in rows:
        if n in (8760, 8784):
            return int(y)
    raise MarketDataError(
        "prices_hourly has no complete calendar year (8760/8784 hours) — "
        "re-run the SMARD pipeline ('make data')."
    )


# --------------------------------------------------------------------------- inputs
def _build_market_inputs(cur: duckdb.DuckDBPyConnection, farm_id: str) -> MarketInputs:
    year = representative_year(cur)
    price_rows = cur.execute(
        "SELECT ts, eur_mwh FROM prices_hourly WHERE year(ts) = ? ORDER BY ts", [year]
    ).fetchall()
    prices = [float(r[1]) for r in price_rows]
    hour_month = [r[0].month - 1 for r in price_rows]
    n = len(prices)
    notes = [f"day-ahead DE/LU hourly prices, calendar year {year} (SMARD, mart.prices_hourly)"]

    # cf shape: cached hourly CF for Path A farms, else FLAT normalized shape
    cf_shape: list[float]
    try:
        cf_rows = cur.execute(
            "SELECT cf FROM cf_hourly WHERE farm_id = ? AND year(ts) = ? ORDER BY ts",
            [farm_id, year],
        ).fetchall()
    except duckdb.CatalogException:
        cf_rows = []
    cf_values = [float(r[0]) for r in cf_rows]
    total = sum(cf_values)
    if len(cf_values) == n and total > 0:
        cf_shape = [v / total for v in cf_values]
        notes.append(f"cf_shape from mart.cf_hourly {year} (Path A)")
    else:
        cf_shape = [1.0 / n] * n
        notes.append("cf_shape FLAT (no cached hourly CF for this farm — Path B fallback)")

    # marktwerte: the representative year's 12 rows, else latest 12 available
    mw_rows = cur.execute(
        "SELECT month, mw_wind_onshore_ct_kwh FROM marktwerte WHERE year(month) = ? ORDER BY month",
        [year],
    ).fetchall()
    if len(mw_rows) == 12:
        notes.append(f"Marktwerte Wind an Land, 12 months of {year} (Netztransparenz)")
    else:
        mw_rows = cur.execute(
            "SELECT month, mw_wind_onshore_ct_kwh FROM ("
            "  SELECT month, mw_wind_onshore_ct_kwh FROM marktwerte ORDER BY month DESC LIMIT 12"
            ") ORDER BY month"
        ).fetchall()
        if len(mw_rows) < 12:
            raise MarketDataError(
                f"marktwerte has only {len(mw_rows)} monthly rows; 12 are required — "
                "re-run the Netztransparenz pipeline ('make data')."
            )
        notes.append(
            f"Marktwerte {year} incomplete — using latest 12 published months "
            f"({mw_rows[0][0]}..{mw_rows[-1][0]}, Netztransparenz)"
        )
    marktwerte = [float(r[1]) for r in mw_rows]

    return MarketInputs(
        price_eur_mwh_hourly=prices,
        cf_shape_hourly=cf_shape,
        hour_month=hour_month,
        marktwert_ct_kwh_by_month=marktwerte,
        price_year=year,
        source_note="; ".join(notes),
    )


@lru_cache(maxsize=64)
def _market_inputs_cached(mart_key: str, farm_id: str) -> MarketInputs:
    return _build_market_inputs(deps.get_conn(), farm_id)


def market_inputs(farm_id: str) -> MarketInputs:
    """Cached MarketInputs for a farm (cache key includes the mart path)."""
    return _market_inputs_cached(str(deps.mart_path().resolve()), farm_id)


def reset_cache() -> None:
    _market_inputs_cached.cache_clear()


# --------------------------------------------------------------------------- vintages
def _iso(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime | date):
        return v.isoformat()
    return str(v)


def vintages(cur: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Max timestamps of the market tables — health endpoint + gate freshness."""
    out: dict[str, Any] = {"prices_max_ts": None, "marktwerte_max_month": None}
    try:
        out["prices_max_ts"] = cur.execute("SELECT max(ts) FROM prices_hourly").fetchone()[0]
    except duckdb.CatalogException:
        pass
    try:
        out["marktwerte_max_month"] = cur.execute("SELECT max(month) FROM marktwerte").fetchone()[0]
    except duckdb.CatalogException:
        pass
    return out


# --------------------------------------------------------------------------- chart payload
def chart_payload(cur: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Revenue-tab chart data: daily mean prices, monthly Marktwerte, neg hours/yr."""
    year = representative_year(cur)
    daily = _fetch_dicts(
        cur,
        "SELECT date_trunc('day', ts)::DATE AS t, avg(eur_mwh) AS v "
        "FROM prices_hourly WHERE year(ts) = ? GROUP BY 1 ORDER BY 1",
        [year],
    )
    marktwerte = _fetch_dicts(
        cur,
        "SELECT month AS t, mw_wind_onshore_ct_kwh AS v FROM marktwerte ORDER BY month",
    )
    neg = _fetch_dicts(
        cur,
        "SELECT year(ts) AS year, count(*) AS hours FROM prices_hourly "
        "WHERE eur_mwh < 0 GROUP BY 1 ORDER BY 1",
    )
    return {
        "representative_year": year,
        "daily": [{"t": _iso(r["t"]), "v": round(float(r["v"]), 2)} for r in daily],
        "marktwerte": [{"t": _iso(r["t"]), "v": float(r["v"])} for r in marktwerte],
        "neg_hours_by_year": [{"year": int(r["year"]), "hours": int(r["hours"])} for r in neg],
    }


# --------------------------------------------------------------------------- cost vintages
@dataclass(frozen=True)
class CostVintage:
    vintage_year: int
    capex_eur_per_mw: float
    opex_fixed_eur_per_mw_yr: float
    interest_rate: float


@lru_cache(maxsize=1)
def _cost_vintages() -> dict[int, CostVintage]:
    path = deps.repo_root() / "data" / "manual" / "cost_vintages.csv"
    if not path.exists():
        raise MarketDataError(f"cost vintage table missing: {path}")
    table: dict[int, CostVintage] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            y = int(row["vintage_year"])
            table[y] = CostVintage(
                vintage_year=y,
                capex_eur_per_mw=float(row["capex_eur_per_mw"]),
                opex_fixed_eur_per_mw_yr=float(row["opex_fixed_eur_per_mw_yr"]),
                interest_rate=float(row["interest_rate"]),
            )
    if not table:
        raise MarketDataError(f"cost vintage table is empty: {path}")
    return table


def cost_vintage(commissioning_year: int) -> CostVintage:
    """Per-vintage capex/opex/rate, commissioning year clamped to the table range."""
    table = _cost_vintages()
    year = min(max(commissioning_year, min(table)), max(table))
    return table[year]


# --------------------------------------------------------------------------- auction awards
@lru_cache(maxsize=1)
def _auction_awards_by_year() -> dict[int, float]:
    """Volume-weighted average Ø-Zuschlagswert (ct/kWh) per calendar year, from
    the hand-compiled BNetzA ground truth (data/manual/bnetza_onshore_auctions.csv)."""
    path = deps.repo_root() / "data" / "manual" / "bnetza_onshore_auctions.csv"
    if not path.exists():
        return {}
    sums: dict[int, tuple[float, float]] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not row.get("avg_award_ct_kwh") or not row.get("volume_awarded_mw"):
                continue
            year = int(row["round_date"][:4])
            vol = float(row["volume_awarded_mw"])
            wsum, vsum = sums.get(year, (0.0, 0.0))
            sums[year] = (wsum + float(row["avg_award_ct_kwh"]) * vol, vsum + vol)
    return {y: round(w / v, 3) for y, (w, v) in sums.items() if v > 0}


def auction_award_ct_kwh(commissioning_year: int) -> float | None:
    """Real award-price default for the farm's AW: the volume-weighted average
    across the BNetzA rounds ~2 years before commissioning (typical realization
    lag), falling back to the commissioning year itself, then adjacent years.
    None for pre-auction-era farms (engine then solves the break-even bid).
    """
    awards = _auction_awards_by_year()
    if not awards:
        return None
    for candidate in (
        commissioning_year - 2,
        commissioning_year - 1,
        commissioning_year,
        commissioning_year - 3,
        commissioning_year + 1,
    ):
        if candidate in awards:
            return awards[candidate]
    return None
