/**
 * API client. Showcase-first (§15): farm dossiers try /public/showcase/{id}.json
 * before the live API, so the demo works with the API asleep.
 */

import type {
  BacktestResult,
  FarmDetail,
  FleetFarm,
  MemoEvent,
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
        buf += decoder.decode(value, { stream: true });
        // SSE frames are separated by a blank line
        const frames = buf.split("\n\n");
        buf = frames.pop() ?? "";
        for (const frame of frames) {
          const dataLines = frame
            .split("\n")
            .filter((l) => l.startsWith("data:"))
            .map((l) => l.slice(5).trim());
          if (dataLines.length === 0) continue;
          try {
            onEvent(JSON.parse(dataLines.join("\n")) as MemoEvent);
          } catch {
            /* ignore malformed frame */
          }
        }
      }
    } catch (err) {
      if (!ctrl.signal.aborted) onError(err instanceof Error ? err : new Error(String(err)));
    }
  })();
  return () => ctrl.abort();
}
