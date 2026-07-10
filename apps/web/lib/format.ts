/**
 * All numbers rendered in the UI go through here (CLAUDE.md rule).
 * de-DE locale: 1.234.567,89 — tabular mono is applied via the .num class.
 */

const de = (opts: Intl.NumberFormatOptions = {}) => new Intl.NumberFormat("de-DE", opts);

const NUM_0 = de({ maximumFractionDigits: 0 });
const NUM_1 = de({ minimumFractionDigits: 1, maximumFractionDigits: 1 });
const NUM_2 = de({ minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const fmtInt = (v: number): string => NUM_0.format(v);
export const fmt1 = (v: number): string => NUM_1.format(v);
export const fmt2 = (v: number): string => NUM_2.format(v);

/** 1234567 € → "1,23 M€"; 45300 → "45 k€" */
export function fmtEur(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1e9) return `${NUM_2.format(v / 1e9)} Mrd€`;
  if (abs >= 1e6) return `${NUM_2.format(v / 1e6)} M€`;
  if (abs >= 1e4) return `${NUM_0.format(v / 1e3)} k€`;
  return `${NUM_0.format(v)} €`;
}

export const fmtEurMwh = (v: number): string => `${NUM_2.format(v)} €/MWh`;
export const fmtCtKwh = (v: number): string => `${NUM_2.format(v)} ct/kWh`;
export const fmtGwh = (v: number): string => `${NUM_1.format(v)} GWh`;
export const fmtMw = (v: number): string => `${NUM_1.format(v)} MW`;

/** 0.084 → "8,4 %" */
export const fmtPct = (v: number, digits = 1): string =>
  `${de({ minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v * 100)} %`;

/** 1.32 → "1,32×" */
export const fmtX = (v: number): string => `${NUM_2.format(v)}×`;

export const fmtYear = (v: number): string => String(v);

export function fmtDelta(v: number, digits = 1): string {
  const s = de({
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: "always",
  }).format(v * 100);
  return `${s} pp`;
}
