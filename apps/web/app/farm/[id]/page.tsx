"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import * as Tabs from "@radix-ui/react-tabs";
import clsx from "clsx";
import type { FarmDetail, Shocks, Verdict } from "@/lib/types";
import { DEFAULT_SHOCKS } from "@/lib/types";
import {
  ApiError,
  fetchFarm,
  fetchShowcase,
  underwrite,
  type ShowcasePayload,
} from "@/lib/api";
import { useScenario } from "@/stores/scenario";
import { ErrorState } from "@/components/ErrorState";
import { VerdictChip } from "@/components/VerdictChip";
import { MemoTab } from "@/components/memo";
import { IdentityCard } from "@/components/dossier/IdentityCard";
import { OverviewTab } from "@/components/dossier/OverviewTab";
import { EnergyTab } from "@/components/dossier/EnergyTab";
import { RevenueTab } from "@/components/dossier/RevenueTab";
import { DebtTab } from "@/components/dossier/DebtTab";
import { ScenariosTab } from "@/components/dossier/ScenariosTab";

/**
 * /farm/[id] — the dossier (§11). Left 340px identity column with the page's
 * single gold CTA; right, the six tabs. Data flow per §15: showcase JSON
 * first (instant, works with the API asleep), live API for everything else.
 * Shocks debounce 250ms into POST /api/underwrite; showcase presets short-
 * circuit to their precomputed results.
 */

type TabKey = "overview" | "energy" | "revenue" | "debt" | "scenarios" | "memo";

const TABS: { key: TabKey; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "energy", label: "Energy" },
  { key: "revenue", label: "Revenue" },
  { key: "debt", label: "Debt" },
  { key: "scenarios", label: "Scenarios" },
  { key: "memo", label: "IC Memo" },
];

const SHOCK_KEYS = Object.keys(DEFAULT_SHOCKS) as (keyof Shocks)[];
const isDefaultShocks = (s: Shocks) => SHOCK_KEYS.every((k) => s[k] === DEFAULT_SHOCKS[k]);

/** Showcase payloads carry no explicit verdict — recover it from the memo head. */
function deriveVerdict(markdown: string | null | undefined): Verdict | null {
  if (!markdown) return null;
  const head = markdown.slice(0, 800).toUpperCase();
  if (head.includes("PROCEED WITH CONDITIONS") || head.includes("PROCEED_WITH_CONDITIONS")) {
    return "PROCEED_WITH_CONDITIONS";
  }
  if (head.includes("DECLINE")) return "DECLINE";
  if (head.includes("PROCEED")) return "PROCEED";
  return null;
}

function DossierSkeleton() {
  return (
    <div className="min-w-0 flex-1 p-6" aria-busy="true" aria-label="Loading dossier">
      <div className="flex gap-2">
        {TABS.map((t) => (
          <div key={t.key} className="h-8 w-20 animate-pulse rounded bg-bg2" />
        ))}
      </div>
      <div className="mt-6 grid grid-cols-2 gap-3 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded border border-line bg-bg2" />
        ))}
      </div>
      <div className="mt-6 h-72 animate-pulse rounded border border-line bg-bg2" />
    </div>
  );
}

export default function FarmDossierPage({ params }: { params: { id: string } }) {
  const farmId = params.id;

  const [farm, setFarm] = useState<FarmDetail | null>(null);
  const [showcase, setShowcase] = useState<ShowcasePayload | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [bootError, setBootError] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);
  const [engineWaking, setEngineWaking] = useState(false);
  const [tab, setTab] = useState<TabKey>("overview");

  const shocks = useScenario((s) => s.shocks);
  const activePreset = useScenario((s) => s.activePreset);
  const result = useScenario((s) => s.result);
  const baseResult = useScenario((s) => s.baseResult);
  const loading = useScenario((s) => s.loading);

  // monotonically increasing sequence to drop stale underwrite responses
  const seqRef = useRef(0);

  // ---- mount: showcase first, then live farm + base underwrite (§15) ------
  useEffect(() => {
    const store = useScenario.getState();
    store.reset();
    store.setResult(null);
    store.setBaseResult(null);
    store.setError(null);
    setFarm(null);
    setShowcase(null);
    setNotFound(false);
    setBootError(null);
    setEngineWaking(false);
    setBooting(true);
    setTab("overview");

    let cancelled = false;
    (async () => {
      const sc = await fetchShowcase(farmId);
      if (cancelled) return;
      if (sc) {
        setShowcase(sc);
        setFarm(sc.farm);
        useScenario.getState().setBaseResult(sc.underwrite);
        useScenario.getState().setResult(sc.underwrite);
        setBooting(false);
      }

      // always try the live registry record; fall back to the showcase shape
      try {
        const f = await fetchFarm(farmId);
        if (!cancelled) setFarm(f);
      } catch (err) {
        if (cancelled) return;
        if (!sc) {
          if (err instanceof ApiError && err.status === 404) {
            setNotFound(true);
          } else {
            setBootError(err instanceof Error ? err.message : String(err));
          }
          setBooting(false);
          return;
        }
        // API down/cold but showcase carries the farm shape — keep going.
      }

      if (!sc) {
        try {
          const r = await underwrite(farmId);
          if (cancelled) return;
          useScenario.getState().setBaseResult(r);
          useScenario.getState().setResult(r);
        } catch {
          if (!cancelled) setEngineWaking(true);
        }
      }
      if (!cancelled) setBooting(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [farmId]);

  // ---- shocks → debounce 250ms → underwrite (presets short-circuit) -------
  useEffect(() => {
    if (baseResult === null) return;
    const store = useScenario.getState();

    if (isDefaultShocks(shocks)) {
      seqRef.current += 1;
      store.setResult(baseResult);
      store.setLoading(false);
      setEngineWaking(false);
      return;
    }

    const presetResult =
      activePreset !== null ? showcase?.presets?.[activePreset] : undefined;
    if (presetResult) {
      // instant chip switching from the precomputed showcase results (§15)
      seqRef.current += 1;
      store.setResult(presetResult);
      store.setLoading(false);
      setEngineWaking(false);
      return;
    }

    const seq = ++seqRef.current;
    store.setLoading(true);
    const t = setTimeout(async () => {
      try {
        const r = await underwrite(farmId, {}, shocks);
        if (seqRef.current !== seq) return;
        store.setResult(r);
        setEngineWaking(false);
      } catch {
        // API down + custom slider → keep last result, flag the waking engine
        if (seqRef.current === seq) setEngineWaking(true);
      } finally {
        if (seqRef.current === seq) store.setLoading(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [shocks, activePreset, baseResult, showcase, farmId]);

  const retryBase = useCallback(() => {
    setEngineWaking(false);
    setBooting(true);
    underwrite(farmId)
      .then((r) => {
        useScenario.getState().setBaseResult(r);
        useScenario.getState().setResult(r);
      })
      .catch(() => setEngineWaking(true))
      .finally(() => setBooting(false));
  }, [farmId]);

  // ---- terminal states -----------------------------------------------------
  if (notFound) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <ErrorState
          className="w-full max-w-md"
          title="Farm not found"
          detail={`No registry record or showcase dossier for “${farmId}”.`}
          hint={`GET /api/farm/${farmId} → 404`}
          action={
            <Link
              href="/"
              className="inline-flex h-8 items-center rounded-sm border border-line bg-bg2 px-4 text-2xs font-medium uppercase tracking-wider text-mid transition-colors hover:text-hi"
            >
              ← Back to the fleet map
            </Link>
          }
        />
      </div>
    );
  }

  if (bootError && farm === null) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <ErrorState
          className="w-full max-w-md"
          title="Dossier unavailable"
          detail="The live API did not answer and this farm has no precomputed showcase dossier."
          hint={bootError}
          action={
            <Link
              href="/"
              className="inline-flex h-8 items-center rounded-sm border border-line bg-bg2 px-4 text-2xs font-medium uppercase tracking-wider text-mid transition-colors hover:text-hi"
            >
              ← Back to the fleet map
            </Link>
          }
        />
      </div>
    );
  }

  const verdict = deriveVerdict(showcase?.memo_markdown);

  return (
    <div className="flex h-full min-h-0">
      {/* ---- left 340px identity column ---- */}
      <aside className="flex w-[340px] shrink-0 flex-col overflow-y-auto border-r border-line bg-bg1 p-4">
        {farm === null ? (
          <div className="space-y-3" aria-busy="true">
            <div className="h-6 w-3/4 animate-pulse rounded bg-bg2" />
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex justify-between gap-3">
                <div className="h-4 w-24 animate-pulse rounded bg-bg2" />
                <div className="h-4 w-20 animate-pulse rounded bg-bg2" />
              </div>
            ))}
          </div>
        ) : (
          <IdentityCard farm={farm} />
        )}

        <div className="mt-6 flex flex-col gap-3 border-t border-line pt-4">
          <VerdictChip verdict={verdict} />
          {/* the page's ONE gold CTA (§3.1) */}
          <button
            type="button"
            disabled={result === null}
            onClick={() => setTab("memo")}
            className={clsx(
              "h-9 rounded-sm px-5 text-base font-medium transition-colors",
              result === null
                ? "cursor-not-allowed border border-line bg-bg2 text-low"
                : "bg-gold-500 text-bg0 hover:bg-gold-400",
            )}
          >
            Generate IC Memo
          </button>
          <p className="text-2xs text-low">
            Three critics argue over frozen evidence; a narrator writes. Every number carries a
            citation seal.
          </p>
        </div>
      </aside>

      {/* ---- right: tabs ---- */}
      {booting && result === null ? (
        <DossierSkeleton />
      ) : result === null ? (
        <div className="flex min-w-0 flex-1 items-start justify-center p-6">
          <ErrorState
            className="w-full max-w-md"
            title="Live engine waking…"
            detail="This farm is not precomputed, so the dossier needs POST /api/underwrite. The free-tier API host may take a moment to spin up."
            action={
              <button
                type="button"
                onClick={retryBase}
                className="h-8 rounded-sm border border-line bg-bg2 px-4 text-2xs font-medium uppercase tracking-wider text-mid transition-colors hover:text-hi"
              >
                Retry
              </button>
            }
          />
        </div>
      ) : (
        <Tabs.Root
          value={tab}
          onValueChange={(v) => setTab(v as TabKey)}
          className="flex min-w-0 flex-1 flex-col"
        >
          <Tabs.List
            aria-label="Dossier sections"
            className="flex shrink-0 gap-1 border-b border-line px-6 pt-3"
          >
            {TABS.map((t) => (
              <Tabs.Trigger
                key={t.key}
                value={t.key}
                className={clsx(
                  "-mb-px h-9 border-b-2 border-transparent px-3 text-base text-low transition-colors",
                  "hover:text-mid focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-dim",
                  "data-[state=active]:border-hi data-[state=active]:text-hi",
                )}
              >
                {t.label}
              </Tabs.Trigger>
            ))}
          </Tabs.List>

          {engineWaking ? (
            <div className="shrink-0 border-b border-line bg-bg1 px-6 py-1.5 text-2xs text-warn" role="status">
              live engine waking… showing the last computed result
            </div>
          ) : null}

          <div className="min-h-0 flex-1 overflow-y-auto p-6">
            <Tabs.Content value="overview">
              <OverviewTab result={result} base={baseResult} loading={loading} />
            </Tabs.Content>
            <Tabs.Content value="energy">
              <EnergyTab energy={result.energy} resource={farm?.resource ?? null} />
            </Tabs.Content>
            <Tabs.Content value="revenue">
              <RevenueTab farmId={farmId} result={result} />
            </Tabs.Content>
            <Tabs.Content value="debt">
              <DebtTab result={result} />
            </Tabs.Content>
            <Tabs.Content value="scenarios">
              <ScenariosTab
                hasShowcasePresets={Boolean(showcase && Object.keys(showcase.presets).length > 0)}
                engineWaking={engineWaking}
              />
            </Tabs.Content>
            <Tabs.Content value="memo">
              <MemoTab
                farmId={farmId}
                result={result}
                showcase={
                  showcase
                    ? {
                        memo_markdown: showcase.memo_markdown,
                        claims: showcase.claims,
                        rebuttals: showcase.rebuttals,
                        validation: showcase.validation,
                      }
                    : null
                }
                ctaGold={false}
              />
            </Tabs.Content>
          </div>
        </Tabs.Root>
      )}
    </div>
  );
}
