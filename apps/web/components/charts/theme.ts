/**
 * Shared visx chart styling — every color a CSS variable from globals.css
 * (§3.1; no hex literals). SVG accepts var() for fill/stroke directly.
 */

export const C = {
  gold: "var(--gold-500)",
  goldHover: "var(--gold-400)",
  goldDim: "var(--gold-dim)",
  rhine: "var(--rhine-500)",
  rhineLight: "var(--rhine-300)",
  neg: "var(--neg)",
  pos: "var(--pos)",
  warn: "var(--warn)",
  border: "var(--border)",
  textHi: "var(--text-hi)",
  textMid: "var(--text-mid)",
  textLow: "var(--text-low)",
  bg2: "var(--bg-2)",
} as const;

export const MONO = "var(--font-plex-mono), ui-monospace, monospace";
export const SANS = "var(--font-plex-sans), system-ui, sans-serif";

/** Numeric tick labels: mono, low-contrast, tabular. */
export const numTickProps = {
  fill: C.textLow,
  fontSize: 10,
  fontFamily: MONO,
} as const;

/** Categorical tick labels (years, names). */
export const catTickProps = {
  fill: C.textLow,
  fontSize: 10,
  fontFamily: SANS,
} as const;

export const axisLineProps = { stroke: C.border, strokeWidth: 1 } as const;
