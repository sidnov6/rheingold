"""Auction backtest (spec §12): does the engine's break-even bid reproduce
observed BNetzA onshore clearing prices 2017–2026?

Method per §12: for each auction round, sample N=40 farms commissioned in
[round_year, round_year+2] (proxy for the round's project pipeline), stratified
by Bundesland wind class (north/center/south); per-round assumptions from
data/manual/cost_vintages.csv; resource via Path B (mart resource table,
uniform method across years — comparability beats precision); solve the
break-even AW at a 7 % equity hurdle; compare the median and P25–P75 band with
the actual Ø-Zuschlagswert. Reports MAE (ct/kWh) and the directional hit-rate.

Deterministic: sampling uses a fixed seed. Reads local parquet/CSV only —
no network. Run via `make backtest`; output feeds /backtest in the web app.

Documented simplifications (also on the /backtest page): uniform representative
price year across all rounds (the market-premium mechanism makes the break-even
bid mostly price-year-independent during support); flat hourly generation shape
(Path B has no hourly profile), which weights §51 hours by time rather than
production and sets capture ≈ 1 for the merchant tail.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .config import assumptions_from_defaults
from .models import FarmInput, MarketInputs
from .underwrite import solve_breakeven_bid

SEED = 42
N_PER_ROUND = 40
HURDLE = 0.07  # §12.3
PATH_B_SIGMA = 0.09

NORTH = {"Schleswig-Holstein", "Niedersachsen", "Mecklenburg-Vorpommern", "Bremen", "Hamburg"}
SOUTH = {"Bayern", "Baden-Württemberg"}


def wind_class(bundesland: str | None) -> str:
    if bundesland in NORTH:
        return "north"
    if bundesland in SOUTH:
        return "south"
    return "center"


def neg_rule_hours_for_round(round_date: str) -> int:
    """§51 cohort by tender award date (MODEL_CARD table)."""
    d = dt.date.fromisoformat(round_date)
    if d < dt.date(2021, 1, 1):
        return 6
    if d < dt.date(2023, 1, 1):
        return 4
    if d < dt.date(2025, 2, 25):
        return 1  # stepdown cohort, steady state 2027+
    return 0  # every negative hour


def build_market_inputs(mart_dir: Path) -> MarketInputs:
    """Representative market year from the mart parquet (latest complete calendar year)."""
    prices = pd.read_parquet(mart_dir / "prices_hourly.parquet")
    prices["ts"] = pd.to_datetime(prices["ts"])
    counts = prices.groupby(prices["ts"].dt.year).size()
    complete = [int(y) for y, n in counts.items() if n >= 8760]
    if not complete:
        raise RuntimeError("no complete calendar year in prices_hourly — run download_smard.py")
    year = max(complete)
    py = prices[prices["ts"].dt.year == year].sort_values("ts")
    # drop leap-day extra hours beyond 8784 handling: keep as-is (8760 or 8784)
    hourly = py["eur_mwh"].tolist()
    months = (py["ts"].dt.month - 1).tolist()

    mw = pd.read_parquet(mart_dir / "marktwerte.parquet")
    mw["month"] = pd.to_datetime(mw["month"])
    mw_year = mw[mw["month"].dt.year == year].sort_values("month")
    if len(mw_year) < 12:
        mw_year = mw.sort_values("month").tail(12)
    mw_monthly = mw_year["mw_wind_onshore_ct_kwh"].tolist()[:12]

    n = len(hourly)
    return MarketInputs(
        price_eur_mwh_hourly=hourly,
        cf_shape_hourly=[1.0 / n] * n,
        hour_month=months,
        marktwert_ct_kwh_by_month=mw_monthly,
        price_year=year,
        source_note=f"SMARD {year} hourly day-ahead DE/LU; Marktwerte netztransparenz.de {year}; flat shape (Path B)",
    )


def sample_round_farms(
    farms: pd.DataFrame, round_year: int, rng: np.random.Generator
) -> pd.DataFrame:
    pool = farms[
        (farms["commissioning_year"] >= round_year)
        & (farms["commissioning_year"] <= round_year + 2)
        & farms["p50_cf"].notna()
        & (farms["mw_total"] >= 3.0)  # §51 6h-rule aggregation floor; excludes micro-singletons
    ]
    if pool.empty:
        return pool
    # stratified: proportional by wind class, at least 1 per non-empty class
    takes = []
    for cls, group in pool.groupby(pool["bundesland"].map(wind_class)):
        share = len(group) / len(pool)
        k = min(len(group), max(1, round(N_PER_ROUND * share)))
        takes.append(group.sample(n=k, random_state=int(rng.integers(0, 2**32 - 1))))
    sampled = pd.concat(takes)
    if len(sampled) > N_PER_ROUND:
        sampled = sampled.sample(n=N_PER_ROUND, random_state=int(rng.integers(0, 2**32 - 1)))
    return sampled


def run_backtest(
    farms_with_resource: pd.DataFrame,
    auctions: pd.DataFrame,
    vintages: pd.DataFrame,
    market: MarketInputs,
    n_per_round: int = N_PER_ROUND,
) -> dict:
    rng = np.random.default_rng(SEED)
    vint = vintages.set_index("vintage_year")
    rounds_out = []
    for _, row in auctions.sort_values("round_date").iterrows():
        round_year = int(str(row["round_date"])[:4])
        vy = min(max(round_year, int(vint.index.min())), int(vint.index.max()))
        v = vint.loc[vy]
        sampled = sample_round_farms(farms_with_resource, round_year, rng)
        if sampled.empty:
            continue
        if n_per_round != N_PER_ROUND and len(sampled) > n_per_round:
            sampled = sampled.head(n_per_round)
        bids = []
        for _, f in sampled.iterrows():
            farm = FarmInput(
                farm_id=str(f["farm_id"]),
                name=str(f["name"]),
                lat=float(f["lat"]),
                lon=float(f["lon"]),
                mw_total=float(f["mw_total"]),
                n_units=int(f["n_units"]),
                turbine_type=None if pd.isna(f.get("turbine_type")) else str(f["turbine_type"]),
                hub_height_m=None if pd.isna(f.get("hub_height_m")) else float(f["hub_height_m"]),
                rotor_d_m=None if pd.isna(f.get("rotor_d_m")) else float(f["rotor_d_m"]),
                commissioning_year=int(f["commissioning_year"]),
                bundesland=str(f["bundesland"]) if pd.notna(f["bundesland"]) else "unbekannt",
                p50_cf=float(f["p50_cf"]),
                cf_uncertainty_sigma=PATH_B_SIGMA,
            )
            assumptions = assumptions_from_defaults(
                {
                    "capex_eur_per_mw": float(v["capex_eur_per_mw"]),
                    "opex_fixed_eur_per_mw_yr": float(v["opex_fixed_eur_per_mw_yr"]),
                    "interest_rate": float(v["interest_rate"]),
                    "equity_target_irr": HURDLE,
                    "neg_price_rule_hours": neg_rule_hours_for_round(str(row["round_date"])),
                    "anzulegender_wert_ct_kwh": None,
                }
            )
            try:
                bid = solve_breakeven_bid(farm, assumptions, market, shocks=_no_shocks())
            except ValueError:
                bid = None
            if bid is not None:
                bids.append(bid)
        if len(bids) < 5:
            print(
                f"  {row['round_date']}: only {len(bids)} solvable bids — skipping round",
                file=sys.stderr,
            )
            continue
        arr = np.sort(np.array(bids))
        rounds_out.append(
            {
                "round_date": str(row["round_date"]),
                "avg_award_ct_kwh": float(row["avg_award_ct_kwh"])
                if pd.notna(row["avg_award_ct_kwh"])
                else None,
                "max_price_ct_kwh": float(row["max_price_ct_kwh"])
                if pd.notna(row["max_price_ct_kwh"])
                else None,
                "model_median_ct_kwh": round(float(np.median(arr)), 3),
                "model_p25_ct_kwh": round(float(np.percentile(arr, 25)), 3),
                "model_p75_ct_kwh": round(float(np.percentile(arr, 75)), 3),
                "n_farms": int(len(bids)),
            }
        )

    paired = [r for r in rounds_out if r["avg_award_ct_kwh"] is not None]
    errors = [r["model_median_ct_kwh"] - r["avg_award_ct_kwh"] for r in paired]
    mae = float(np.mean(np.abs(errors))) if errors else float("nan")
    hits = 0
    moves = 0
    for prev, cur in zip(paired, paired[1:], strict=False):
        da = cur["avg_award_ct_kwh"] - prev["avg_award_ct_kwh"]
        dm = cur["model_median_ct_kwh"] - prev["model_median_ct_kwh"]
        if da == 0:
            continue
        moves += 1
        if da * dm > 0:
            hits += 1
    return {
        "rounds": rounds_out,
        "mae_ct_kwh": round(mae, 3),
        "directional_hit_rate": round(hits / moves, 3) if moves else None,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "method_note": (
            f"N≤{N_PER_ROUND} farms/round commissioned in [Y, Y+2], stratified by Bundesland wind "
            f"class; Path B resource (GWA + power curve); vintage costs from WindGuard series; "
            f"break-even AW at {HURDLE:.0%} equity IRR; representative market year "
            f"{market.price_year} (flat hourly shape); §51 cohort by round date; seed {SEED}."
        ),
    }


def _no_shocks():
    from .models import Shocks

    return Shocks()


def main() -> int:
    parser = argparse.ArgumentParser(description="RHEINGOLD auction backtest (§12)")
    parser.add_argument("--out", default="data/mart/backtest.json")
    parser.add_argument("--mart", default="data/mart")
    parser.add_argument("--manual", default="data/manual")
    parser.add_argument("--rounds", type=int, default=None, help="limit to first N rounds (smoke)")
    args = parser.parse_args()

    mart = Path(args.mart)
    manual = Path(args.manual)
    for req in ["farms.parquet", "resource.parquet", "prices_hourly.parquet", "marktwerte.parquet"]:
        if not (mart / req).exists():
            print(f"ERROR: {mart / req} missing — run `make data` first", file=sys.stderr)
            return 2

    farms = pd.read_parquet(mart / "farms.parquet")
    resource = pd.read_parquet(mart / "resource.parquet")
    fw = farms.merge(resource[["farm_id", "p50_cf"]], on="farm_id", how="left")
    auctions = pd.read_csv(manual / "bnetza_onshore_auctions.csv")
    if args.rounds:
        auctions = auctions.sort_values("round_date").head(args.rounds)
    vintages = pd.read_csv(manual / "cost_vintages.csv")
    market = build_market_inputs(mart)

    result = run_backtest(fw, auctions, vintages, market)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print(
        f"backtest: {len(result['rounds'])} rounds, MAE {result['mae_ct_kwh']} ct/kWh, "
        f"directional hit-rate {result['directional_hit_rate']}",
        file=sys.stderr,
    )
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
