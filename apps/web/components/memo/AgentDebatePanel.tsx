"use client";

import clsx from "clsx";
import type { Claim, Rebuttal } from "@/lib/types";
import { fmtInt } from "@/lib/format";
import "./memo.css";

/**
 * AgentDebatePanel (§9.3, §11): three critic columns; claims stream in as
 * severity-tinted cards, rebuttals nest under their target claim with ⇄.
 * Quiet chrome — gold appears only on evidence-id chips (data).
 */

export type AgentStatus = "running" | "done" | "error";

export interface AgentDebatePanelProps {
  claims: Claim[];
  rebuttals: Rebuttal[];
  statuses: Record<string, AgentStatus>;
}

const AGENTS: { key: Claim["agent"]; label: string }[] = [
  { key: "resource", label: "Resource Critic" },
  { key: "revenue", label: "Revenue Critic" },
  { key: "credit", label: "Credit Critic" },
];

const SEVERITY_BORDER: Record<Claim["severity"], string> = {
  info: "border-l-line",
  concern: "border-l-warn",
  dealbreaker: "border-l-neg",
};

const SEVERITY_TEXT: Record<Claim["severity"], string> = {
  info: "text-low",
  concern: "text-warn",
  dealbreaker: "text-neg",
};

function StatusDot({ status }: { status: AgentStatus | undefined }) {
  if (status === "running") {
    return (
      <span
        className="memo-pulse-dot inline-block h-1.5 w-1.5 rounded-full bg-rhine-300"
        title="running"
      />
    );
  }
  if (status === "error") {
    return <span className="inline-block h-1.5 w-1.5 rounded-full bg-neg" title="error" />;
  }
  if (status === "done") {
    return <span className="inline-block h-1.5 w-1.5 rounded-full bg-pos" title="done" />;
  }
  return <span className="inline-block h-1.5 w-1.5 rounded-full bg-bg2" title="idle" />;
}

function EvidenceChips({ ids }: { ids: string[] }) {
  if (ids.length === 0) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      {ids.map((id) => (
        <span key={id} className="num rounded-sm bg-gold-dim px-1 py-px text-[10px] leading-3 text-gold-500">
          {id}
        </span>
      ))}
    </div>
  );
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, confidence)) * 100);
  return (
    <div className="mt-2 flex items-center gap-2">
      <div className="h-px flex-1 bg-bg2">
        <div className="h-px bg-rhine-500" style={{ width: `${pct}%` }} />
      </div>
      <span className="num text-[10px] leading-3 text-low">{fmtInt(pct)} %</span>
    </div>
  );
}

function ClaimCard({ claim, rebuttals }: { claim: Claim; rebuttals: Rebuttal[] }) {
  return (
    <div className={clsx("border-l-2 bg-bg1 px-2.5 py-2", SEVERITY_BORDER[claim.severity])}>
      <div className="flex items-baseline justify-between gap-2">
        <span className={clsx("text-[10px] uppercase tracking-wider", SEVERITY_TEXT[claim.severity])}>
          {claim.severity}
        </span>
        <span className="num text-[10px] text-low">{claim.id}</span>
      </div>
      <p className="mt-1 text-data text-hi">{claim.statement}</p>
      <EvidenceChips ids={claim.evidence_ids} />
      <ConfidenceBar confidence={claim.confidence} />
      {rebuttals.map((r) => (
        <div
          key={r.id}
          className={clsx("mt-2 border-l-2 bg-bg2 px-2 py-1.5", SEVERITY_BORDER[r.severity])}
        >
          <div className="flex items-baseline gap-1.5">
            <span aria-hidden className="text-low">
              ⇄
            </span>
            <span className="text-[10px] uppercase tracking-wider text-low">
              {r.agent} rebuts
            </span>
            <span className="num ml-auto text-[10px] text-low">{r.id}</span>
          </div>
          <p className="mt-0.5 text-2xs text-mid">{r.statement}</p>
          <EvidenceChips ids={r.evidence_ids} />
        </div>
      ))}
    </div>
  );
}

export function AgentDebatePanel({ claims, rebuttals, statuses }: AgentDebatePanelProps) {
  return (
    <div className="memo-no-print grid grid-cols-1 gap-px border border-line bg-line md:grid-cols-3">
      {AGENTS.map((agent) => {
        const agentClaims = claims.filter((c) => c.agent === agent.key);
        const status = statuses[agent.key];
        return (
          <section key={agent.key} className="flex min-w-0 flex-col bg-bg0" aria-label={agent.label}>
            <header className="flex h-8 items-center gap-2 border-b border-line bg-bg1 px-2.5">
              <StatusDot status={status} />
              <h3 className="text-2xs font-medium uppercase tracking-wider text-mid">
                {agent.label}
              </h3>
              <span className="num ml-auto text-[10px] text-low">
                {fmtInt(agentClaims.length)}
              </span>
            </header>
            <div className="flex flex-col gap-1.5 p-1.5">
              {agentClaims.length === 0 && (
                <p className="px-1 py-2 text-2xs italic text-low">
                  {status === "running"
                    ? "Examining evidence…"
                    : status === "error"
                      ? "Critic failed."
                      : "No claims."}
                </p>
              )}
              {agentClaims.map((claim) => (
                <ClaimCard
                  key={claim.id}
                  claim={claim}
                  rebuttals={rebuttals.filter((r) => r.targets_claim_id === claim.id)}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
