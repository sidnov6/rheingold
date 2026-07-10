# RHEINGOLD Model Card

What the numbers are, where they come from, and — prominently — what this model
does **not** do. The engine is deterministic (same inputs → identical outputs);
the agent layer only narrates evidence the engine produced.

## Engine assumptions & conventions

- **Periodicity:** annual for debt/DCF; hourly only inside revenue shaping (one
  representative calendar year of prices + a normalized hourly generation shape).
- **Money:** nominal EUR throughout. LCOE is nominal (stated on the page).
  ct/kWh ↔ EUR/MWh converts at ×10.
- **Valuation date:** underwriting is as-of commissioning (year 1 = first full
  operating year). Historic farms are valued as their original greenfield deal,
  not marked to today — the backtest (§12) depends on this convention.
- **Energy:** P50 from resource pipeline (Path A renewables.ninja hourly, Path B
  Global Wind Atlas + windpowerlib power curve). Uncertainty stack combined in
  quadrature; inter-annual variability (σ≈0.06) is *excluded* from the long-term
  P90 and reported separately as a 1-year P90.
- **Tax circularity:** tax needs interest, interest needs debt sizing, sizing
  needs after-tax CFADS. Resolved with exactly two deterministic passes
  (sculpt pre-tax → tax → re-sculpt once). Not iterated to convergence.
- **§51 negative-price rule:** modeled as a single config int
  (`neg_price_rule_hours`) applied to the representative price year's streaks.
  <!-- RESEARCH: commissioning-year mapping table goes here -->

## Known limitations (deliberate)

1. **Tax:** no loss carryforward, no Zinsschranke (interest barrier), no
   trade-tax (GewSt) split by municipality. Straight-line AfA over 16 years.
2. **§51 vintages:** one rule int per run; per-plant legal vintage stacking
   (EEG 2017/2021/2023 + 2025 changes) is not modeled per unit.
3. **Merchant tail:** years after EEG support earn the wind-weighted capture
   price derived from the representative year — no forward curve, no basis risk.
4. **No monthly debt model:** annual DSCR only; intra-year seasonality ignored.
5. **Resource error:** Path B (GWA + power curve) has no hourly shape of its
   own; it borrows a class-average duration profile. σ set accordingly (0.09).
6. **Repowering, curtailment contracts, balancing costs:** out of scope.
7. **Backtest caveats:** winner's curse, undersubscribed rounds 2019–2022,
   binding Höchstwert post-2022, site-selection bias (registry ≠ bid pipeline).

## Agent layer limits

- Critics/narrator read a frozen EvidenceStore; they cannot fetch or compute.
- Every numeric claim must cite an evidence id; the citation-integrity
  validator (§9.6) hard-fails memos with fabricated or drifting numbers
  (>0.5 % relative). One regeneration; then errors surface in the UI.
- The compliance gate is deterministic Python — verdict constraints
  (no PROCEED past a failed dealbreaker gate) are enforced in code after
  generation, not by prompt.
- Model: `claude-sonnet-4-6` (env-overridable), temperature 0.2.

## Data vintages

See `/api/health` for live mart vintages and docs/DATA_SOURCES.md for licenses.
