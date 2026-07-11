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
- **Inflation convention (deliberate deviation from the literal §8.4 text):**
  fixed opex escalates as `(1+infl)^(t−1)` — year 1 runs at today's price
  level, the standard modeling convention — where the spec text reads
  `(1+infl)^t`. Declared per the CLAUDE.md rule: the spec text changed, not
  the engine. (Golden farm is unaffected: its inflation is 0.)
- **Debt sculpting principal floor:** DS_t = max(s·CFADS_t, I_t). Years where
  the interest-only floor binds report DSCR below target honestly; the extra
  payments retire the loan *early* (trailing DS = 0 inside the tenor) rather
  than re-sculpting to land exactly at maturity.
- **Tornado sensitivities** are anchored to the *unshocked* base case — the
  sliders answer "what if the world moves", the tornado answers "what is this
  deal structurally sensitive to". In break-even mode the tornado's AW is
  therefore solved without scenario shocks, while the headline result uses the
  shock-consistent break-even bid.
- **§51 negative-price rule:** modeled as a single config int
  (`neg_price_rule_hours`) applied to the representative price year's streaks.
  The cohort mapping (verified against §§51/51a/100 EEG, Clearingstelle FAQ 264,
  buzer.de amendment history, as of 2026-07-11):

  | Commissioning (or tender award) | Rule | Engine int |
  |---|---|---|
  | ≤ 2015-12-31 | no negative-price rule | 8760 (sentinel: never triggers) |
  | 2016–2020 | ≥ 6 consecutive negative hours (wind ≥ 3 MW w/ §24 aggregation) | 6 |
  | 2021–2022 | ≥ 4 consecutive hours (EEG 2021) | 4 |
  | 2023-01-01 – 2025-02-24 | stepdown **by calendar year of the event**: 4h (2023), 3h (2024 **and** 2025), 2h (2026), 1h (2027+) | 1 (steady state 2027+; 2026's 2h documented deviation) |
  | ≥ 2025-02-25 (Solarspitzengesetz) | premium = 0 in **every** negative quarter-hour (wind included) | 0 |

  Simplifications: (a) the stepdown cohort is keyed on commissioning OR tender
  award date — we key on commissioning year only, which overstates severity for
  farms awarded pre-25.02.2025 but commissioned later; (b) the current
  quarter-hour rule is approximated at hourly resolution; (c) the §51a
  support-period extension (lost time appended after year 20, day-rounded) is
  **not modeled** — a documented conservative bias.

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
8. **Pre-auction-era farms (COD < 2017):** their statutory EEG feed-in tariffs
   are not modeled. The API underwrites them at the break-even bid when it
   exists, else as pure merchant projects at the representative market year —
   the evidence store shows `revenue_mode` transparently. Auction-era farms
   default to the real volume-weighted Ø-Zuschlagswert of the rounds ~2 years
   before commissioning (typical realization lag).

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
