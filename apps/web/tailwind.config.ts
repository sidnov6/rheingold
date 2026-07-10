import type { Config } from "tailwindcss";

/**
 * Nachtgold design system (spec §3). Every color maps to a CSS variable from
 * globals.css — no hex literals in components, ever (CLAUDE.md rule).
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg0: "var(--bg-0)",
        bg1: "var(--bg-1)",
        bg2: "var(--bg-2)",
        line: "var(--border)",
        gold: {
          500: "var(--gold-500)",
          400: "var(--gold-400)",
          300: "var(--gold-300)",
          dim: "var(--gold-dim)",
        },
        rhine: {
          500: "var(--rhine-500)",
          300: "var(--rhine-300)",
        },
        hi: "var(--text-hi)",
        mid: "var(--text-mid)",
        low: "var(--text-low)",
        pos: "var(--pos)",
        neg: "var(--neg)",
        warn: "var(--warn)",
        paper: "var(--paper)",
        "paper-edge": "var(--paper-edge)",
        ink: "var(--ink)",
        "stamp-proceed": "var(--stamp-proceed)",
        "stamp-conditions": "var(--stamp-conditions)",
        "stamp-decline": "var(--stamp-decline)",
      },
      fontFamily: {
        display: ["var(--font-newsreader)", "Georgia", "serif"],
        sans: ["var(--font-plex-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-plex-mono)", "ui-monospace", "monospace"],
      },
      fontSize: {
        // §3.2 scale
        "2xs": ["12px", "16px"],
        data: ["13px", "18px"],
        base: ["14px", "20px"],
        md: ["16px", "24px"],
        lg: ["20px", "28px"],
        xl: ["28px", "36px"],
        "2xl": ["40px", "48px"],
      },
      transitionDuration: { DEFAULT: "175ms" },
      transitionTimingFunction: { DEFAULT: "cubic-bezier(0, 0, 0.2, 1)" },
    },
  },
  plugins: [],
};

export default config;
