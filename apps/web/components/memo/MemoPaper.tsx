"use client";

import { useEffect, useMemo, useRef } from "react";
import clsx from "clsx";
import type { EvidenceItem, MemoValidation, Verdict } from "@/lib/types";
import { renderMemoMarkdown } from "./markdown";
import "./memo.css";

/**
 * MemoPaper — the signature element (§3): a warm paper credit memo lying
 * inside the dark terminal. Newsreader 17/1.6 on --paper with --ink text.
 * The register shift IS the design moment.
 *
 * Paper edge: hairline double border (outer --border frame offset 3px from
 * the --paper-edge border) — no drop shadows, per §3.1.
 */

export interface MemoPaperProps {
  markdown: string | null;
  streaming: boolean;
  verdict: Verdict | null;
  validation: MemoValidation | null;
  evidence: EvidenceItem[];
  vetoed?: boolean;
}

const VERDICT_LABEL: Record<Verdict, string> = {
  PROCEED: "Proceed",
  PROCEED_WITH_CONDITIONS: "Proceed with Conditions",
  DECLINE: "Decline",
};

const VERDICT_COLOR: Record<Verdict, string> = {
  PROCEED: "text-stamp-proceed border-stamp-proceed",
  PROCEED_WITH_CONDITIONS: "text-stamp-conditions border-stamp-conditions",
  DECLINE: "text-stamp-decline border-stamp-decline",
};

/** find nearest scrollable ancestor (assistant-ui auto-scroll pattern) */
function getScrollParent(el: HTMLElement | null): HTMLElement | null {
  let node = el?.parentElement ?? null;
  while (node) {
    const { overflowY } = getComputedStyle(node);
    if (overflowY === "auto" || overflowY === "scroll") return node;
    node = node.parentElement;
  }
  return null;
}

export function MemoPaper({
  markdown,
  streaming,
  verdict,
  validation,
  evidence,
  vetoed = false,
}: MemoPaperProps) {
  const evidenceMap = useMemo(() => {
    const m = new Map<string, EvidenceItem>();
    for (const e of evidence) m.set(e.id, e);
    return m;
  }, [evidence]);

  const body = useMemo(
    () => (markdown ? renderMemoMarkdown(markdown, evidenceMap) : null),
    [markdown, evidenceMap],
  );

  // Auto-scroll to bottom while streaming, unless the user scrolled up.
  const bottomRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);
  useEffect(() => {
    if (!streaming) return;
    stickRef.current = true;
    const parent = getScrollParent(bottomRef.current);
    // No scrollable ancestor → the window scrolls (dossier-page case).
    const distanceFromBottom = () =>
      parent
        ? parent.scrollHeight - parent.scrollTop - parent.clientHeight
        : (document.scrollingElement?.scrollHeight ?? 0) - window.scrollY - window.innerHeight;
    const onScroll = () => {
      stickRef.current = distanceFromBottom() < 48;
    };
    const target: HTMLElement | Window = parent ?? window;
    target.addEventListener("scroll", onScroll, { passive: true });
    return () => target.removeEventListener("scroll", onScroll);
  }, [streaming]);
  useEffect(() => {
    if (streaming && stickRef.current) {
      bottomRef.current?.scrollIntoView({ block: "end" });
    }
  }, [markdown, streaming]);

  return (
    <div className="w-full">
      {validation && !validation.ok && (
        <div
          role="alert"
          className="memo-no-print mx-auto mb-3 max-w-[726px] border-l-2 border-warn bg-bg1 px-4 py-3"
        >
          <div className="text-2xs font-semibold uppercase tracking-wider text-warn">
            Citation-integrity validation failed — memo shown as-is, honesty is the feature
          </div>
          <ul className="mt-2 space-y-1">
            {validation.errors.map((err, i) => (
              <li key={i} className="num text-2xs text-mid">
                {err}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* hairline double edge: outer --border frame, inner --paper-edge border */}
      <div className="memo-paper-frame mx-auto max-w-[726px] border border-line p-[3px]">
        <article
          className={clsx(
            "memo-paper relative border border-paper-edge bg-paper px-10 pb-12 font-display text-[17px] leading-[1.6] text-ink",
            // reserve headroom for the stamp so it lands in whitespace, not on the title
            verdict ? "pt-28" : "pt-12",
          )}
          aria-busy={streaming}
        >
          {verdict && (
            <div
              aria-label={`Verdict: ${VERDICT_LABEL[verdict]}`}
              className={clsx(
                "memo-stamp absolute right-8 top-8 max-w-[220px] select-none border-[3px] px-3 py-1.5 text-center font-display text-md font-bold uppercase leading-tight tracking-[0.14em]",
                VERDICT_COLOR[verdict],
              )}
            >
              {VERDICT_LABEL[verdict]}
            </div>
          )}

          {vetoed && (
            <div
              aria-label="Draft — vetoed"
              className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center overflow-hidden"
            >
              <span className="-rotate-[24deg] whitespace-nowrap font-display text-[64px] font-bold uppercase tracking-[0.2em] text-ink opacity-10">
                Draft — Vetoed
              </span>
            </div>
          )}

          {body === null || (markdown !== null && markdown.length === 0 && streaming) ? (
            <div className="py-16 text-center">
              {streaming ? (
                <p className="italic text-ink opacity-60">
                  The committee is drafting
                  <span className="memo-caret" aria-hidden />
                </p>
              ) : (
                <p className="italic text-ink opacity-50">No memo yet.</p>
              )}
            </div>
          ) : (
            <div>
              {body}
              {streaming && <span className="memo-caret" aria-hidden />}
            </div>
          )}
          <div ref={bottomRef} aria-hidden />
        </article>
      </div>
    </div>
  );
}
