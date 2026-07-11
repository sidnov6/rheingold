"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import type {
  Claim,
  MemoValidation,
  Rebuttal,
  UnderwriteResult,
  Verdict,
} from "@/lib/types";
import { streamMemo } from "@/lib/api";
import { ErrorState } from "@/components/ErrorState";
import { AgentDebatePanel, type AgentStatus } from "./AgentDebatePanel";
import { MemoPaper } from "./MemoPaper";
import { VetoBar } from "./VetoBar";
import "./memo.css";

/**
 * MemoTab (§11 IC Memo tab): AgentDebatePanel above MemoPaper + VetoBar.
 * Showcase-first: a precomputed memo renders instantly (demo works with the
 * API asleep); otherwise "Generate IC Memo" opens the live SSE stream.
 */

export interface MemoTabShowcase {
  memo_markdown: string | null;
  claims: unknown[];
  rebuttals: unknown[];
  validation: { ok: boolean; errors: string[] } | null;
}

export interface MemoTabProps {
  farmId: string;
  result: UnderwriteResult;
  showcase?: MemoTabShowcase | null;
  /**
   * Gold is allowed on ONE primary CTA per view (§3.1). The dossier's left
   * column already carries the gold "Generate IC Memo" CTA — pass false there
   * so this tab's button stays quiet chrome.
   */
  ctaGold?: boolean;
}

type Phase = "idle" | "streaming" | "done" | "error";

function isClaim(x: unknown): x is Claim {
  if (typeof x !== "object" || x === null) return false;
  const c = x as Record<string, unknown>;
  return (
    typeof c.id === "string" &&
    typeof c.statement === "string" &&
    typeof c.agent === "string" &&
    Array.isArray(c.evidence_ids)
  );
}

const asClaims = (arr: unknown[]): Claim[] => arr.filter(isClaim);
const asRebuttals = (arr: unknown[]): Rebuttal[] =>
  arr.filter(
    (x): x is Rebuttal => isClaim(x) && typeof (x as Rebuttal).targets_claim_id === "string",
  );

/** Showcase payloads carry no explicit verdict — recover it from the memo's recommendation. */
function deriveVerdict(markdown: string | null): Verdict | null {
  if (!markdown) return null;
  const head = markdown.slice(0, 800).toUpperCase();
  if (head.includes("PROCEED WITH CONDITIONS") || head.includes("PROCEED_WITH_CONDITIONS")) {
    return "PROCEED_WITH_CONDITIONS";
  }
  if (head.includes("DECLINE")) return "DECLINE";
  if (head.includes("PROCEED")) return "PROCEED";
  return null;
}

const ALL_DONE: Record<string, AgentStatus> = {
  resource: "done",
  revenue: "done",
  credit: "done",
};
const ALL_RUNNING: Record<string, AgentStatus> = {
  resource: "running",
  revenue: "running",
  credit: "running",
};

export default function MemoTab({ farmId, result, showcase = null, ctaGold = true }: MemoTabProps) {
  const hasShowcaseMemo = Boolean(showcase?.memo_markdown);

  const [phase, setPhase] = useState<Phase>(hasShowcaseMemo ? "done" : "idle");
  const [markdown, setMarkdown] = useState<string | null>(showcase?.memo_markdown ?? null);
  const [verdict, setVerdict] = useState<Verdict | null>(
    deriveVerdict(showcase?.memo_markdown ?? null),
  );
  const [validation, setValidation] = useState<MemoValidation | null>(
    showcase?.validation ?? null,
  );
  const [claims, setClaims] = useState<Claim[]>(
    showcase ? asClaims(showcase.claims) : [],
  );
  const [rebuttals, setRebuttals] = useState<Rebuttal[]>(
    showcase ? asRebuttals(showcase.rebuttals) : [],
  );
  const [statuses, setStatuses] = useState<Record<string, AgentStatus>>(
    hasShowcaseMemo ? ALL_DONE : {},
  );
  const [streamError, setStreamError] = useState<string | null>(null);

  // human-override state (§9.3 step 7)
  const [vetoed, setVetoed] = useState(false);
  const [approved, setApproved] = useState(false);
  const [annotations, setAnnotations] = useState<string[]>([]);

  const abortRef = useRef<(() => void) | null>(null);
  useEffect(() => () => abortRef.current?.(), []);

  const generate = useCallback(() => {
    abortRef.current?.();
    setPhase("streaming");
    setMarkdown("");
    setVerdict(null);
    setValidation(null);
    setClaims([]);
    setRebuttals([]);
    setStatuses({ ...ALL_RUNNING });
    setStreamError(null);
    setVetoed(false);
    setApproved(false);

    abortRef.current = streamMemo(
      farmId,
      {},
      result.shocks,
      (e) => {
        switch (e.type) {
          case "agent_status":
            setStatuses((s) => ({ ...s, [e.agent]: e.status }));
            break;
          case "claim":
            setClaims((c) => [...c, e.claim]);
            break;
          case "rebuttal":
            setRebuttals((r) => [...r, e.rebuttal]);
            break;
          case "memo_delta":
            setMarkdown((m) => (m ?? "") + e.text);
            break;
          case "validation":
            setValidation(e.validation);
            break;
          case "gate":
            // gate flags surface through the narrator's Risks section; no panel here
            break;
          case "done":
            setVerdict(e.verdict);
            setPhase("done");
            break;
          case "error":
            setStreamError(e.message);
            setPhase("error");
            break;
        }
      },
      (err) => {
        setStreamError(err.message);
        setPhase("error");
      },
    );
  }, [farmId, result.shocks]);

  if (phase === "idle") {
    return (
      <div className="flex flex-col items-center gap-3 py-16">
        <p className="max-w-md text-center text-base text-mid">
          Three critics read the frozen evidence, argue one round, and a narrator
          writes the memo. Every number must carry a citation seal.
        </p>
        <button
          type="button"
          onClick={generate}
          className={clsx(
            "h-9 rounded-sm px-5 text-base font-medium transition-colors",
            ctaGold
              ? "bg-gold-500 text-bg0 hover:bg-gold-400"
              : "border border-line bg-bg2 text-hi hover:bg-bg1",
          )}
        >
          Generate IC Memo
        </button>
        <p className="num text-2xs text-low">~60–90 s · streams live</p>
      </div>
    );
  }

  if (phase === "error") {
    return (
      <ErrorState
        className="mx-auto max-w-md"
        title="Live engine unavailable"
        detail="The memo stream could not complete — the agent API may be asleep or rate-limited. Showcase farms carry a precomputed memo; this one does not, so there is nothing cached to fall back on."
        hint={streamError ?? undefined}
        action={
          <button
            type="button"
            onClick={generate}
            className="h-8 rounded-sm border border-line bg-bg2 px-4 text-2xs font-medium uppercase tracking-wider text-mid transition-colors hover:text-hi"
          >
            Retry
          </button>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <AgentDebatePanel claims={claims} rebuttals={rebuttals} statuses={statuses} />

      <MemoPaper
        markdown={markdown}
        streaming={phase === "streaming"}
        verdict={vetoed ? null : verdict}
        validation={validation}
        evidence={result.evidence}
        vetoed={vetoed}
      />

      {phase === "done" && (
        <>
          <VetoBar
            onApprove={() => setApproved(true)}
            onVeto={() => setVetoed(true)}
            onAnnotate={(note) => setAnnotations((a) => [...a, note])}
            vetoed={vetoed}
            annotations={annotations}
          />
          <div className="memo-no-print mx-auto flex max-w-[726px] w-full items-center justify-between">
            {approved && !vetoed ? (
              <span className="text-2xs uppercase tracking-wider text-pos">
                Approved for export
              </span>
            ) : (
              <span />
            )}
            <button
              type="button"
              onClick={() => window.print()}
              className="h-8 rounded-sm border border-line bg-bg2 px-4 text-2xs font-medium uppercase tracking-wider text-mid transition-colors hover:text-hi"
            >
              Export PDF
            </button>
          </div>
        </>
      )}
    </div>
  );
}
