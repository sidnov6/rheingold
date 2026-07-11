"use client";

/**
 * /backtest (§11, §12) — the falsifiable claim. Model break-even bid band vs
 * actual BNetzA onshore clearing prices 2017–2025, MAE stated, caveats mandatory.
 */

import { useEffect, useState } from "react";
import { AuctionBacktestChart } from "@/components/AuctionBacktestChart";
import { ErrorState } from "@/components/ErrorState";
import { fetchBacktest, ApiError } from "@/lib/api";
import type { BacktestResult, BacktestRound } from "@/lib/types";
import { fmt2, fmtCtKwh, fmtInt, fmtPct } from "@/lib/format";

// ---------------------------------------------------------------- content

const METHOD_STEPS: { n: string; title: string; body: string }[] = [
  {
    n: "1",
    title: "Sample the round's pipeline",
    body: "For each auction year Y, sample N=40 farms from MaStR commissioned in Y..Y+2 — a proxy for that round's project pipeline — stratified by Bundesland wind class (north / center / south).",
  },
  {
    n: "2",
    title: "Vintage the assumptions",
    body: "Assumptions per year come from cost_vintages.csv (capex, opex, interest-rate vintage). Wind resource is estimated via Path B for every farm — a uniform method across years, because comparability beats precision here.",
  },
  {
    n: "3",
    title: "Solve the break-even bid",
    body: "For each sampled farm, the engine solves the break-even anzulegender Wert (§8.6) such that equity IRR equals the 7 % target — producing a distribution of model bids per round.",
  },
  {
    n: "4",
    title: "Compare against reality",
    body: "The model's median and P25–P75 band are compared with the actual average award price (Ø-Zuschlagswert) per round. Reported: MAE in ct/kWh and the directional hit-rate — did the model move the right way round-over-round.",
  },
];

const CAVEATS: { title: string; body: string }[] = [
  {
    title: "Winner's curse",
    body: "Auction winners are systematically the most optimistic bidders. Observed awards therefore sit below an unbiased break-even estimate; the model prices a median project, not the most aggressive bid in the room.",
  },
  {
    title: "Undersubscribed rounds 2019–2022",
    body: "Many rounds in 2019–2022 were undersubscribed. With little competitive pressure, awards drifted toward the Höchstwert cap — prices in those rounds reflect the cap more than project economics.",
  },
  {
    title: "Höchstwert binding post-2022",
    body: "After the 2022–2023 cost inflation, the Höchstwert became a binding constraint: awards cluster at the cap, so the observed series carries regulatory truncation the model does not.",
  },
  {
    title: "Site-selection bias",
    body: "Farms sampled from the registry are commissioned projects, not the bid pipeline. Registry ≠ bids: projects that bid and lost, or won and were never built, are invisible to this sampling.",
  },
  {
    title: "Path B resource error",
    body: "The backtest uses the coarser Path B wind-resource method uniformly for comparability. Its per-site capacity-factor error propagates directly into each farm's break-even bid.",
  },
];

// ---------------------------------------------------------------- pieces

function StatCard({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="rounded border border-line bg-bg1 px-4 py-3">
      <div className="text-2xs uppercase tracking-wider text-low">{label}</div>
      <div className="num mt-1 text-xl text-gold-500">{value}</div>
      {note && <div className="mt-1 text-2xs text-mid">{note}</div>}
    </div>
  );
}

function roundError(r: BacktestRound): number | null {
  if (r.avg_award_ct_kwh === null) return null;
  return r.model_median_ct_kwh - r.avg_award_ct_kwh;
}

function RoundsTable({ rounds }: { rounds: BacktestRound[] }) {
  return (
    <div className="overflow-x-auto rounded border border-line">
      <table className="w-full min-w-[720px] border-collapse text-data">
        <thead>
          <tr className="h-8 bg-bg2 text-left text-2xs uppercase tracking-wider text-low">
            <th className="px-3 font-medium">Round</th>
            <th className="px-3 text-right font-medium">Farms sampled</th>
            <th className="px-3 text-right font-medium">Actual Ø award</th>
            <th className="px-3 text-right font-medium">Höchstwert</th>
            <th className="px-3 text-right font-medium">Model median</th>
            <th className="px-3 text-right font-medium">Model P25–P75</th>
            <th className="px-3 text-right font-medium">Error</th>
          </tr>
        </thead>
        <tbody>
          {rounds.map((r) => {
            const err = roundError(r);
            return (
              <tr
                key={r.round_date}
                className="h-8 border-t border-line transition-colors hover:bg-bg2"
              >
                <td className="num px-3 text-mid">{r.round_date}</td>
                <td className="num px-3 text-right text-mid">{fmtInt(r.n_farms)}</td>
                <td className="num px-3 text-right text-hi">
                  {r.avg_award_ct_kwh === null ? "—" : fmt2(r.avg_award_ct_kwh)}
                </td>
                <td className="num px-3 text-right text-low">
                  {r.max_price_ct_kwh === null ? "—" : fmt2(r.max_price_ct_kwh)}
                </td>
                <td className="num px-3 text-right text-gold-500">
                  {fmt2(r.model_median_ct_kwh)}
                </td>
                <td className="num px-3 text-right text-mid">
                  {fmt2(r.model_p25_ct_kwh)}–{fmt2(r.model_p75_ct_kwh)}
                </td>
                <td
                  className={`num px-3 text-right ${
                    err === null
                      ? "text-low"
                      : Math.abs(err) <= 0.5
                        ? "text-pos"
                        : "text-neg"
                  }`}
                >
                  {err === null
                    ? "—"
                    : `${err > 0 ? "+" : ""}${fmt2(err)}`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="border-t border-line bg-bg1 px-3 py-1.5 text-2xs text-low">
        All prices in ct/kWh. Error = model median − actual Ø-Zuschlagswert.
      </div>
    </div>
  );
}

function MethodSection() {
  return (
    <section aria-labelledby="method-h">
      <h2 id="method-h" className="text-lg font-medium text-hi">
        Method
      </h2>
      <p className="mt-2 max-w-3xl text-base text-mid">
        Does the engine&apos;s break-even bid reproduce observed BNetzA onshore
        clearing prices 2017–2025? Four steps, run identically for every round:
      </p>
      <ol className="mt-4 grid gap-3 md:grid-cols-2">
        {METHOD_STEPS.map((s) => (
          <li key={s.n} className="rounded border border-line bg-bg1 px-4 py-3">
            <div className="flex items-baseline gap-2">
              <span className="num text-data text-low">{s.n}</span>
              <h3 className="text-base font-medium text-hi">{s.title}</h3>
            </div>
            <p className="mt-1.5 text-data leading-relaxed text-mid">{s.body}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function CaveatsSection() {
  return (
    <section aria-labelledby="caveats-h">
      <h2 id="caveats-h" className="text-lg font-medium text-hi">
        Caveats
      </h2>
      <p className="mt-2 max-w-3xl text-base text-mid">
        Five reasons to distrust the chart above — stated up front, because the
        honesty is the feature.
      </p>
      <div className="mt-4 space-y-2">
        {CAVEATS.map((c) => (
          <div key={c.title} className="rounded border border-line bg-bg1 px-4 py-3">
            <h3 className="text-base font-medium text-hi">{c.title}</h3>
            <p className="mt-1 max-w-3xl text-data leading-relaxed text-mid">
              {c.body}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- page

export default function BacktestPage() {
  const [data, setData] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchBacktest()
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(
          e instanceof ApiError && e.status === 503
            ? "backtest artifact not built"
            : e instanceof Error
              ? e.message
              : "backtest unavailable",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <header>
        <p className="text-2xs uppercase tracking-widest text-low">
          Auction backtest · BNetzA Wind an Land
        </p>
        <h1 className="mt-1 font-display text-xl font-medium text-hi">
          Model bid band vs. observed award prices, 2017–2025
        </h1>
        <p className="mt-2 max-w-3xl text-base text-mid">
          For every onshore auction round, the engine solves each sampled
          farm&apos;s break-even bid at a 7 % equity hurdle — then the model
          band is laid over what BNetzA actually cleared. The claim is
          falsifiable by construction.
        </p>
      </header>

      <div className="mt-8 space-y-10">
        {loading && (
          <div className="space-y-4" aria-label="Loading backtest">
            <div className="h-[380px] animate-pulse rounded border border-line bg-bg2" />
            <div className="grid grid-cols-3 gap-3">
              <div className="h-20 animate-pulse rounded bg-bg2" />
              <div className="h-20 animate-pulse rounded bg-bg2" />
              <div className="h-20 animate-pulse rounded bg-bg2" />
            </div>
          </div>
        )}

        {!loading && error && (
          <ErrorState
            title="Backtest results not available"
            detail="The backtest artifact has not been generated yet, or the API is asleep. The full run samples 40 farms per auction round and solves each break-even bid — it is produced offline, not on request."
            hint={`run: make backtest — then GET /api/backtest serves the result (${error})`}
          />
        )}

        {!loading && data && (
          <>
            <AuctionBacktestChart rounds={data.rounds} />

            <section aria-label="Headline statistics" className="grid gap-3 sm:grid-cols-3">
              <StatCard
                label="MAE"
                value={fmtCtKwh(data.mae_ct_kwh)}
                note="mean absolute error, model median vs actual Ø award"
              />
              <StatCard
                label="Directional hit-rate"
                value={fmtPct(data.directional_hit_rate, 0)}
                note="rounds where the model moved the same way as awards"
              />
              <StatCard
                label="Rounds compared"
                value={fmtInt(data.rounds.length)}
                note={`generated ${data.generated_at.slice(0, 10)}`}
              />
            </section>

            <section aria-labelledby="rounds-h">
              <h2 id="rounds-h" className="text-lg font-medium text-hi">
                Per-round results
              </h2>
              <div className="mt-3">
                <RoundsTable rounds={data.rounds} />
              </div>
            </section>
          </>
        )}

        {/* Method + caveats always render — the page is never blank (§12). */}
        <MethodSection />
        <CaveatsSection />

        {data?.method_note && (
          <p className="border-t border-line pt-4 text-2xs text-low">
            {data.method_note}
          </p>
        )}
      </div>
    </div>
  );
}
