"use client";

/**
 * AuctionBacktestChart (§11 /backtest, §12).
 * x = auction rounds (time). Actual avg award price: --text-hi line.
 * Model break-even band P25–P75: --gold-dim area with --gold-500 median line.
 * Höchstwert (price cap): dashed --text-low line.
 * Exactly 4 visual series max — this uses 4 (§3 chart rule).
 */

import { useMemo } from "react";
import { ParentSize } from "@visx/responsive";
import { Group } from "@visx/group";
import { scaleLinear, scalePoint } from "@visx/scale";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridRows } from "@visx/grid";
import { LinePath, Area } from "@visx/shape";
import { curveMonotoneX } from "@visx/curve";
import type { BacktestRound } from "@/lib/types";
import { fmt2 } from "@/lib/format";

const MARGIN = { top: 16, right: 24, bottom: 44, left: 56 };

function roundLabel(iso: string): string {
  // "2019-05-01" → "05/19" — compact mono tick
  const [y, m] = iso.split("-");
  return `${m}/${y.slice(2)}`;
}

function Chart({
  rounds,
  width,
  height,
}: {
  rounds: BacktestRound[];
  width: number;
  height: number;
}) {
  const innerW = Math.max(0, width - MARGIN.left - MARGIN.right);
  const innerH = Math.max(0, height - MARGIN.top - MARGIN.bottom);

  const xScale = useMemo(
    () =>
      scalePoint<string>({
        domain: rounds.map((r) => r.round_date),
        range: [0, innerW],
        padding: 0.5,
      }),
    [rounds, innerW],
  );

  const yScale = useMemo(() => {
    const vals = rounds.flatMap((r) =>
      [
        r.avg_award_ct_kwh,
        r.max_price_ct_kwh,
        r.model_p25_ct_kwh,
        r.model_p75_ct_kwh,
        r.model_median_ct_kwh,
      ].filter((v): v is number => v !== null),
    );
    const lo = Math.min(...vals);
    const hi = Math.max(...vals);
    const pad = (hi - lo) * 0.12 || 1;
    return scaleLinear<number>({
      domain: [Math.max(0, lo - pad), hi + pad],
      range: [innerH, 0],
      nice: true,
    });
  }, [rounds, innerH]);

  const x = (r: BacktestRound) => xScale(r.round_date) ?? 0;
  const actualRounds = rounds.filter((r) => r.avg_award_ct_kwh !== null);
  const capRounds = rounds.filter((r) => r.max_price_ct_kwh !== null);

  if (width < 10) return null;

  return (
    <svg width={width} height={height} role="img" aria-label="Model break-even bid band versus actual BNetzA award prices per auction round">
      <Group left={MARGIN.left} top={MARGIN.top}>
        <GridRows
          scale={yScale}
          width={innerW}
          stroke="var(--border)"
          strokeOpacity={0.6}
          numTicks={5}
        />

        {/* Model band P25–P75 — gold-dim area */}
        <Area<BacktestRound>
          data={rounds}
          x={x}
          y0={(r) => yScale(r.model_p25_ct_kwh)}
          y1={(r) => yScale(r.model_p75_ct_kwh)}
          curve={curveMonotoneX}
          fill="var(--gold-dim)"
        />

        {/* Model median — gold-500 */}
        <LinePath<BacktestRound>
          data={rounds}
          x={x}
          y={(r) => yScale(r.model_median_ct_kwh)}
          curve={curveMonotoneX}
          stroke="var(--gold-500)"
          strokeWidth={1.75}
        />

        {/* Höchstwert cap — dashed text-low */}
        <LinePath<BacktestRound>
          data={capRounds}
          x={x}
          y={(r) => yScale(r.max_price_ct_kwh as number)}
          stroke="var(--text-low)"
          strokeWidth={1}
          strokeDasharray="5,4"
        />

        {/* Actual avg award — text-hi line + points */}
        <LinePath<BacktestRound>
          data={actualRounds}
          x={x}
          y={(r) => yScale(r.avg_award_ct_kwh as number)}
          curve={curveMonotoneX}
          stroke="var(--text-hi)"
          strokeWidth={1.5}
        />
        {actualRounds.map((r) => (
          <circle
            key={r.round_date}
            cx={x(r)}
            cy={yScale(r.avg_award_ct_kwh as number)}
            r={2.5}
            fill="var(--text-hi)"
          />
        ))}

        <AxisLeft
          scale={yScale}
          numTicks={5}
          stroke="var(--border)"
          tickStroke="var(--border)"
          tickFormat={(v) => fmt2(Number(v))}
          tickLabelProps={() => ({
            fill: "var(--text-low)",
            fontSize: 11,
            fontFamily: "var(--font-plex-mono), monospace",
            textAnchor: "end",
            dx: -6,
            dy: 3,
          })}
          label="ct/kWh"
          labelProps={{
            fill: "var(--text-low)",
            fontSize: 11,
            fontFamily: "var(--font-plex-mono), monospace",
            textAnchor: "middle",
          }}
        />
        <AxisBottom
          top={innerH}
          scale={xScale}
          stroke="var(--border)"
          tickStroke="var(--border)"
          tickFormat={(d) => roundLabel(String(d))}
          tickLabelProps={() => ({
            fill: "var(--text-low)",
            fontSize: 10,
            fontFamily: "var(--font-plex-mono), monospace",
            textAnchor: "middle",
            dy: 4,
            angle: rounds.length > 14 ? -40 : 0,
          })}
        />
      </Group>
    </svg>
  );
}

export function AuctionBacktestChart({ rounds }: { rounds: BacktestRound[] }) {
  return (
    <figure className="rounded border border-line bg-bg1">
      <div className="h-[380px] w-full">
        <ParentSize>
          {({ width, height }) => (
            <Chart rounds={rounds} width={width} height={height} />
          )}
        </ParentSize>
      </div>
      <figcaption className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line px-4 py-2 text-2xs text-mid">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-0.5 w-4 bg-hi" />
          Actual Ø-Zuschlagswert (BNetzA)
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-0.5 w-4 bg-gold-500" />
          Model break-even median
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-2.5 w-4 bg-gold-dim" />
          Model P25–P75 band
        </span>
        <span className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-0 w-4 border-t border-dashed border-low"
          />
          Höchstwert (cap)
        </span>
      </figcaption>
    </figure>
  );
}
