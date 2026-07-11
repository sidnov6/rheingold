"""Underwriting orchestration (spec §8): the single pure entry point.

underwrite(farm, assumptions, market, shocks) -> UnderwriteResult

Tax circularity (§8.7): exactly two deterministic passes — sculpt on pre-tax
CFADS (=EBITDA), compute tax with that interest, re-sculpt once on after-tax
CFADS, then recompute tax with the final interest for reporting. Coverage
ratios are reported against the final CFADS.

AW = None in eeg_premium mode → the break-even bid (§8.6) is solved first and
the underwrite runs at that AW (a self-consistent deal at the hurdle rate).
"""

from __future__ import annotations

from scipy.optimize import brentq

from . import costs as costs_mod
from . import debt as debt_mod
from . import energy as energy_mod
from . import revenue as revenue_mod
from . import tax as tax_mod
from . import valuation as valuation_mod
from .evidence import build_evidence
from .models import (
    AnnualSeries,
    Assumptions,
    DebtResult,
    FarmInput,
    MarketInputs,
    Shocks,
    UnderwriteResult,
    ValuationResult,
)
from .scenarios import apply_capex_shock, apply_rate_shocks
from .sensitivity import tornado as tornado_mod

_BREAKEVEN_LO, _BREAKEVEN_HI = 2.0, 12.0


def _effective_life(a: Assumptions) -> int:
    """Project truncates at end of EEG support when the merchant tail is off."""
    if a.revenue_mode == "eeg_premium" and not a.merchant_tail:
        life = min(a.lifetime_years, a.eeg_support_years)
    else:
        life = a.lifetime_years
    if a.debt_tenor_years > life:
        raise ValueError(
            f"debt tenor ({a.debt_tenor_years}y) exceeds effective project life ({life}y); "
            "shorten the tenor or enable the merchant tail"
        )
    return life


def _pv(flows: list[float], rate: float) -> float:
    return sum(f / (1.0 + rate) ** (t + 1) for t, f in enumerate(flows))


class _Core:
    """Intermediate results of one deterministic pass through the engine."""

    def __init__(
        self, farm: FarmInput, a: Assumptions, market: MarketInputs, shocks: Shocks
    ) -> None:
        life = _effective_life(a)
        rate, wacc = apply_rate_shocks(a.interest_rate, a.wacc, shocks)
        capex = apply_capex_shock(a.capex_eur_per_mw * farm.mw_total, shocks)

        annual_mwh = energy_mod.annual_energy_mwh(farm, a, shocks, life)
        energy = energy_mod.energy_result(farm, a, shocks, annual_mwh)
        stats = revenue_mod.market_stats(market, a.neg_price_rule_hours)
        rev_market, rev_premium = revenue_mod.annual_revenue(
            annual_mwh, a, market, stats, shocks, a.anzulegender_wert_ct_kwh
        )
        rev_total = [m + p for m, p in zip(rev_market, rev_premium, strict=True)]
        cost = costs_mod.annual_costs(annual_mwh, rev_total, farm.mw_total, a)
        ebitda = [r - o for r, o in zip(rev_total, cost.opex_total, strict=True)]
        depreciation = tax_mod.depreciation_schedule(capex, a, life)

        # --- two-pass sculpt (§8.7) ---
        tenor = a.debt_tenor_years
        sched1 = debt_mod.sculpt(
            ebitda, life, tenor, rate, a.target_dscr, capex, a.max_gearing, a.dsra_months
        )
        tax1 = tax_mod.annual_tax(ebitda, depreciation, sched1.interest, a)
        cfads1 = [e - x for e, x in zip(ebitda, tax1, strict=True)]
        sched2 = debt_mod.sculpt(
            cfads1, life, tenor, rate, a.target_dscr, capex, a.max_gearing, a.dsra_months
        )
        tax_final = tax_mod.annual_tax(ebitda, depreciation, sched2.interest, a)
        cfads = [e - x for e, x in zip(ebitda, tax_final, strict=True)]

        # coverage ratios against final CFADS
        dscr: list[float | None] = []
        llcr: list[float | None] = []
        for t in range(life):
            ds_t = sched2.debt_service[t]
            dscr.append(cfads[t] / ds_t if t < tenor and ds_t > 0 else None)
            bop = sched2.balance_bop[t]
            if t < tenor and bop > 1e-6:
                llcr.append((_pv(cfads[t:tenor], rate) + sched2.dsra) / bop)
            else:
                llcr.append(None)
        dscr_vals = [d for d in dscr if d is not None]

        equity_cf = valuation_mod.equity_cash_flows(cfads, sched2.debt_service, tenor, sched2.dsra)
        equity_t0 = capex + sched2.dsra - sched2.debt_drawn
        irr = valuation_mod.equity_irr(equity_t0, equity_cf)

        self.farm, self.a, self.market, self.shocks = farm, a, market, shocks
        self.life, self.rate, self.wacc, self.capex = life, rate, wacc, capex
        self.annual_mwh, self.energy, self.stats = annual_mwh, energy, stats
        self.rev_market, self.rev_premium, self.rev_total = rev_market, rev_premium, rev_total
        self.cost, self.ebitda, self.depreciation = cost, ebitda, depreciation
        self.sched, self.tax, self.cfads = sched2, tax_final, cfads
        self.dscr, self.llcr, self.dscr_vals = dscr, llcr, dscr_vals
        self.equity_cf, self.equity_t0, self.irr = equity_cf, equity_t0, irr

    def p90_min_dscr(self) -> float:
        """Min DSCR with energy at P90, debt schedule held at P50 sizing (§9.4)."""
        if self.energy.p50_gwh <= 0:
            return 0.0
        ratio = self.energy.p90_gwh / self.energy.p50_gwh
        mwh_p90 = [e * ratio for e in self.annual_mwh]
        rev_m, rev_p = revenue_mod.annual_revenue(
            mwh_p90, self.a, self.market, self.stats, self.shocks, self.a.anzulegender_wert_ct_kwh
        )
        rev_t = [m + p for m, p in zip(rev_m, rev_p, strict=True)]
        cost = costs_mod.annual_costs(mwh_p90, rev_t, self.farm.mw_total, self.a)
        ebitda = [r - o for r, o in zip(rev_t, cost.opex_total, strict=True)]
        tax_p90 = tax_mod.annual_tax(ebitda, self.depreciation, self.sched.interest, self.a)
        cfads_p90 = [e - x for e, x in zip(ebitda, tax_p90, strict=True)]
        tenor = self.a.debt_tenor_years
        ratios = [
            cfads_p90[t] / self.sched.debt_service[t]
            for t in range(tenor)
            if self.sched.debt_service[t] > 0
        ]
        return min(ratios) if ratios else float("inf")


def _irr_at_aw(
    farm: FarmInput, a: Assumptions, market: MarketInputs, shocks: Shocks, aw: float
) -> float:
    """Equity IRR at a given AW (eeg_premium mode forced); −1 when undefined."""
    a_eeg = a.model_copy(update={"revenue_mode": "eeg_premium", "anzulegender_wert_ct_kwh": aw})
    core = _Core(farm, a_eeg, market, shocks)
    return core.irr if core.irr is not None else -1.0


def solve_breakeven_bid(
    farm: FarmInput, a: Assumptions, market: MarketInputs, shocks: Shocks
) -> float | None:
    """AW ∈ [2, 12] ct/kWh s.t. equity IRR = hurdle (§8.6); None outside bracket."""
    target = a.equity_target_irr

    def f(aw: float) -> float:
        return _irr_at_aw(farm, a, market, shocks, aw) - target

    try:
        f_lo, f_hi = f(_BREAKEVEN_LO), f(_BREAKEVEN_HI)
    except ValueError:
        return None
    if f_lo == 0.0:
        return _BREAKEVEN_LO
    if f_hi == 0.0:
        return _BREAKEVEN_HI
    if f_lo * f_hi > 0:
        return None
    return float(brentq(f, _BREAKEVEN_LO, _BREAKEVEN_HI, xtol=1e-10))


def _tornado_irr(
    farm: FarmInput, a: Assumptions, market: MarketInputs, shocks: Shocks
) -> float | None:
    try:
        return _Core(farm, a, market, shocks).irr
    except ValueError:
        return None


def underwrite(
    farm: FarmInput,
    assumptions: Assumptions,
    market: MarketInputs,
    shocks: Shocks | None = None,
) -> UnderwriteResult:
    shocks = shocks if shocks is not None else Shocks()
    a = assumptions

    breakeven: float | None
    tornado_assumptions = a
    if a.revenue_mode == "eeg_premium" and a.anzulegender_wert_ct_kwh is None:
        breakeven = solve_breakeven_bid(farm, a, market, shocks)
        if breakeven is None:
            raise ValueError(
                "no break-even AW in [2, 12] ct/kWh at the hurdle rate — "
                "provide anzulegender_wert_ct_kwh explicitly"
            )
        a = a.model_copy(update={"anzulegender_wert_ct_kwh": breakeven})
        # The tornado is anchored to the UNSHOCKED base (see sensitivity.py), so in
        # break-even mode its AW must be solved without scenario shocks — otherwise
        # the shock vector leaks into the "structural" sensitivities via the bid.
        unshocked_aw = breakeven
        if shocks != Shocks():
            unshocked_aw = solve_breakeven_bid(farm, tornado_assumptions, market, Shocks())
        if unshocked_aw is None:
            unshocked_aw = (
                breakeven  # degenerate: keep the deal computable, sensitivity approximate
            )
        tornado_assumptions = tornado_assumptions.model_copy(
            update={"anzulegender_wert_ct_kwh": unshocked_aw}
        )
    else:
        breakeven = solve_breakeven_bid(farm, a, market, shocks)
        tornado_assumptions = a

    core = _Core(farm, a, market, shocks)

    annual = AnnualSeries(
        year=list(range(1, core.life + 1)),
        energy_mwh=core.annual_mwh,
        revenue_market=core.rev_market,
        revenue_premium=core.rev_premium,
        revenue_total=core.rev_total,
        opex_fixed=core.cost.opex_fixed,
        opex_variable=core.cost.opex_variable,
        land_lease=core.cost.land_lease,
        municipal_participation=core.cost.municipal_participation,
        opex_total=core.cost.opex_total,
        ebitda=core.ebitda,
        depreciation=core.depreciation,
        tax=core.tax,
        cfads=core.cfads,
        debt_balance_bop=core.sched.balance_bop,
        interest=core.sched.interest,
        principal=core.sched.principal,
        debt_service=core.sched.debt_service,
        dscr=core.dscr,
        llcr=core.llcr,
        equity_cf=core.equity_cf,
    )

    debt = DebtResult(
        debt_capacity_eur=core.sched.debt_capacity,
        debt_drawn_eur=core.sched.debt_drawn,
        gearing=core.sched.debt_drawn / core.capex if core.capex > 0 else 0.0,
        gearing_cap_binding=core.sched.gearing_cap_binding,
        dsra_eur=core.sched.dsra,
        min_dscr=min(core.dscr_vals) if core.dscr_vals else float("inf"),
        avg_dscr=sum(core.dscr_vals) / len(core.dscr_vals) if core.dscr_vals else float("inf"),
        llcr=core.llcr[0] if core.llcr and core.llcr[0] is not None else float("inf"),
        plcr=(_pv(core.cfads, core.rate) + core.sched.dsra) / core.sched.debt_drawn
        if core.sched.debt_drawn > 0
        else float("inf"),
    )

    valuation = ValuationResult(
        lcoe_eur_mwh=valuation_mod.lcoe_eur_mwh(
            core.capex, core.cost.opex_total, core.annual_mwh, core.wacc
        ),
        npv_wacc_eur=valuation_mod.npv_unlevered(
            core.capex,
            core.ebitda,
            tax_mod.unlevered_tax(core.ebitda, core.depreciation, a),
            core.wacc,
        ),
        equity_irr=core.irr,
        equity_invested_eur=core.equity_t0,
        payback_year=valuation_mod.payback_year(core.equity_t0, core.equity_cf),
        breakeven_bid_ct_kwh=breakeven,
        capture_rate=core.stats.capture_rate,
        p90_min_dscr=core.p90_min_dscr(),
    )

    energy = core.energy
    tornado = tornado_mod(farm, tornado_assumptions, market, _tornado_irr)
    evidence = build_evidence(farm, a, shocks, annual, energy, debt, valuation)

    return UnderwriteResult(
        farm=farm,
        assumptions=a,
        shocks=shocks,
        annual=annual,
        energy=energy,
        debt=debt,
        valuation=valuation,
        tornado=tornado,
        evidence=evidence,
    )
