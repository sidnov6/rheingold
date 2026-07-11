"use client";

import { useState } from "react";
import clsx from "clsx";
import { fmtInt } from "@/lib/format";
import "./memo.css";

/**
 * VetoBar (§9.3 step 7): quiet human-override strip under the memo.
 * Approve / annotate (inline input) / veto. Veto is destructive-styled;
 * a veto forces DRAFT — VETOED on the export. The human is always senior.
 */

export interface VetoBarProps {
  onApprove: () => void;
  onVeto: () => void;
  onAnnotate: (note: string) => void;
  vetoed: boolean;
  annotations: string[];
}

export function VetoBar({ onApprove, onVeto, onAnnotate, vetoed, annotations }: VetoBarProps) {
  const [annotating, setAnnotating] = useState(false);
  const [note, setNote] = useState("");

  const submitNote = () => {
    const trimmed = note.trim();
    if (trimmed) onAnnotate(trimmed);
    setNote("");
    setAnnotating(false);
  };

  return (
    <div className="memo-no-print mx-auto max-w-[726px] border border-line bg-bg1">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2">
        <button
          type="button"
          onClick={onApprove}
          disabled={vetoed}
          className="h-7 rounded-sm border border-line bg-bg2 px-3 text-2xs font-medium uppercase tracking-wider text-mid transition-colors hover:text-hi disabled:cursor-not-allowed disabled:opacity-40"
        >
          Approve
        </button>
        <button
          type="button"
          onClick={() => setAnnotating((v) => !v)}
          className={clsx(
            "h-7 rounded-sm border border-line px-3 text-2xs font-medium uppercase tracking-wider transition-colors",
            annotating ? "bg-bg2 text-hi" : "bg-bg2 text-mid hover:text-hi",
          )}
        >
          Annotate
        </button>
        <button
          type="button"
          onClick={onVeto}
          disabled={vetoed}
          className="h-7 rounded-sm border border-neg px-3 text-2xs font-medium uppercase tracking-wider text-neg transition-colors hover:bg-neg hover:text-hi disabled:cursor-not-allowed disabled:opacity-60"
        >
          {vetoed ? "Vetoed" : "Veto"}
        </button>
        {vetoed && (
          <span className="text-2xs uppercase tracking-wider text-neg">
            Export will read DRAFT — VETOED
          </span>
        )}
        <span className="ml-auto text-2xs italic text-low">The human is always senior.</span>
      </div>

      {annotating && (
        <div className="flex items-center gap-2 border-t border-line px-3 py-2">
          <input
            autoFocus
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitNote();
              if (e.key === "Escape") {
                setNote("");
                setAnnotating(false);
              }
            }}
            placeholder="Annotation — attached to the memo record"
            aria-label="Annotation"
            className="h-7 min-w-0 flex-1 rounded-sm border border-line bg-bg0 px-2 text-data text-hi placeholder:text-low focus:outline-none"
          />
          <button
            type="button"
            onClick={submitNote}
            className="h-7 rounded-sm border border-line bg-bg2 px-3 text-2xs font-medium uppercase tracking-wider text-mid transition-colors hover:text-hi"
          >
            Add
          </button>
        </div>
      )}

      {annotations.length > 0 && (
        <ul className="border-t border-line px-3 py-2">
          <li className="mb-1 text-[10px] uppercase tracking-wider text-low">
            Annotations ({fmtInt(annotations.length)})
          </li>
          {annotations.map((a, i) => (
            <li key={i} className="flex gap-2 py-0.5 text-2xs text-mid">
              <span aria-hidden className="text-low">
                ›
              </span>
              {a}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
