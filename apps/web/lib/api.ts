/**
 * API client. Showcase-first (§15): farm dossiers try /public/showcase/{id}.json
 * before the live API, so the demo works with the API asleep.
 */

import type {
  BacktestResult,
  Claim,
  FarmDetail,
  FleetFarm,
  GateFlag,
  MemoEvent,
  MemoValidation,
  Rebuttal,
  Shocks,
  UnderwriteResult,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body.error ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const fetchFleet = () => getJson<FleetFarm[]>(`${API_URL}/api/fleet`);

export const fetchFarm = (id: string) => getJson<FarmDetail>(`${API_URL}/api/farm/${id}`);

export interface ShowcasePayload {
  farm: FarmDetail;
  underwrite: UnderwriteResult;
  presets: Record<string, UnderwriteResult>;
  memo_markdown: string | null;
  claims: unknown[];
  rebuttals: unknown[];
  gate_flags: unknown[];
  validation: { ok: boolean; errors: string[] } | null;
}

/** null when the farm is not a precomputed showcase farm. */
export async function fetchShowcase(id: string): Promise<ShowcasePayload | null> {
  const res = await fetch(`/showcase/${id}.json`);
  if (!res.ok) return null;
  return (await res.json()) as ShowcasePayload;
}

export const underwrite = (
  farmId: string,
  overrides: Record<string, unknown> = {},
  shocks: Partial<Shocks> = {},
) =>
  getJson<UnderwriteResult>(`${API_URL}/api/underwrite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      farm_id: farmId,
      assumptions_overrides: overrides,
      shocks,
    }),
  });

export const fetchBacktest = () => getJson<BacktestResult>(`${API_URL}/api/backtest`);

/**
 * Map an SSE (event-name, flat-payload) pair onto the MemoEvent union the UI
 * consumes. The server emits the type in the `event:` line and a flat data
 * object; claim/rebuttal/validation get wrapped to match the union.
 */
function toMemoEvent(eventType: string, p: Record<string, unknown>): MemoEvent {
  switch (eventType) {
    case "claim":
      return { type: "claim", claim: p as unknown as Claim };
    case "rebuttal":
      return { type: "rebuttal", rebuttal: p as unknown as Rebuttal };
    case "validation":
      return { type: "validation", validation: p as unknown as MemoValidation };
    case "gate":
      return { type: "gate", flags: (p.flags ?? []) as GateFlag[] };
    default:
      // agent_status / memo_delta / done / error carry their fields flat.
      return { type: eventType, ...p } as unknown as MemoEvent;
  }
}

/**
 * POST-based SSE for /api/memo. Returns an abort function.
 */
export function streamMemo(
  farmId: string,
  overrides: Record<string, unknown>,
  shocks: Partial<Shocks>,
  onEvent: (e: MemoEvent) => void,
  onError: (err: Error) => void,
): () => void {
  const ctrl = new AbortController();
  (async () => {
    try {
      const res = await fetch(`${API_URL}/api/memo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ farm_id: farmId, assumptions_overrides: overrides, shocks }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        throw new ApiError(res.status, `memo stream failed (${res.status})`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        // Normalise CRLF (sse-starlette emits \r\n) so frames split cleanly.
        buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
        const frames = buf.split("\n\n");
        buf = frames.pop() ?? "";
        for (const frame of frames) {
          let eventType = "";
          const dataLines: string[] = [];
          for (const line of frame.split("\n")) {
            if (line.startsWith("event:")) eventType = line.slice(6).trim();
            else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
          }
          if (!eventType || dataLines.length === 0) continue;
          let payload: Record<string, unknown>;
          try {
            payload = JSON.parse(dataLines.join("\n"));
          } catch {
            continue; // malformed frame
          }
          onEvent(toMemoEvent(eventType, payload));
        }
      }
    } catch (err) {
      if (!ctrl.signal.aborted) onError(err instanceof Error ? err : new Error(String(err)));
    }
  })();
  return () => ctrl.abort();
}
