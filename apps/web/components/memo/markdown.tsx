import React from "react";
import type { EvidenceItem } from "@/lib/types";
import { CitationSeal } from "./CitationSeal";

/**
 * Minimal, safe markdown renderer for the IC memo (§9.7). No extra deps, no
 * dangerouslySetInnerHTML: the source is tokenized and emitted as React
 * elements, so any HTML in the input is rendered inert as escaped text.
 *
 * Supported: # / ## / ### headings, paragraphs, **bold**, *italic*,
 * pipe tables (the §9.7 metrics table), "- " lists, and [E:ID] citation
 * tokens which become <CitationSeal/> chips.
 */

const INLINE_RE = /(\[E:[A-Za-z0-9_.-]+\]|\*\*[^*]+\*\*|\*[^*\n]+\*)/g;
const CITE_RE = /^\[E:([A-Za-z0-9_.-]+)\]$/;
// numeric literals incl. %, ×, ct/kWh, €/MWh, M€ … set in mono per §3.2
const NUM_RE = /\d[\d.,]*(?:\s?(?:%|×|bps|pp|ct\/kWh|€\/MWh|EUR\/MWh|Mrd€|M€|k€|€|GWh|MWh|MW|a))?/g;

/** Wrap numeric literals in .num spans (IBM Plex Mono, tabular figures). */
function renderTextWithNums(text: string, keyPrefix: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let last = 0;
  let i = 0;
  NUM_RE.lastIndex = 0;
  for (let m = NUM_RE.exec(text); m !== null; m = NUM_RE.exec(text)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(
      <span key={`${keyPrefix}-n${i++}`} className="num text-[0.88em]">
        {m[0]}
      </span>,
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function renderInline(
  text: string,
  evidenceMap: Map<string, EvidenceItem>,
  keyPrefix: string,
): React.ReactNode[] {
  const parts = text.split(INLINE_RE);
  const out: React.ReactNode[] = [];
  parts.forEach((part, idx) => {
    if (!part) return;
    const key = `${keyPrefix}-${idx}`;
    const cite = CITE_RE.exec(part);
    if (cite) {
      const id = cite[1];
      out.push(<CitationSeal key={key} id={id} evidence={evidenceMap.get(id)} />);
      return;
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      out.push(
        <strong key={key} className="font-semibold">
          {renderInline(part.slice(2, -2), evidenceMap, key)}
        </strong>,
      );
      return;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      out.push(
        <em key={key}>{renderInline(part.slice(1, -1), evidenceMap, key)}</em>,
      );
      return;
    }
    out.push(...renderTextWithNums(part, key));
  });
  return out;
}

type Block =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "para"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "table"; header: string[]; rows: string[][] };

const TABLE_SEP_CELL = /^\s*:?-{2,}:?\s*$/;

function splitRow(line: string): string[] {
  const cells = line.split("|").map((c) => c.trim());
  if (cells.length > 0 && cells[0] === "") cells.shift();
  if (cells.length > 0 && cells[cells.length - 1] === "") cells.pop();
  return cells;
}

export function parseBlocks(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed === "") {
      i++;
      continue;
    }
    const h = /^(#{1,3})\s+(.*)$/.exec(trimmed);
    if (h) {
      blocks.push({ kind: "heading", level: h[1].length as 1 | 2 | 3, text: h[2] });
      i++;
      continue;
    }
    if (trimmed.startsWith("|")) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        tableLines.push(lines[i].trim());
        i++;
      }
      const rows = tableLines.map(splitRow);
      const sepIdx = rows.findIndex(
        (r) => r.length > 0 && r.every((c) => TABLE_SEP_CELL.test(c)),
      );
      if (sepIdx >= 1) {
        blocks.push({
          kind: "table",
          header: rows[sepIdx - 1],
          rows: rows.filter((_, ri) => ri !== sepIdx && ri !== sepIdx - 1),
        });
      } else {
        blocks.push({ kind: "table", header: rows[0] ?? [], rows: rows.slice(1) });
      }
      continue;
    }
    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*]\s+/, ""));
        i++;
      }
      blocks.push({ kind: "list", items });
      continue;
    }
    // paragraph: consume until blank line or a new block opener
    const para: string[] = [trimmed];
    i++;
    while (i < lines.length) {
      const t = lines[i].trim();
      if (t === "" || t.startsWith("#") || t.startsWith("|") || /^[-*]\s+/.test(t)) break;
      para.push(t);
      i++;
    }
    blocks.push({ kind: "para", text: para.join(" ") });
  }
  return blocks;
}

/** true if a cell is numeric-ish → right-aligned mono per terminal density rules */
function isNumericCell(cell: string): boolean {
  const stripped = cell
    .replace(/\[E:[A-Za-z0-9_.-]+\]/g, "")
    .replace(/\*/g, "")
    .trim();
  return /^[-+−]?\d/.test(stripped);
}

export function renderMemoMarkdown(
  markdown: string,
  evidenceMap: Map<string, EvidenceItem>,
): React.ReactNode[] {
  const blocks = parseBlocks(markdown);
  return blocks.map((block, bi) => {
    const key = `b${bi}`;
    switch (block.kind) {
      case "heading": {
        if (block.level === 1) {
          return (
            <h1 key={key} className="mb-4 mt-2 font-display text-xl font-semibold leading-tight text-ink">
              {renderInline(block.text, evidenceMap, key)}
            </h1>
          );
        }
        if (block.level === 2) {
          return (
            <h2
              key={key}
              className="mb-3 mt-7 border-b border-paper-edge pb-1 font-display text-lg font-semibold text-ink"
            >
              {renderInline(block.text, evidenceMap, key)}
            </h2>
          );
        }
        return (
          <h3 key={key} className="mb-2 mt-5 font-display text-md font-semibold text-ink">
            {renderInline(block.text, evidenceMap, key)}
          </h3>
        );
      }
      case "para":
        return (
          <p key={key} className="mb-3">
            {renderInline(block.text, evidenceMap, key)}
          </p>
        );
      case "list":
        return (
          <ul key={key} className="mb-3 ml-5 list-disc space-y-1 marker:text-[color:var(--paper-edge)]">
            {block.items.map((item, li) => (
              <li key={`${key}-li${li}`}>{renderInline(item, evidenceMap, `${key}-li${li}`)}</li>
            ))}
          </ul>
        );
      case "table":
        return (
          <div key={key} className="mb-4 overflow-x-auto">
            <table className="w-full border-collapse text-data">
              <thead>
                <tr>
                  {block.header.map((cell, ci) => (
                    <th
                      key={`${key}-h${ci}`}
                      className={
                        "border-b border-[color:var(--ink)] px-2 py-1.5 font-sans text-2xs font-semibold uppercase tracking-wider " +
                        (ci === 0 ? "text-left" : "text-right")
                      }
                    >
                      {renderInline(cell, evidenceMap, `${key}-h${ci}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, ri) => (
                  <tr key={`${key}-r${ri}`} className="border-b border-paper-edge">
                    {row.map((cell, ci) => {
                      const numeric = ci > 0 && isNumericCell(cell);
                      return (
                        <td
                          key={`${key}-r${ri}c${ci}`}
                          className={
                            "h-8 px-2 py-1 align-middle " +
                            (numeric ? "num text-right" : ci === 0 ? "text-left font-sans" : "text-right")
                          }
                        >
                          {renderInline(cell, evidenceMap, `${key}-r${ri}c${ci}`)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
    }
  });
}
