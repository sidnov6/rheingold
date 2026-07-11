"""API routes (spec §10). Thin: mart reads + engine calls, no business logic."""

from __future__ import annotations

import json
import os
from typing import Any

import duckdb
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from rheingold_engine.config import assumptions_from_defaults
from rheingold_engine.models import FarmInput, Shocks, UnderwriteResult
from rheingold_engine.underwrite import underwrite
from sse_starlette.sse import EventSourceResponse

from . import deps, eeg51, market
from .memo_stream import memo_event_stream

router = APIRouter(prefix="/api")

MASTR_PUBLIC_URL = "https://www.marktstammdatenregister.de/MaStR"
#: Method → CF-uncertainty sigma (spec §8.2.2): Path A (ninja) 0.06, Path B (GWA) 0.09.
_METHOD_SIGMA = {"gwa_windpowerlib": 0.09, "ninja": 0.06}


def _fetch_one(cur: duckdb.DuckDBPyConnection, sql: str, params: list) -> dict[str, Any] | None:
    res = cur.execute(sql, params)
    cols = [d[0] for d in res.description]
    row = res.fetchone()
    return dict(zip(cols, row, strict=True)) if row else None


def _conn_or_503() -> duckdb.DuckDBPyConnection:
    try:
        return deps.get_conn()
    except deps.MartMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ------------------------------------------------------------------ fleet
@router.get("/fleet")
def get_fleet() -> FileResponse:
    path = deps.mart_dir() / "fleet.json.gz"
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"fleet.json.gz not found at {path} — run 'make data' to build the mart.",
        )
    return FileResponse(
        path,
        media_type="application/json",
        headers={
            "Content-Encoding": "gzip",
            "Cache-Control": "public, max-age=86400, immutable",
        },
    )


@router.get("/fleet/meta")
def get_fleet_meta() -> JSONResponse:
    path = deps.mart_dir() / "fleet_meta.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="fleet_meta.json not found")
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


# ------------------------------------------------------------------ farm dossier
@router.get("/farm/{farm_id}")
def get_farm(farm_id: str) -> dict[str, Any]:
    cur = _conn_or_503()
    farm = _fetch_one(cur, "SELECT * FROM farms WHERE farm_id = ?", [farm_id])
    if farm is None:
        raise HTTPException(status_code=404, detail=f"no farm with id '{farm_id}' in the mart")
    resource = _fetch_one(cur, "SELECT * FROM resource WHERE farm_id = ?", [farm_id])

    unit_ids: list[str] = json.loads(farm.get("unit_ids") or "[]")
    units: list[dict[str, Any]] = []
    if unit_ids:
        placeholders = ", ".join("?" for _ in unit_ids)
        res = cur.execute(
            f"SELECT * FROM units WHERE unit_id IN ({placeholders}) ORDER BY unit_id", unit_ids
        )
        cols = [d[0] for d in res.description]
        units = [dict(zip(cols, row, strict=True)) for row in res.fetchall()]

    sources: list[dict[str, Any]] = [
        {
            "label": "MaStR Registereintrag",
            "unit_id": uid,
            "url": MASTR_PUBLIC_URL,
            "note": (
                "Public MaStR search — look up this unit id "
                "(detail pages have no stable public deep link)."
            ),
        }
        for uid in unit_ids
    ]
    if resource is not None:
        sources.append(
            {
                "label": f"Wind resource ({resource.get('method')})",
                "unit_id": None,
                "url": None,
                "note": resource.get("source"),
            }
        )
    # FarmDetail contract (apps/web/lib/types.ts): FLAT farm fields + nested
    # resource + sources[{label,url}] + unit_ids list. `units` rides along as extra.
    detail = _jsonable(farm)
    detail.pop("unit_ids", None)
    detail["unit_ids"] = unit_ids
    detail["resource"] = _jsonable(resource)
    detail["sources"] = [
        {"label": s["label"], "url": s["url"], "license": s.get("note")} for s in sources
    ]
    detail["units"] = _jsonable(units)
    return detail


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


# ------------------------------------------------------------------ underwrite
class UnderwriteRequest(BaseModel):
    farm_id: str
    assumptions_overrides: dict[str, Any] | None = None
    shocks: dict[str, Any] | None = None


def build_underwrite(body: UnderwriteRequest) -> UnderwriteResult:
    """farms+resource row → FarmInput, vintage-aware Assumptions, cached MarketInputs."""
    cur = _conn_or_503()
    farm_row = _fetch_one(cur, "SELECT * FROM farms WHERE farm_id = ?", [body.farm_id])
    if farm_row is None:
        raise HTTPException(status_code=404, detail=f"no farm with id '{body.farm_id}'")
    resource = _fetch_one(cur, "SELECT * FROM resource WHERE farm_id = ?", [body.farm_id])
    if resource is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"no resource row for farm '{body.farm_id}' — the wind-resource pipeline "
                "(data/pipelines, Path A ninja or Path B GWA+windpowerlib) has not produced "
                "a P50 capacity factor for this farm yet. Run 'make data' or pick a farm "
                "with resource coverage."
            ),
        )
    if farm_row.get("commissioning_year") is None:
        raise HTTPException(
            status_code=422,
            detail=f"farm '{body.farm_id}' has no commissioning_year in MaStR — "
            "cost vintage and §51 cohort cannot be determined.",
        )

    year = int(farm_row["commissioning_year"])
    method = resource.get("method")
    farm = FarmInput(
        farm_id=farm_row["farm_id"],
        name=farm_row["name"],
        lat=farm_row["lat"],
        lon=farm_row["lon"],
        mw_total=farm_row["mw_total"],
        n_units=farm_row["n_units"],
        turbine_type=farm_row.get("turbine_type"),
        hub_height_m=farm_row.get("hub_height_m"),
        rotor_d_m=farm_row.get("rotor_d_m"),
        commissioning_year=year,
        bundesland=farm_row.get("bundesland") or "unbekannt",
        p50_cf=float(resource["p50_cf"]),
        cf_uncertainty_sigma=_METHOD_SIGMA.get(method, 0.10),
    )

    vintage = market.cost_vintage(year)
    # AW default: the REAL volume-weighted average award of the farm's
    # commissioning-year BNetzA rounds (auction era, 2017+). Pre-auction farms
    # fall back to the engine's break-even solve. Users can always override.
    aw_default = market.auction_award_ct_kwh(year)
    overrides: dict[str, Any] = {
        "capex_eur_per_mw": vintage.capex_eur_per_mw,
        "opex_fixed_eur_per_mw_yr": vintage.opex_fixed_eur_per_mw_yr,
        "interest_rate": vintage.interest_rate,
        "neg_price_rule_hours": eeg51.neg_price_rule_hours(year),
        "anzulegender_wert_ct_kwh": aw_default,  # None → engine break-even solve
    }
    overrides.update(body.assumptions_overrides or {})

    try:
        assumptions = assumptions_from_defaults(overrides)
        shocks = Shocks(**(body.shocks or {}))
        market_inputs = market.market_inputs(body.farm_id)
        try:
            return underwrite(farm, assumptions, market_inputs, shocks)
        except ValueError as exc:
            user_set_aw = "anzulegender_wert_ct_kwh" in (body.assumptions_overrides or {})
            if aw_default is None and not user_set_aw and "break-even" in str(exc):
                # Pre-auction-era farm whose break-even sits below the bracket at
                # current price levels: underwrite as a merchant project instead.
                # The historical statutory EEG tariff is NOT modeled (MODEL_CARD);
                # the evidence store shows revenue_mode=merchant transparently.
                assumptions = assumptions.model_copy(update={"revenue_mode": "merchant"})
                return underwrite(farm, assumptions, market_inputs, shocks)
            raise
    except market.MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/underwrite")
def post_underwrite(body: UnderwriteRequest) -> dict[str, Any]:
    return build_underwrite(body).model_dump()


# ------------------------------------------------------------------ market charts
@router.get("/market")
def get_market(farm_id: str | None = None) -> dict[str, Any]:
    cur = _conn_or_503()
    try:
        return market.chart_payload(cur)
    except market.MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ------------------------------------------------------------------ memo (SSE)
@router.post("/memo")
@deps.limiter.limit("5/minute")
async def post_memo(request: Request, body: UnderwriteRequest) -> EventSourceResponse:
    return EventSourceResponse(memo_event_stream(body))


# ------------------------------------------------------------------ backtest
@router.get("/backtest")
def get_backtest() -> JSONResponse:
    path = deps.mart_dir() / "backtest.json"
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"backtest.json not found at {path} — run 'make backtest' to produce it.",
        )
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


# ------------------------------------------------------------------ health
@router.get("/health")
def get_health() -> dict[str, Any]:
    """Build sha + data vintages. Never 500s: absent mart → null vintages."""
    data_vintages: dict[str, Any] = {
        "prices_max_ts": None,
        "marktwerte_max_month": None,
        "mastr_snapshot": None,
    }
    try:
        cur = deps.get_conn()
        v = market.vintages(cur)
        data_vintages["prices_max_ts"] = _jsonable(v["prices_max_ts"])
        data_vintages["marktwerte_max_month"] = _jsonable(v["marktwerte_max_month"])
    except Exception:  # noqa: BLE001 — health must never fail
        pass
    try:
        units_meta = deps.mart_dir() / "units_meta.json"
        if units_meta.exists():
            meta = json.loads(units_meta.read_text(encoding="utf-8"))
            data_vintages["mastr_snapshot"] = meta.get("mastr_snapshot_date") or meta.get(
                "snapshot_date"
            )
    except Exception:  # noqa: BLE001
        pass
    return {
        "sha": os.environ.get("GIT_SHA", "dev"),
        "data_vintages": data_vintages,
        "showcase": False,
    }
