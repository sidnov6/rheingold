"use client";

/**
 * /methodology (§11) — the engine, documented. Accordion of §8 formulas,
 * assumptions table (mirrors defaults.yaml), data lineage, licenses, glossary.
 * Config IS documentation.
 */

import { useEffect, useState } from "react";
import * as Accordion from "@radix-ui/react-accordion";
import {
  ARCHITECTURE_MMD,
  DEFAULT_ASSUMPTIONS,
  FORMULA_SECTIONS,
  LICENSE_TABLE,
  MODEL_CARD_URL,
} from "@/lib/methodology-content";
import { GLOSSARY, GlossaryTerm } from "@/components/Glossary";
import { API_URL } from "@/lib/api";

interface HealthPayload {
  build_sha?: string;
  data_vintages?: Record<string, string>;
  [k: string]: unknown;
}

function SectionHeading({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="text-lg font-medium text-hi">
      {children}
    </h2>
  );
}

export default function MethodologyPage() {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [healthError, setHealthError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/api/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: HealthPayload) => {
        if (!cancelled) setHealth(d);
      })
      .catch(() => {
        if (!cancelled) setHealthError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const vintages = health?.data_vintages ?? null;

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <header>
        <p className="text-2xs uppercase tracking-widest text-low">Methodology</p>
        <h1 className="mt-1 font-display text-xl font-medium text-hi">
          A deterministic engine, shown in full
        </h1>
        <p className="mt-2 max-w-3xl text-base text-mid">
          Every number in RHEINGOLD comes from the pure-function finance engine
          below — no network, no randomness, no language model. Same inputs,
          identical outputs, always. These are the actual formulas (spec §8),
          the actual defaults, and the actual licenses.
        </p>
      </header>

      {/* ---------------------------------------------------- §8 formulas */}
      <section className="mt-10" aria-labelledby="formulas-h">
        <SectionHeading id="formulas-h">The engine, formula by formula</SectionHeading>
        <Accordion.Root
          type="multiple"
          defaultValue={["energy"]}
          className="mt-4 divide-y divide-[var(--border)] rounded border border-line bg-bg1"
        >
          {FORMULA_SECTIONS.map((s) => (
            <Accordion.Item key={s.id} value={s.id}>
              <Accordion.Header>
                <Accordion.Trigger className="group flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-bg2">
                  <span className="flex items-baseline gap-3">
                    <span className="num text-2xs text-low">{s.ref}</span>
                    <span className="text-base font-medium text-hi">{s.title}</span>
                  </span>
                  <span
                    aria-hidden
                    className="text-low transition-transform duration-150 group-data-[state=open]:rotate-90"
                  >
                    ›
                  </span>
                </Accordion.Trigger>
              </Accordion.Header>
              <Accordion.Content className="overflow-hidden px-4 pb-4">
                <p className="max-w-3xl text-data leading-relaxed text-mid">{s.intro}</p>
                <div className="mt-3 overflow-x-auto rounded border border-line bg-bg0">
                  <pre className="num whitespace-pre px-4 py-3 text-data leading-relaxed text-hi">
                    {s.formulas}
                  </pre>
                </div>
                {s.notes && <p className="mt-2 max-w-3xl text-2xs text-low">{s.notes}</p>}
              </Accordion.Content>
            </Accordion.Item>
          ))}
        </Accordion.Root>
      </section>

      {/* ------------------------------------------------- assumptions */}
      <section className="mt-10" aria-labelledby="assumptions-h">
        <SectionHeading id="assumptions-h">Default assumptions</SectionHeading>
        <p className="mt-2 max-w-3xl text-data text-mid">
          Mirrors <code className="num text-2xs">packages/engine/rheingold_engine/defaults.yaml</code>{" "}
          field-for-field — every value carries its source. Vintage-dependent
          values (capex, opex, interest) are overridden per farm from{" "}
          <code className="num text-2xs">cost_vintages.csv</code> by commissioning year.
        </p>
        <div className="mt-3 overflow-x-auto rounded border border-line">
          <table className="w-full min-w-[640px] border-collapse text-data">
            <thead>
              <tr className="h-8 bg-bg2 text-left text-2xs uppercase tracking-wider text-low">
                <th className="px-3 font-medium">Field</th>
                <th className="px-3 text-right font-medium">Default</th>
                <th className="px-3 font-medium">Source</th>
              </tr>
            </thead>
            <tbody>
              {DEFAULT_ASSUMPTIONS.map((row) => (
                <tr key={row.field} className="h-8 border-t border-line align-top hover:bg-bg2">
                  <td className="num px-3 py-1.5 text-mid">{row.field}</td>
                  <td className={`px-3 py-1.5 text-right ${row.numeric ? "num text-hi" : "num text-mid"}`}>
                    {row.value}
                  </td>
                  <td className="px-3 py-1.5 text-mid">{row.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ----------------------------------------------- data vintages */}
      <section className="mt-10" aria-labelledby="vintages-h">
        <SectionHeading id="vintages-h">Data vintages</SectionHeading>
        <p className="mt-2 max-w-3xl text-data text-mid">
          Live from <code className="num text-2xs">GET /api/health</code> — the max
          date of each mart table baked into the running API.
        </p>
        <div className="mt-3 rounded border border-line bg-bg1 px-4 py-3">
          {vintages && Object.keys(vintages).length > 0 ? (
            <dl className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
              {Object.entries(vintages).map(([k, v]) => (
                <div key={k} className="flex items-baseline justify-between gap-4 border-b border-line pb-1.5">
                  <dt className="text-data text-mid">{k}</dt>
                  <dd className="num text-data text-hi">{String(v)}</dd>
                </div>
              ))}
            </dl>
          ) : healthError ? (
            <p className="text-data text-low">
              API asleep — vintages unavailable right now. The assumptions and
              formulas above are static and remain authoritative.
            </p>
          ) : (
            <p className="num animate-pulse text-data text-low">querying /api/health…</p>
          )}
          {health?.build_sha && (
            <p className="mt-2 text-2xs text-low">
              build <span className="num">{String(health.build_sha)}</span>
            </p>
          )}
        </div>
      </section>

      {/* ------------------------------------------------- data lineage */}
      <section className="mt-10" aria-labelledby="lineage-h">
        <SectionHeading id="lineage-h">Data lineage</SectionHeading>
        <p className="mt-2 max-w-3xl text-data text-mid">
          The pipeline, as committed in{" "}
          <code className="num text-2xs">docs/architecture.mmd</code> (Mermaid
          source, rendered by GitHub in the README). Registry and market data
          flow left to right; the language models only ever see the frozen
          EvidenceStore.
        </p>
        <div className="mt-3 overflow-x-auto rounded border border-line bg-bg0">
          <pre className="num whitespace-pre px-4 py-3 text-2xs leading-relaxed text-mid">
            {ARCHITECTURE_MMD}
          </pre>
        </div>
      </section>

      {/* ----------------------------------------------------- licenses */}
      <section className="mt-10" aria-labelledby="licenses-h">
        <SectionHeading id="licenses-h">Data sources & licenses</SectionHeading>
        <div className="mt-3 overflow-x-auto rounded border border-line">
          <table className="w-full min-w-[640px] border-collapse text-data">
            <thead>
              <tr className="h-8 bg-bg2 text-left text-2xs uppercase tracking-wider text-low">
                <th className="px-3 font-medium">Source</th>
                <th className="px-3 font-medium">Used for</th>
                <th className="px-3 font-medium">License</th>
              </tr>
            </thead>
            <tbody>
              {LICENSE_TABLE.map((row) => (
                <tr key={row.source} className="border-t border-line align-top hover:bg-bg2">
                  <td className="px-3 py-2 text-hi">{row.source}</td>
                  <td className="px-3 py-2 text-mid">{row.whatFor}</td>
                  <td className="px-3 py-2">
                    <span
                      className={
                        row.license.includes("NON-COMMERCIAL")
                          ? "font-medium text-warn"
                          : "text-mid"
                      }
                    >
                      {row.license}
                    </span>
                    {row.note && <p className="mt-1 text-2xs text-low">{row.note}</p>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-2xs text-low">
          renewables.ninja profiles are CC BY-NC 4.0 — this project is strictly
          non-commercial. Full lineage and limitations:{" "}
          <a
            href={MODEL_CARD_URL}
            className="underline decoration-dotted underline-offset-2 transition-colors hover:text-mid"
          >
            MODEL_CARD.md
          </a>
          .
        </p>
      </section>

      {/* ----------------------------------------------------- glossary */}
      <section className="mb-6 mt-10" aria-labelledby="glossary-h">
        <SectionHeading id="glossary-h">Glossary</SectionHeading>
        <p className="mt-2 max-w-3xl text-data text-mid">
          The domain terms used across dossiers and memos (hover any dotted term
          anywhere in the app).
        </p>
        <div className="mt-3 overflow-x-auto rounded border border-line">
          <table className="w-full min-w-[520px] border-collapse text-data">
            <tbody>
              {Object.entries(GLOSSARY).map(([term, def]) => (
                <tr key={term} className="h-8 border-t border-line first:border-t-0 hover:bg-bg2">
                  <td className="w-64 px-3 py-1.5 text-hi">
                    <GlossaryTerm term={term} />
                  </td>
                  <td className="px-3 py-1.5 text-mid">{def}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
