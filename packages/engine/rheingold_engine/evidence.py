"""EvidenceStore builder (spec §9.5).

Every scalar the agents may cite gets a stable id: E-INP-* (registry/resource
facts), E-ASM-* (assumptions), E-ENE-*/E-REV-*/E-DBT-*/E-VAL-* (computed, with
formula_ref and input links). Deterministically ordered by id — the output JSON
must be byte-stable across runs.
"""

from __future__ import annotations

from .models import (
    AnnualSeries,
    Assumptions,
    DebtResult,
    EnergyResult,
    EvidenceItem,
    FarmInput,
    Shocks,
    ValuationResult,
)


def _src(id_: str, label: str, value: float | str, unit: str = "") -> EvidenceItem:
    return EvidenceItem(id=id_, type="source", label=label, value=value, unit=unit)


def _asm(id_: str, label: str, value: float | str, unit: str = "") -> EvidenceItem:
    return EvidenceItem(id=id_, type="assumption", label=label, value=value, unit=unit)


def _cmp(
    id_: str,
    label: str,
    value: float | str,
    unit: str,
    formula_ref: str,
    inputs: list[str],
) -> EvidenceItem:
    return EvidenceItem(
        id=id_,
        type="computed",
        label=label,
        value=value,
        unit=unit,
        formula_ref=formula_ref,
        inputs=inputs,
    )


def build_evidence(
    farm: FarmInput,
    a: Assumptions,
    shocks: Shocks,
    annual: AnnualSeries,
    energy: EnergyResult,
    debt: DebtResult,
    valuation: ValuationResult,
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []

    # --- inputs (registry / resource facts) ---
    items += [
        _src("E-INP-MW", "Installed capacity (MaStR)", farm.mw_total, "MW"),
        _src("E-INP-N-UNITS", "Turbine count (MaStR)", float(farm.n_units), ""),
        _src("E-INP-CF-P50", "Gross P50 capacity factor (resource)", farm.p50_cf, ""),
        _src("E-INP-CF-SIGMA", "Resource method sigma", farm.cf_uncertainty_sigma, ""),
        _src(
            "E-INP-COMMISSIONING", "Commissioning year (MaStR)", float(farm.commissioning_year), ""
        ),
        _src("E-INP-BUNDESLAND", "Bundesland (MaStR)", farm.bundesland, ""),
    ]
    if farm.hub_height_m is not None:
        items.append(_src("E-INP-HUB-HEIGHT", "Hub height (MaStR)", farm.hub_height_m, "m"))
    if farm.rotor_d_m is not None:
        items.append(_src("E-INP-ROTOR", "Rotor diameter (MaStR)", farm.rotor_d_m, "m"))
    if farm.turbine_type is not None:
        items.append(_src("E-INP-TURBINE", "Turbine type (MaStR)", farm.turbine_type, ""))

    # --- assumptions actually used ---
    asm_fields: list[tuple[str, str, float | str, str]] = [
        ("E-ASM-LIFETIME", "Project lifetime", float(a.lifetime_years), "years"),
        ("E-ASM-AVAILABILITY", "Energy availability", a.availability, ""),
        ("E-ASM-ELEC-LOSSES", "Electrical losses", a.electrical_losses, ""),
        ("E-ASM-WAKE", "Wake losses", a.wake_losses, ""),
        ("E-ASM-CURTAILMENT", "Curtailment / redispatch", a.curtailment_redispatch, ""),
        ("E-ASM-DEGRADATION", "Degradation p.a.", a.degradation_pa, ""),
        ("E-ASM-CAPEX-MW", "Capex per MW", a.capex_eur_per_mw, "EUR/MW"),
        ("E-ASM-OPEX-FIXED", "Fixed opex per MW·yr", a.opex_fixed_eur_per_mw_yr, "EUR/MW/yr"),
        ("E-ASM-LEASE", "Land lease share of revenue", a.land_lease_pct_revenue, ""),
        ("E-ASM-INFLATION", "Inflation p.a.", a.inflation_pa, ""),
        ("E-ASM-REVENUE-MODE", "Revenue mode", a.revenue_mode, ""),
        ("E-ASM-EEG-SUPPORT", "EEG support period", float(a.eeg_support_years), "years"),
        ("E-ASM-NEG-RULE", "§51 rule threshold", float(a.neg_price_rule_hours), "h"),
        ("E-ASM-TARGET-DSCR", "Sculpting target DSCR", a.target_dscr, "×"),
        ("E-ASM-MAX-GEARING", "Gearing cap", a.max_gearing, ""),
        ("E-ASM-TENOR", "Debt tenor", float(a.debt_tenor_years), "years"),
        ("E-ASM-RATE", "Senior interest rate", a.interest_rate, ""),
        ("E-ASM-DSRA", "DSRA", float(a.dsra_months), "months"),
        ("E-ASM-WACC", "WACC (nominal)", a.wacc, ""),
        ("E-ASM-HURDLE", "Equity hurdle IRR", a.equity_target_irr, ""),
        ("E-ASM-TAX", "Tax rate", a.tax_rate, ""),
        ("E-ASM-DEPRECIATION", "Depreciation period", float(a.depreciation_years), "years"),
    ]
    if a.anzulegender_wert_ct_kwh is not None:
        asm_fields.append(("E-ASM-AW", "Anzulegender Wert", a.anzulegender_wert_ct_kwh, "ct/kWh"))
    if a.revenue_mode == "ppa" and a.ppa_price_eur_mwh is not None:
        asm_fields.append(("E-ASM-PPA", "PPA price", a.ppa_price_eur_mwh, "EUR/MWh"))
    if a.opex_variable_eur_per_mwh > 0:
        asm_fields.append(
            ("E-ASM-OPEX-VAR", "Variable opex", a.opex_variable_eur_per_mwh, "EUR/MWh")
        )
    if a.municipal_participation_enabled:
        asm_fields.append(
            (
                "E-ASM-MUNICIPAL",
                "Municipal participation (EEG §6)",
                a.municipal_participation_ct_kwh,
                "ct/kWh",
            )
        )
    items += [_asm(*f) for f in asm_fields]

    # --- computed: energy ---
    e_inputs = [
        "E-INP-MW",
        "E-INP-CF-P50",
        "E-ASM-WAKE",
        "E-ASM-AVAILABILITY",
        "E-ASM-ELEC-LOSSES",
        "E-ASM-CURTAILMENT",
    ]
    items += [
        _cmp("E-ENE-P50", "P50 annual energy", energy.p50_gwh, "GWh", "§8.2", e_inputs),
        _cmp(
            "E-ENE-P75",
            "P75 annual energy",
            energy.p75_gwh,
            "GWh",
            "§8.2.2",
            ["E-ENE-P50", "E-ENE-SIGMA"],
        ),
        _cmp(
            "E-ENE-P90",
            "P90 annual energy",
            energy.p90_gwh,
            "GWh",
            "§8.2.2",
            ["E-ENE-P50", "E-ENE-SIGMA"],
        ),
        _cmp(
            "E-ENE-P90-1YR",
            "1-year P90 energy (incl. inter-annual)",
            energy.p90_1yr_gwh,
            "GWh",
            "§8.2.2",
            ["E-ENE-P50", "E-ENE-SIGMA"],
        ),
        _cmp("E-ENE-NET-CF", "Net capacity factor", energy.net_cf, "", "§8.2", e_inputs),
        _cmp(
            "E-ENE-SIGMA",
            "Combined uncertainty sigma",
            energy.sigma_total,
            "",
            "§8.2.2",
            ["E-INP-CF-SIGMA"],
        ),
    ]

    # --- computed: revenue / operations (year 1) ---
    rev_inputs = ["E-ENE-P50", "E-ASM-REVENUE-MODE"]
    if a.anzulegender_wert_ct_kwh is not None:
        rev_inputs.append("E-ASM-AW")
    items += [
        _cmp(
            "E-REV-CAPTURE",
            "Wind capture rate",
            valuation.capture_rate,
            "",
            "§8.3.4",
            ["E-ENE-P50"],
        ),
        _cmp("E-REV-Y1", "Revenue, year 1", annual.revenue_total[0], "EUR", "§8.3", rev_inputs),
        _cmp(
            "E-REV-MARKET-Y1",
            "Market revenue, year 1",
            annual.revenue_market[0],
            "EUR",
            "§8.3.1",
            rev_inputs,
        ),
        _cmp(
            "E-REV-PREMIUM-Y1",
            "EEG premium revenue, year 1",
            annual.revenue_premium[0],
            "EUR",
            "§8.3.2",
            rev_inputs,
        ),
        _cmp(
            "E-REV-OPEX-Y1",
            "Opex, year 1",
            annual.opex_total[0],
            "EUR",
            "§8.4",
            ["E-ASM-OPEX-FIXED", "E-INP-MW"],
        ),
        _cmp(
            "E-REV-EBITDA-Y1",
            "EBITDA, year 1",
            annual.ebitda[0],
            "EUR",
            "§8.4",
            ["E-REV-Y1", "E-REV-OPEX-Y1"],
        ),
        _cmp(
            "E-REV-CFADS-Y1",
            "CFADS, year 1",
            annual.cfads[0],
            "EUR",
            "§8.5",
            ["E-REV-EBITDA-Y1"],
        ),
    ]

    # --- computed: debt ---
    d_inputs = ["E-REV-CFADS-Y1", "E-ASM-TARGET-DSCR", "E-ASM-RATE", "E-ASM-TENOR"]
    items += [
        _cmp(
            "E-DBT-CAPACITY",
            "Sculpted debt capacity",
            debt.debt_capacity_eur,
            "EUR",
            "§8.5",
            d_inputs,
        ),
        _cmp(
            "E-DBT-DRAWN",
            "Senior debt drawn",
            debt.debt_drawn_eur,
            "EUR",
            "§8.5",
            ["E-DBT-CAPACITY", "E-ASM-MAX-GEARING"],
        ),
        _cmp(
            "E-DBT-GEARING",
            "Gearing achieved",
            debt.gearing,
            "",
            "§8.5",
            ["E-DBT-DRAWN", "E-ASM-CAPEX-MW", "E-INP-MW"],
        ),
        _cmp("E-DBT-MIN-DSCR", "Minimum DSCR", debt.min_dscr, "×", "§8.5", d_inputs),
        _cmp("E-DBT-AVG-DSCR", "Average DSCR", debt.avg_dscr, "×", "§8.5", d_inputs),
        _cmp("E-DBT-LLCR", "LLCR", debt.llcr, "×", "§8.5", d_inputs),
        _cmp("E-DBT-PLCR", "PLCR", debt.plcr, "×", "§8.5", d_inputs),
        _cmp("E-DBT-DSRA", "DSRA funded at close", debt.dsra_eur, "EUR", "§8.5", ["E-ASM-DSRA"]),
    ]

    # --- computed: valuation ---
    items += [
        _cmp(
            "E-VAL-LCOE",
            "LCOE (nominal)",
            valuation.lcoe_eur_mwh,
            "EUR/MWh",
            "§8.6",
            ["E-ASM-CAPEX-MW", "E-REV-OPEX-Y1", "E-ENE-P50", "E-ASM-WACC"],
        ),
        _cmp(
            "E-VAL-NPV",
            "NPV @ WACC (unlevered, after tax)",
            valuation.npv_wacc_eur,
            "EUR",
            "§8.6",
            ["E-REV-EBITDA-Y1", "E-ASM-WACC", "E-ASM-TAX"],
        ),
        _cmp(
            "E-VAL-EQUITY",
            "Equity invested",
            valuation.equity_invested_eur,
            "EUR",
            "§8.6",
            ["E-ASM-CAPEX-MW", "E-DBT-DRAWN", "E-DBT-DSRA"],
        ),
        _cmp(
            "E-VAL-P90-DSCR",
            "Minimum DSCR at P90 energy",
            valuation.p90_min_dscr,
            "×",
            "§9.4",
            ["E-ENE-P90", "E-DBT-MIN-DSCR"],
        ),
    ]
    if valuation.equity_irr is not None:
        items.append(
            _cmp(
                "E-VAL-IRR",
                "Equity IRR",
                valuation.equity_irr,
                "",
                "§8.6",
                ["E-VAL-EQUITY", "E-REV-CFADS-Y1"],
            )
        )
    if valuation.payback_year is not None:
        items.append(
            _cmp(
                "E-VAL-PAYBACK",
                "Equity payback year",
                float(valuation.payback_year),
                "",
                "§8.6",
                ["E-VAL-EQUITY"],
            )
        )
    if valuation.breakeven_bid_ct_kwh is not None:
        items.append(
            _cmp(
                "E-VAL-BREAKEVEN",
                "Break-even bid",
                valuation.breakeven_bid_ct_kwh,
                "ct/kWh",
                "§8.6",
                ["E-ASM-HURDLE", "E-VAL-EQUITY"],
            )
        )

    items.sort(key=lambda e: e.id)
    ids = [e.id for e in items]
    assert len(ids) == len(set(ids)), "duplicate evidence ids"
    known = set(ids)
    for e in items:
        for ref in e.inputs:
            assert ref in known, f"evidence {e.id} references unknown id {ref}"
    return items
