/**
 * TypeScript mirrors of the engine's pydantic contracts
 * (packages/engine/rheingold_engine/models.py). Keep field names snake_case —
 * they arrive verbatim from FastAPI.
 */

export interface FleetFarm {
  id: string;
  name: string;
  lat: number;
  lon: number;
  mw: number;
  n: number; // unit count
  man: string | null; // manufacturer
  yr: number | null; // commissioning year
  bl: string | null; // Bundesland
}

export interface FleetMeta {
  unit_count: number;
  farm_count: number;
  total_mw: number;
  mastr_snapshot_date: string;
  built_at: string;
}

export interface FarmDetail {
  farm_id: string;
  name: string;
  lat: number;
  lon: number;
  mw_total: number;
  n_units: number;
  manufacturer: string | null;
  turbine_type: string | null;
  hub_height_m: number | null;
  rotor_d_m: number | null;
  commissioning_year: number | null;
  bundesland: string | null;
  operator: string | null;
  resource: {
    p50_cf: number;
    method: "ninja" | "gwa_windpowerlib";
    hub_height_used: number;
    source: string;
  } | null;
  sources: { label: string; url: string }[];
  unit_ids: string[];
}

export interface Shocks {
  price_level: number;
  price_years: number | null;
  production_delta: number;
  production_years: number | null;
  rate_delta_bps: number;
  wacc_delta_bps: number;
  capex_delta: number;
  availability_override: number | null;
  curtailment_override: number | null;
  negative_hours_multiplier: number;
}

export const DEFAULT_SHOCKS: Shocks = {
  price_level: 0,
  price_years: null,
  production_delta: 0,
  production_years: null,
  rate_delta_bps: 0,
  wacc_delta_bps: 0,
  capex_delta: 0,
  availability_override: null,
  curtailment_override: null,
  negative_hours_multiplier: 1,
};

export interface AnnualSeries {
  year: number[];
  energy_mwh: number[];
  revenue_market: number[];
  revenue_premium: number[];
  revenue_total: number[];
  opex_fixed: number[];
  opex_variable: number[];
  land_lease: number[];
  municipal_participation: number[];
  opex_total: number[];
  ebitda: number[];
  depreciation: number[];
  tax: number[];
  cfads: number[];
  debt_balance_bop: number[];
  interest: number[];
  principal: number[];
  debt_service: number[];
  dscr: (number | null)[];
  llcr: (number | null)[];
  equity_cf: number[];
}

export interface UncertaintyStackRow {
  component: string;
  sigma: number;
  included_in_p90: boolean;
  note: string;
}

export interface EnergyResult {
  p50_gwh: number;
  p75_gwh: number;
  p90_gwh: number;
  p90_1yr_gwh: number;
  net_cf: number;
  sigma_total: number;
  uncertainty_stack: UncertaintyStackRow[];
}

export interface DebtResult {
  debt_capacity_eur: number;
  debt_drawn_eur: number;
  gearing: number;
  gearing_cap_binding: boolean;
  dsra_eur: number;
  min_dscr: number;
  avg_dscr: number;
  llcr: number;
  plcr: number;
}

export interface ValuationResult {
  lcoe_eur_mwh: number;
  npv_wacc_eur: number;
  equity_irr: number | null;
  equity_invested_eur: number;
  payback_year: number | null;
  breakeven_bid_ct_kwh: number | null;
  capture_rate: number;
  p90_min_dscr: number;
}

export interface TornadoItem {
  variable: string;
  label: string;
  low_input: string;
  high_input: string;
  irr_low: number | null;
  irr_high: number | null;
}

export interface EvidenceItem {
  id: string;
  type: "computed" | "assumption" | "source";
  label: string;
  value: number | string;
  unit: string;
  formula_ref: string | null;
  inputs: string[];
  url: string | null;
  retrieved_at: string | null;
}

export interface UnderwriteResult {
  farm: Record<string, unknown> & { farm_id: string; name: string };
  assumptions: Record<string, number | string | boolean | null>;
  shocks: Shocks;
  annual: AnnualSeries;
  energy: EnergyResult;
  debt: DebtResult;
  valuation: ValuationResult;
  tornado: TornadoItem[];
  evidence: EvidenceItem[];
}

// ---- agent / memo stream (§9, §10) ----

export type Verdict = "PROCEED" | "PROCEED_WITH_CONDITIONS" | "DECLINE";

export interface Claim {
  id: string;
  agent: "resource" | "revenue" | "credit";
  statement: string;
  evidence_ids: string[];
  severity: "info" | "concern" | "dealbreaker";
  confidence: number;
}

export interface Rebuttal extends Claim {
  targets_claim_id: string;
}

export interface GateFlag {
  rule_id: string;
  passed: boolean;
  value: number;
  threshold: number;
}

export interface MemoValidation {
  ok: boolean;
  errors: string[];
}

export type MemoEvent =
  | { type: "agent_status"; agent: string; status: "running" | "done" | "error" }
  | { type: "claim"; claim: Claim }
  | { type: "rebuttal"; rebuttal: Rebuttal }
  | { type: "memo_delta"; text: string }
  | { type: "validation"; validation: MemoValidation }
  | { type: "gate"; flags: GateFlag[] }
  | { type: "error"; message: string }
  | { type: "done"; verdict: Verdict | null };

export interface BacktestRound {
  round_date: string;
  avg_award_ct_kwh: number | null;
  max_price_ct_kwh: number | null;
  model_median_ct_kwh: number;
  model_p25_ct_kwh: number;
  model_p75_ct_kwh: number;
  n_farms: number;
}

export interface BacktestResult {
  rounds: BacktestRound[];
  mae_ct_kwh: number;
  directional_hit_rate: number;
  generated_at: string;
  method_note: string;
}
