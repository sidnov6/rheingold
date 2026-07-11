"""Pydantic I/O contracts for the RHEINGOLD engine (spec §8.1).

The engine is PURE: every function is a deterministic map from these models to
UnderwriteResult. All money in EUR, energy in MWh, prices in EUR/MWh internally;
ct/kWh converts at the boundary (1 ct/kWh = 10 EUR/MWh). Annual periodicity for
debt/DCF; hourly only inside revenue shaping.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

CT_KWH_TO_EUR_MWH = 10.0


class FarmInput(BaseModel):
    farm_id: str
    name: str
    lat: float
    lon: float
    mw_total: float
    n_units: int
    turbine_type: str | None = None
    hub_height_m: float | None = None
    rotor_d_m: float | None = None
    commissioning_year: int
    bundesland: str
    p50_cf: float  # from mart.resource — gross single-turbine CF before farm losses
    cf_uncertainty_sigma: float = 0.10  # method sigma (§8.2.2): Path A 0.06, Path B 0.09


class Assumptions(BaseModel):
    """Every field defaulted from §8.9 / defaults.yaml, all overridable."""

    lifetime_years: int = 25
    availability: float = 0.97  # energy availability — Suzlon-informed default
    electrical_losses: float = 0.02
    wake_losses: float = (
        0.06  # farm-level if CF is single-turbine based; 0 if CF already farm-level
    )
    curtailment_redispatch: float = 0.02
    degradation_pa: float = 0.002
    capex_eur_per_mw: float = 1_650_000.0
    opex_fixed_eur_per_mw_yr: float = 55_000.0
    opex_variable_eur_per_mwh: float = 0.0
    land_lease_pct_revenue: float = 0.06
    municipal_participation_ct_kwh: float = 0.2  # EEG §6 toggle, on by default
    municipal_participation_enabled: bool = True
    inflation_pa: float = 0.02
    # Revenue mode
    revenue_mode: Literal["eeg_premium", "merchant", "ppa"] = "eeg_premium"
    anzulegender_wert_ct_kwh: float | None = None  # award price; None → break-even solve
    ppa_price_eur_mwh: float | None = None
    eeg_support_years: int = 20
    neg_price_rule_hours: int = 4  # §51 config: 4/3/2/1/0(=all negative hrs excluded)
    merchant_tail: bool = True  # years 21–25 at capture price
    # Financing
    target_dscr: float = 1.30
    max_gearing: float = 0.75
    debt_tenor_years: int = 18
    interest_rate: float = 0.045
    dsra_months: int = 6
    # Valuation
    wacc: float = 0.058
    equity_target_irr: float = 0.08
    tax_rate: float = 0.30
    depreciation_years: int = 16


class MarketInputs(BaseModel):
    """Representative-year hourly market data, built by the data/API layer.

    The engine never fetches: it receives one representative hourly year of prices
    plus the farm's normalized hourly generation shape, and a per-project-year
    price-level path. Deterministic transforms only.
    """

    price_eur_mwh_hourly: list[float]  # representative calendar year, len 8760/8784
    cf_shape_hourly: list[float]  # same length, sums to 1.0 — share of annual energy per hour
    hour_month: list[int]  # month index 0..11 per hour (calendar of the representative year)
    marktwert_ct_kwh_by_month: list[float]  # len 12 — MW Wind an Land reference
    price_path: list[float] | None = (
        None  # multiplicative price level per project year; None → all 1.0
    )
    price_year: int | None = None  # calendar year the hourly series comes from (provenance)
    source_note: str = ""

    @model_validator(mode="after")
    def _check_lengths(self) -> MarketInputs:
        n = len(self.price_eur_mwh_hourly)
        if n not in (8760, 8784):
            raise ValueError(f"hourly price series must be one calendar year, got {n} hours")
        if len(self.cf_shape_hourly) != n or len(self.hour_month) != n:
            raise ValueError("price, cf shape and hour_month series must have equal length")
        if len(self.marktwert_ct_kwh_by_month) != 12:
            raise ValueError("marktwert_ct_kwh_by_month must have 12 entries")
        s = sum(self.cf_shape_hourly)
        if abs(s - 1.0) > 1e-6:
            raise ValueError(f"cf_shape_hourly must sum to 1.0, got {s}")
        return self

    @classmethod
    def flat(
        cls,
        price_eur_mwh: float = 50.0,
        marktwert_ct_kwh: float = 5.0,
        n_hours: int = 8760,
    ) -> MarketInputs:
        """Uniform-price, uniform-shape market — used by tests and simple Path B mode."""
        hours_per_month = n_hours // 12
        hour_month = [min(h // hours_per_month, 11) for h in range(n_hours)]
        return cls(
            price_eur_mwh_hourly=[price_eur_mwh] * n_hours,
            cf_shape_hourly=[1.0 / n_hours] * n_hours,
            hour_month=hour_month,
            marktwert_ct_kwh_by_month=[marktwert_ct_kwh] * 12,
            source_note="synthetic flat market (test artifact)",
        )


class Shocks(BaseModel):
    """Scenario shock vector (§8.8). All multiplicative/additive deltas off base."""

    price_level: float = 0.0  # ±0.40 → prices ×(1+x)
    price_years: int | None = None  # None → whole life; else first N years only
    production_delta: float = 0.0  # ±0.15 → energy ×(1+x)
    production_years: int | None = None
    rate_delta_bps: float = 0.0  # ±300
    wacc_delta_bps: float = 0.0
    capex_delta: float = 0.0  # ±0.25
    availability_override: float | None = None  # 0.90–0.99
    curtailment_override: float | None = None  # 0.0–0.10
    negative_hours_multiplier: float = 1.0  # §51 streak-loss scaling


class AnnualSeries(BaseModel):
    """Parallel annual arrays, year 1..lifetime (calendar offset from commissioning)."""

    year: list[int]
    energy_mwh: list[float]
    revenue_market: list[float]
    revenue_premium: list[float]
    revenue_total: list[float]
    opex_fixed: list[float]
    opex_variable: list[float]
    land_lease: list[float]
    municipal_participation: list[float]
    opex_total: list[float]
    ebitda: list[float]
    depreciation: list[float]
    tax: list[float]
    cfads: list[float]
    debt_balance_bop: list[float]
    interest: list[float]
    principal: list[float]
    debt_service: list[float]
    dscr: list[float | None]  # None outside tenor
    llcr: list[float | None]
    equity_cf: list[float]

    @model_validator(mode="after")
    def _equal_lengths(self) -> AnnualSeries:
        n = len(self.year)
        for name, values in self.__dict__.items():
            if isinstance(values, list) and len(values) != n:
                raise ValueError(f"annual series '{name}' has length {len(values)} != {n}")
        return self


class UncertaintyStackRow(BaseModel):
    component: str
    sigma: float
    included_in_p90: bool
    note: str = ""


class EnergyResult(BaseModel):
    p50_gwh: float
    p75_gwh: float
    p90_gwh: float
    p90_1yr_gwh: float  # includes inter-annual variability, reported separately
    net_cf: float
    sigma_total: float
    uncertainty_stack: list[UncertaintyStackRow]


class DebtResult(BaseModel):
    debt_capacity_eur: float  # pre-cap PV of sculpted DS
    debt_drawn_eur: float  # after gearing cap
    gearing: float
    gearing_cap_binding: bool
    dsra_eur: float
    min_dscr: float
    avg_dscr: float
    llcr: float
    plcr: float


class ValuationResult(BaseModel):
    lcoe_eur_mwh: float
    npv_wacc_eur: float
    equity_irr: float | None  # None when IRR does not exist
    equity_invested_eur: float
    payback_year: int | None
    breakeven_bid_ct_kwh: float | None  # None outside brentq bracket [2, 12]
    capture_rate: float
    p90_min_dscr: float  # min DSCR when energy at P90 — compliance-gate input


class TornadoItem(BaseModel):
    variable: str
    label: str
    low_input: str  # human-readable, e.g. "−20%"
    high_input: str
    irr_low: float | None
    irr_high: float | None


class EvidenceItem(BaseModel):
    """One entry in the EvidenceStore (§9.5). Agents may only cite these ids."""

    id: str
    type: Literal["computed", "assumption", "source"]
    label: str
    value: float | str
    unit: str = ""
    formula_ref: str | None = None
    inputs: list[str] = Field(default_factory=list)
    url: str | None = None
    retrieved_at: str | None = None


class UnderwriteResult(BaseModel):
    farm: FarmInput
    assumptions: Assumptions
    shocks: Shocks
    annual: AnnualSeries
    energy: EnergyResult
    debt: DebtResult
    valuation: ValuationResult
    tornado: list[TornadoItem]
    evidence: list[EvidenceItem]
