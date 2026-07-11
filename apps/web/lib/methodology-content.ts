/**
 * Static content for /methodology: the §8 formulas (transcribed faithfully
 * from docs/RHEINGOLD_BUILD_SPEC.md §8.2–8.7), the default-assumptions table
 * (mirrors packages/engine/rheingold_engine/defaults.yaml — config IS
 * documentation), the data-source license table, and the architecture
 * lineage diagram source (docs/architecture.mmd).
 */

export interface FormulaSection {
  id: string;
  ref: string; // spec section
  title: string;
  intro: string;
  formulas: string; // rendered as a mono code block
  notes?: string;
}

export const FORMULA_SECTIONS: FormulaSection[] = [
  {
    id: "energy",
    ref: "§8.2",
    title: "Energy — P50 and the uncertainty stack",
    intro:
      "P50 annual energy from the capacity factor, degraded per year; P90/P75 from independent uncertainty components combined in quadrature.",
    formulas: `E_p50 = mw_total × 8760 × p50_cf × (1 − wake) × availability
        × (1 − elec_losses) × (1 − curtailment)

E_t = E_p50 × (1 − degradation)^(t − 1)

σ_total = sqrt(Σ σ²)        # independent σ's in quadrature:
                            #   wind-data/method σ  (Path A: 0.06, Path B: 0.09)
                            #   loss uncertainties   0.03
                            #   inter-annual var.    0.06 — NOT in long-term P90;
                            #                        reported separately as 1-yr P90

P90 = P50 × (1 − 1.2816 σ_total)
P75 = P50 × (1 − 0.6745 σ_total)`,
    notes:
      "The uncertainty stack is published as a table in every dossier — each σ, and whether it enters the long-term P90.",
  },
  {
    id: "revenue",
    ref: "§8.3",
    title: "Revenue — merchant, EEG premium, §51, capture, PPA",
    intro:
      "Hourly shaping: the farm's hourly CF profile (Path A) or class-average profile (Path B) is normalized to E_t and joined with hourly day-ahead prices.",
    formulas: `1. Merchant:        Rev_t = Σ_h E_h × price_h

2. EEG premium:     premium_h = max(0, AW − MW_month)   on eligible energy,
                    on top of market sales
                    AW = anzulegender Wert, MW = monthly Marktwert Wind an Land
                    support for eeg_support_years from commissioning;
                    after → merchant tail (if enabled)

3. §51 rule:        premium = 0 for hours inside negative-price streaks
                    ≥ neg_price_rule_hours (market revenue in those hours per
                    actual price, floored at 0 for the premium leg)

4. Capture rate:    capture_t = wind-weighted price / baseload avg
                    (computed from data — never hardcoded)

5. PPA:             flat ppa_price_eur_mwh on all volume, no premium`,
    notes:
      "The EEG 2023 §51 stepdown (4h→3h→2h→1h by year, stricter for newer plants) is why the streak length is a config int; the chosen mapping is documented in MODEL_CARD.md.",
  },
  {
    id: "costs",
    ref: "§8.4",
    title: "Costs",
    intro: "Annual operating costs; EBITDA follows directly.",
    formulas: `Opex_t = opex_fixed × MW × (1 + infl)^t
       + opex_var × E_t
       + land_lease_pct × Rev_t
       + municipal_0.2ct × E_t          (if enabled, EEG §6)
       + insurance/management            (folded into fixed)

EBITDA_t = Rev_t − Opex_t`,
  },
  {
    id: "debt",
    ref: "§8.5",
    title: "Debt — sculpting & coverage ratios",
    intro:
      "Principal is sculpted so DSCR is constant at target over the tenor; a gearing cap can bind and lift DSCR above target.",
    formulas: `CFADS_t = EBITDA_t − tax_t

Sculpt to target DSCR over tenor T, rate r:
  DS_t = CFADS_t / target_dscr            for t = 1..T
  D₀   = Σ DS_t / (1 + r)^t               # debt capacity
  D    = min(D₀, max_gearing × Capex)     # gearing cap
         if the cap binds: rescale DS_t uniformly so PV = D
         (DSCR rises above target)

Roll forward:
  I_t = r × B_{t−1}
  P_t = DS_t − I_t          assert B_T ≈ 0 and P_t ≥ 0
                            (negative early principal → floor at 0, re-solve)

DSRA    = dsra_months/12 × avg(DS)        funded at close, released at maturity
DSCR_t  = CFADS_t / DS_t
LLCR_t  = [ PV_{t..T}(CFADS, r) + DSRA ] / B_{t−1}
PLCR    = analogous, to project end`,
  },
  {
    id: "valuation",
    ref: "§8.6",
    title: "Valuation — LCOE, NPV, equity IRR, break-even bid",
    intro:
      "Nominal LCOE (stated as such), unlevered NPV at WACC, levered equity IRR, and the break-even auction bid that powers the backtest.",
    formulas: `LCOE = [ Capex + Σ Opex_t/(1+wacc)^t ] / [ Σ E_t/(1+wacc)^t ]   (nominal)

NPV@WACC     on unlevered after-tax FCF

Equity IRR   on [ −(Capex + DSRA − D), (CFADS_t − DS_t)... ]

Payback      on cumulative equity CF

Break-even bid:  solve AW ∈ [2, 12] ct/kWh (brentq)
                 s.t. Equity IRR = equity_target_irr`,
    notes: "The break-even solve is the function behind the entire auction backtest (§12).",
  },
  {
    id: "tax",
    ref: "§8.7",
    title: "Tax — simple, honest",
    intro: "Straight-line depreciation, interest deductible, no refinements.",
    formulas: `depr_t = Capex / depreciation_years        (straight-line, 16y standard for wind)

tax_t  = max(0, tax_rate × (EBITDA_t − depr_t − interest_t))

Circularity (tax needs sculpted interest):
  pass 1: sculpt on pre-tax CFADS → interest
  pass 2: compute tax, re-sculpt once on after-tax CFADS
  Two passes, deterministic, done.`,
    notes:
      "No loss carryforward, no Zinsschranke, no trade-tax split — all three listed as limitations in MODEL_CARD.md.",
  },
];

// -------------------------------------------------------- default assumptions

export interface AssumptionRow {
  field: string;
  value: string; // display string (already formatted, unit included)
  numeric: boolean; // wrap in .num?
  source: string;
}

/**
 * Mirrors packages/engine/rheingold_engine/defaults.yaml (field-for-field,
 * source-for-source). If defaults.yaml changes, change this table too.
 */
export const DEFAULT_ASSUMPTIONS: AssumptionRow[] = [
  {
    field: "lifetime_years",
    value: "25",
    numeric: true,
    source:
      "Standard German onshore design life; WindGuard Kostensituation studies assume 20–25y, modern permits 25y+",
  },
  {
    field: "availability",
    value: "0,97",
    numeric: true,
    source:
      "Author field experience (Suzlon O&M, 10+ plants); consistent with full-service contract guarantees of 95–97%",
  },
  {
    field: "electrical_losses",
    value: "0,02",
    numeric: true,
    source:
      "Typical park-internal + grid-connection electrical losses, DNV/WindGuard energy-assessment practice",
  },
  {
    field: "wake_losses",
    value: "0,06",
    numeric: true,
    source:
      "Typical German onshore park wake deficit for mid-size parks; applied only when CF is single-turbine based",
  },
  {
    field: "curtailment_redispatch",
    value: "0,02",
    numeric: true,
    source:
      "BNetzA Monitoringbericht redispatch/EinsMan volumes for onshore wind, order-of-magnitude national average",
  },
  {
    field: "degradation_pa",
    value: "0,002",
    numeric: true,
    source:
      "Staffell & Green (2014), UK fleet performance degradation ~0.2%/yr aged-fleet estimate",
  },
  {
    field: "capex_eur_per_mw",
    value: "1.650.000 €",
    numeric: true,
    source:
      "FALLBACK ONLY — per-vintage values from data/manual/cost_vintages.csv (WindGuard/Fraunhofer ISE/IRENA)",
  },
  {
    field: "opex_fixed_eur_per_mw_yr",
    value: "55.000 €",
    numeric: true,
    source:
      "FALLBACK ONLY — per-vintage values from data/manual/cost_vintages.csv (WindGuard Betriebskosten)",
  },
  {
    field: "opex_variable_eur_per_mwh",
    value: "0,0",
    numeric: true,
    source: "Variable O&M folded into fixed full-service rate by default (§8.4)",
  },
  {
    field: "land_lease_pct_revenue",
    value: "0,06",
    numeric: true,
    source:
      "German onshore land-lease benchmarks, 4–8% of revenue; WindGuard Kostensituation 2019 range midpoint",
  },
  {
    field: "municipal_participation_ct_kwh",
    value: "0,2 ct/kWh",
    numeric: true,
    source:
      "EEG 2023 §6: up to 0.2 ct/kWh to hosting municipalities; market practice treats as standard for new builds",
  },
  {
    field: "municipal_participation_enabled",
    value: "true",
    numeric: false,
    source: "EEG §6 participation is voluntary but near-universal in post-2021 projects",
  },
  {
    field: "inflation_pa",
    value: "0,02",
    numeric: true,
    source: "ECB medium-term inflation target",
  },
  {
    field: "revenue_mode",
    value: "eeg_premium",
    numeric: false,
    source: "Default German route-to-market: EEG Marktprämienmodell (§8.3.2)",
  },
  {
    field: "anzulegender_wert_ct_kwh",
    value: "null",
    numeric: false,
    source:
      "None → engine solves break-even bid (§8.6); real farms use awarded AW when known",
  },
  {
    field: "ppa_price_eur_mwh",
    value: "null",
    numeric: false,
    source: "PPA mode only",
  },
  {
    field: "eeg_support_years",
    value: "20",
    numeric: true,
    source: "EEG §25: 20-year support period from commissioning",
  },
  {
    field: "neg_price_rule_hours",
    value: "4",
    numeric: true,
    source:
      "EEG §51 (2021): premium = 0 in negative-price streaks ≥ 4h; per-vintage mapping in MODEL_CARD.md",
  },
  {
    field: "merchant_tail",
    value: "true",
    numeric: false,
    source: "Years beyond support earn wind-weighted capture price (§8.3)",
  },
  {
    field: "target_dscr",
    value: "1,30×",
    numeric: true,
    source:
      "German onshore project-finance market convention for EEG-backed revenue (1.20–1.35 range)",
  },
  {
    field: "max_gearing",
    value: "0,75",
    numeric: true,
    source: "Typical senior gearing cap for onshore wind with EEG revenue",
  },
  {
    field: "debt_tenor_years",
    value: "18",
    numeric: true,
    source: "Market convention: support period (20y) minus 1–2y tail",
  },
  {
    field: "interest_rate",
    value: "0,045",
    numeric: true,
    source: "FALLBACK ONLY — per-vintage values from data/manual/cost_vintages.csv",
  },
  {
    field: "dsra_months",
    value: "6",
    numeric: true,
    source: "6-month DSRA is standard senior-debt security package",
  },
  {
    field: "wacc",
    value: "0,058",
    numeric: true,
    source: "Fraunhofer ISE LCOE study WACC range for German onshore wind (nominal)",
  },
  {
    field: "equity_target_irr",
    value: "0,08",
    numeric: true,
    source:
      "Infrastructure-fund hurdle for German onshore wind equity, market commentary range 7–9%",
  },
  {
    field: "tax_rate",
    value: "0,30",
    numeric: true,
    source:
      "German corporate tax ≈ 15% KSt + Soli + ~14–17% GewSt → ~30% combined (§8.7 simplification)",
  },
  {
    field: "depreciation_years",
    value: "16",
    numeric: true,
    source: "AfA table for wind turbines: 16-year straight-line standard",
  },
];

// ---------------------------------------------------------------- licenses

export interface LicenseRow {
  source: string;
  whatFor: string;
  license: string;
  note?: string;
}

export const LICENSE_TABLE: LicenseRow[] = [
  {
    source: "Marktstammdatenregister (MaStR), Bundesnetzagentur",
    whatFor: "The fleet — every registered onshore wind unit",
    license: "DL-DE/BY-2.0",
    note: "Attribution required (Datenlizenz Deutschland – Namensnennung).",
  },
  {
    source: "SMARD.de, Bundesnetzagentur",
    whatFor: "Day-ahead power prices (hourly)",
    license: "CC BY 4.0",
  },
  {
    source: "Netztransparenz.de (ÜNB)",
    whatFor: "Monthly market values (Marktwert Wind an Land)",
    license: "Terms of use — attribution",
    note: "Used per the transmission operators' published terms, with attribution.",
  },
  {
    source: "renewables.ninja",
    whatFor: "Hourly wind capacity-factor profiles (resource Path A)",
    license: "CC BY-NC 4.0 — NON-COMMERCIAL",
    note: "Non-commercial license. RHEINGOLD is a non-commercial portfolio/demo project; any commercial use would require replacing this source.",
  },
  {
    source: "BNetzA onshore auction results",
    whatFor: "Award prices 2017–2025 (backtest validation target)",
    license: "Public sector information",
  },
  {
    source: "CARTO \"Dark Matter\" basemap",
    whatFor: "Map tiles / style",
    license: "CARTO basemap terms — attribution required",
    note: "© CARTO, © OpenStreetMap contributors.",
  },
];

// ------------------------------------------------------------- data lineage

/** Verbatim source of docs/architecture.mmd (mermaid). */
export const ARCHITECTURE_MMD = `flowchart LR
  A[MaStR] --> P[pipelines]
  B[SMARD] --> P
  C[Netztransparenz] --> P
  D[BNetzA auctions CSV] --> P
  E[Wind resource: ninja / GWA] --> P
  P --> M[(DuckDB mart)]
  M --> API[FastAPI]
  API --> ENG[Deterministic engine]
  ENG --> EV[(EvidenceStore)]
  EV --> GATE[Compliance gate - code]
  EV --> CR[3 critics - Claude]
  CR --> N[Narrator - Claude]
  GATE --> N
  N --> V{Citation validator}
  V -->|pass| UI[Next.js: map / dossier / memo]
  V -->|fail| CR
  UI --> H[Human veto]`;

export const MODEL_CARD_URL = "../../docs/MODEL_CARD.md";
