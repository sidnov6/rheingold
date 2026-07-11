"use client";

import { useState } from "react";
import type { Claim, EvidenceItem, Rebuttal } from "@/lib/types";
import { AgentDebatePanel, MemoPaper, VetoBar } from "@/components/memo";

/**
 * DEV HARNESS — synthetic demo data only (clearly labeled, never shipped as
 * real output). Exercises MemoPaper (verdict stamp, citation seals, orphan
 * seal, validation-failure banner, vetoed watermark) and AgentDebatePanel.
 */

const EVIDENCE: EvidenceItem[] = [
  {
    id: "E-CF-P50",
    type: "computed",
    label: "P50 net capacity factor",
    value: 0.284,
    unit: "",
    formula_ref: "§8.2",
    inputs: ["E-RES-CF-RAW", "E-ASM-AVAIL"],
    url: null,
    retrieved_at: null,
  },
  {
    id: "E-ENERGY-P50",
    type: "computed",
    label: "P50 net energy, year 1",
    value: 104.5,
    unit: "GWh",
    formula_ref: "§8.2",
    inputs: ["E-CF-P50"],
    url: null,
    retrieved_at: null,
  },
  {
    id: "E-DSCR-MIN",
    type: "computed",
    label: "Minimum DSCR",
    value: 1.32,
    unit: "×",
    formula_ref: "§8.5",
    inputs: ["E-CFADS", "E-DEBT-SERVICE"],
    url: null,
    retrieved_at: null,
  },
  {
    id: "E-IRR-EQ",
    type: "computed",
    label: "Equity IRR",
    value: 0.084,
    unit: "%",
    formula_ref: "§8.6",
    inputs: ["E-EQUITY-CF"],
    url: null,
    retrieved_at: null,
  },
  {
    id: "E-LCOE",
    type: "computed",
    label: "LCOE",
    value: 58.7,
    unit: "€/MWh",
    formula_ref: "§8.6",
    inputs: ["E-CAPEX", "E-OPEX", "E-ENERGY-P50"],
    url: null,
    retrieved_at: null,
  },
  {
    id: "E-SRC-MASTR-HUB",
    type: "source",
    label: "Hub height (MaStR)",
    value: 135,
    unit: "m",
    formula_ref: null,
    inputs: [],
    url: "https://www.marktstammdatenregister.de/MaStR",
    retrieved_at: "2026-07-14",
  },
  {
    id: "E-MW-MARKTWERT",
    type: "source",
    label: "Marktwert Wind an Land, Jun 2026",
    value: 6.12,
    unit: "ct/kWh",
    formula_ref: null,
    inputs: [],
    url: "https://www.netztransparenz.de/",
    retrieved_at: "2026-07-05",
  },
];

const MEMO_MD = `# IC Memo — Windpark Uckermark Nord (synthetic)

## 1. Recommendation

**PROCEED WITH CONDITIONS.** The asset earns a P50 of 104,5 GWh [E:E-ENERGY-P50] at a net capacity factor of 0,284 [E:E-CF-P50], carrying a minimum DSCR of 1,32× [E:E-DSCR-MIN] and an equity IRR of 8,4 % [E:E-IRR-EQ]. Merchant-tail exposure after the EEG period and the negative-hour trend are the binding risks; both are condition-managed rather than decline-grade.

## 2. Asset & Resource

The fleet stands on 135 m hub heights [E:E-SRC-MASTR-HUB], *upper quartile for its vintage*. LCOE lands at 58,70 €/MWh [E:E-LCOE], comfortably inside the observed award band. One citation in this draft is deliberately broken to demonstrate the orphan-seal state [E:E-DOES-NOT-EXIST].

## 4. Financial Structure

| Metric | Value | Evidence |
|---|---|---|
| P50 energy | 104,5 GWh | [E:E-ENERGY-P50] |
| Min DSCR | 1,32× | [E:E-DSCR-MIN] |
| Equity IRR | 8,4 % | [E:E-IRR-EQ] |
| LCOE | 58,70 €/MWh | [E:E-LCOE] |
| Marktwert (Jun 2026) | 6,12 ct/kWh | [E:E-MW-MARKTWERT] |

## 5. Risks & Mitigants

- **Merchant tail.** Post-EEG revenue reprices at the Marktwert, 6,12 ct/kWh [E:E-MW-MARKTWERT]; a sustained capture-rate slide compresses the equity case.
- **Negative hours.** §51 exposure trends upward; the sculpting already haircuts affected volumes.
- *Mitigant:* covenant package holds a 1,32× floor [E:E-DSCR-MIN] against a 1,20× documentation covenant.

## 7. Conditions Precedent

- Independent energy assessment confirming the P50 within 3 % [E:E-ENERGY-P50].
- Fixed-price O&M term sheet for years 1–10.
`;

const CLAIMS: Claim[] = [
  {
    id: "RC-1",
    agent: "resource",
    statement: "P50 capacity factor of 0,284 sits above the Brandenburg fleet median for the vintage; the uncertainty stack is complete and the availability assumption (97 %) is defensible for a gearbox-era fleet.",
    evidence_ids: ["E-CF-P50", "E-ENERGY-P50"],
    severity: "info",
    confidence: 0.82,
  },
  {
    id: "RC-2",
    agent: "resource",
    statement: "Hub height of 135 m is upper-quartile, but the turbine platform is out of production — long-dated spares risk is real and unpriced in opex.",
    evidence_ids: ["E-SRC-MASTR-HUB"],
    severity: "concern",
    confidence: 0.64,
  },
  {
    id: "RV-1",
    agent: "revenue",
    statement: "Merchant tail after year 20 reprices at the Marktwert; the June 2026 print of 6,12 ct/kWh already reflects a deteriorating capture rate for wind-heavy hours.",
    evidence_ids: ["E-MW-MARKTWERT"],
    severity: "concern",
    confidence: 0.71,
  },
  {
    id: "CC-1",
    agent: "credit",
    statement: "Minimum DSCR of 1,32× clears the 1,20× covenant with headroom, but the sculpting is fragile to a simultaneous price and production downside.",
    evidence_ids: ["E-DSCR-MIN"],
    severity: "concern",
    confidence: 0.77,
  },
];

const REBUTTALS: Rebuttal[] = [
  {
    id: "RB-1",
    agent: "credit",
    statement: "Spares risk is covenant-manageable: a maintenance-reserve condition prices it without moving the DSCR floor.",
    evidence_ids: ["E-DSCR-MIN"],
    severity: "info",
    confidence: 0.6,
    targets_claim_id: "RC-2",
  },
];

const FAILED_VALIDATION = {
  ok: false,
  errors: [
    "paragraph 3 contains numeric literal '58,70 €/MWh' but cites no evidence id",
    "cited id E-DOES-NOT-EXIST does not exist in the evidence store",
    "value 8,7 % deviates 2,1 % relative from cited E-IRR-EQ (0,084)",
  ],
};

export default function MemoDevPage() {
  const [vetoed, setVetoed] = useState(false);
  const [annotations, setAnnotations] = useState<string[]>([]);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-10 px-6 py-8">
      <header className="border-l-2 border-warn bg-bg1 px-4 py-2">
        <h1 className="text-md font-medium text-hi">DEV — synthetic demo data</h1>
        <p className="text-2xs text-mid">
          components/memo harness. Nothing here is real engine output; the memo,
          claims and evidence are hand-written fixtures (incl. one intentional
          orphan citation and a validation-failure variant).
        </p>
      </header>

      <section className="flex flex-col gap-3">
        <h2 className="text-2xs uppercase tracking-wider text-low">
          AgentDebatePanel — canned claims, credit critic still running
        </h2>
        <AgentDebatePanel
          claims={CLAIMS}
          rebuttals={REBUTTALS}
          statuses={{ resource: "done", revenue: "done", credit: "running" }}
        />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-2xs uppercase tracking-wider text-low">
          MemoPaper — validated, verdict stamped{vetoed ? ", vetoed" : ""}
        </h2>
        <MemoPaper
          markdown={MEMO_MD}
          streaming={false}
          verdict={vetoed ? null : "PROCEED_WITH_CONDITIONS"}
          validation={{ ok: true, errors: [] }}
          evidence={EVIDENCE}
          vetoed={vetoed}
        />
        <VetoBar
          onApprove={() => setVetoed(false)}
          onVeto={() => setVetoed(true)}
          onAnnotate={(n) => setAnnotations((a) => [...a, n])}
          vetoed={vetoed}
          annotations={annotations}
        />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-2xs uppercase tracking-wider text-low">
          MemoPaper — validation-failure variant (amber banner, errors verbatim)
        </h2>
        <MemoPaper
          markdown={MEMO_MD}
          streaming={false}
          verdict={null}
          validation={FAILED_VALIDATION}
          evidence={EVIDENCE}
        />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-2xs uppercase tracking-wider text-low">
          MemoPaper — streaming state (gold caret)
        </h2>
        <MemoPaper
          markdown={MEMO_MD.slice(0, 420)}
          streaming
          verdict={null}
          validation={null}
          evidence={EVIDENCE}
        />
      </section>
    </div>
  );
}
