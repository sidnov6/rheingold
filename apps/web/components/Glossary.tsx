"use client";

/**
 * Glossary (Appendix C) — hover-tooltip term component.
 * <GlossaryTerm term="CFADS" /> renders the term with a dotted underline and a
 * Radix hover card carrying the definition. GLOSSARY is exported for tables
 * (methodology page) and the memo appendix.
 */

import * as HoverCard from "@radix-ui/react-hover-card";
import clsx from "clsx";

/** Appendix C, verbatim. */
export const GLOSSARY: Record<string, string> = {
  "MaStR / Marktstammdatenregister":
    "Federal register of all German generation units",
  "Anzulegender Wert (AW)":
    "Award value from EEG auction, basis of the market premium",
  "Marktwert (MW Wind an Land)":
    "Monthly reference market value of onshore wind energy",
  Marktprämie: "EEG market premium = max(0, AW − Marktwert)",
  "§51 / negative-price rule":
    "Hours in negative-price streaks lose the premium",
  "Zuschlagswert / Höchstwert": "Auction award price / price cap",
  CFADS: "Cash flow available for debt service",
  "DSCR / LLCR / PLCR": "Period / loan-life / project-life coverage ratios",
  DSRA: "Debt-service reserve account",
  Sculpting: "Shaping principal so DSCR is constant at target",
  Repowering: "Replacing old turbines with fewer, larger ones",
  "Nabenhöhe / Inbetriebnahme": "Hub height / commissioning",
};

/** Find a glossary entry by exact key or by substring of a key. */
function lookup(term: string): { key: string; def: string } | null {
  if (term in GLOSSARY) return { key: term, def: GLOSSARY[term] };
  const hit = Object.keys(GLOSSARY).find((k) =>
    k.toLowerCase().includes(term.toLowerCase()),
  );
  return hit ? { key: hit, def: GLOSSARY[hit] } : null;
}

export function GlossaryTerm({
  term,
  children,
  className,
}: {
  /** Glossary key (exact or substring match against Appendix C keys). */
  term: string;
  /** Visible text; defaults to the term itself. */
  children?: React.ReactNode;
  className?: string;
}) {
  const entry = lookup(term);
  const label = children ?? term;
  if (!entry) return <span className={className}>{label}</span>;

  return (
    <HoverCard.Root openDelay={150} closeDelay={100}>
      <HoverCard.Trigger asChild>
        <span
          tabIndex={0}
          className={clsx(
            "cursor-help underline decoration-low decoration-dotted underline-offset-2 transition-colors hover:decoration-mid",
            className,
          )}
        >
          {label}
        </span>
      </HoverCard.Trigger>
      <HoverCard.Portal>
        <HoverCard.Content
          side="top"
          sideOffset={6}
          collisionPadding={12}
          className="z-50 max-w-xs rounded border border-line bg-bg2 px-3 py-2 text-data text-mid"
        >
          <span className="block text-2xs uppercase tracking-wider text-low">
            {entry.key}
          </span>
          <span className="mt-1 block leading-relaxed text-hi">{entry.def}</span>
          <HoverCard.Arrow className="fill-[var(--border)]" />
        </HoverCard.Content>
      </HoverCard.Portal>
    </HoverCard.Root>
  );
}
