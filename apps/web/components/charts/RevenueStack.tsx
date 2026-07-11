"use client";

import { useMemo, useState } from "react";
import { ParentSize } from "@visx/responsive";
import { Group } from "@visx/group";
import { scaleLinear } from "@visx/scale";
import { Area, LinePath, Line } from "@visx/shape";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { curveMonotoneX } from "@visx/curve";
import { localPoint } from "@visx/event";
import type { AnnualSeries } from "@/lib/types";
import { fmtEur, fmtYear } from "@/lib/format";
import { EmptyState } from "@/components/EmptyState";
import { C, axisLineProps, numTickProps } from "./theme";
import { ChartTooltip, TipRow, type TipState } from "./ChartTooltip";

/**
 * RevenueStack (§11 Revenue): stacked area by year — market revenue (rhine)
 * below, EEG market premium stacked on top (gold-dim fill, gold line).
 */

export interface RevenueStackProps {
  annual: AnnualSeries;
}

const MARGIN = { top: 12, right: 12, bottom: 30, left: 56 };

interface Datum {
  year: number;
  market: number;
  premium: number;
}

function Inner({ data, width, height }: { data: Datum[]; width: number; height: number }) {
  const [tip, setTip] = useState<TipState | null>(null);
  const xMax = width - MARGIN.left - MARGIN.right;
  const yMax = height - MARGIN.top - MARGIN.bottom;

  const xScale = useMemo(
    () =>
      scaleLinear<number>({
        domain: [data[0].year, data[data.length - 1].year],
        range: [0, xMax],
      }),
    [data, xMax],
  );
  const yScale = useMemo(
    () =>
      scaleLinear<number>({
        domain: [0, Math.max(...data.map((d) => d.market + d.premium)) * 1.08],
        range: [yMax, 0],
        nice: true,
      }),
    [data, yMax],
  );

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const pt = localPoint(e);
    if (!pt) return;
    const x0 = xScale.invert(pt.x - MARGIN.left);
    let best = data[0];
    for (const d of data) if (Math.abs(d.year - x0) < Math.abs(best.year - x0)) best = d;
    setTip({
      x: pt.x,
      y: pt.y,
      content: (
        <>
          <div className="mb-0.5 text-hi">{fmtYear(best.year)}</div>
          <TipRow label="Market" value={fmtEur(best.market)} accent={C.rhine} />
          <TipRow label="EEG premium" value={fmtEur(best.premium)} accent={C.gold} />
          <TipRow label="Total" value={fmtEur(best.market + best.premium)} />
        </>
      ),
    });
  };

  return (
    <>
      <svg
        width={width}
        height={height}
        role="img"
        aria-label="Revenue stack by year: market revenue plus EEG market premium"
        onMouseMove={onMove}
        onMouseLeave={() => setTip(null)}
      >
        <Group left={MARGIN.left} top={MARGIN.top}>
          {/* market leg: rhine */}
          <Area<Datum>
            data={data}
            x={(d) => xScale(d.year)}
            y0={() => yScale(0)}
            y1={(d) => yScale(d.market)}
            curve={curveMonotoneX}
            fill={C.rhine}
            fillOpacity={0.35}
          />
          <LinePath<Datum>
            data={data}
            x={(d) => xScale(d.year)}
            y={(d) => yScale(d.market)}
            curve={curveMonotoneX}
            stroke={C.rhine}
            strokeWidth={1.5}
          />
          {/* premium leg stacked on top: gold-dim fill, gold line */}
          <Area<Datum>
            data={data}
            x={(d) => xScale(d.year)}
            y0={(d) => yScale(d.market)}
            y1={(d) => yScale(d.market + d.premium)}
            curve={curveMonotoneX}
            fill={C.goldDim}
          />
          <LinePath<Datum>
            data={data}
            x={(d) => xScale(d.year)}
            y={(d) => yScale(d.market + d.premium)}
            curve={curveMonotoneX}
            stroke={C.gold}
            strokeWidth={1.5}
          />
          {tip ? (
            <Line
              from={{ x: tip.x - MARGIN.left, y: 0 }}
              to={{ x: tip.x - MARGIN.left, y: yMax }}
              stroke={C.textLow}
              strokeWidth={1}
              strokeDasharray="2,3"
              pointerEvents="none"
            />
          ) : null}
          <AxisLeft
            scale={yScale}
            numTicks={5}
            stroke={axisLineProps.stroke}
            tickStroke={axisLineProps.stroke}
            tickFormat={(v) => fmtEur(Number(v))}
            tickLabelProps={() => ({ ...numTickProps, textAnchor: "end" as const, dx: -4, dy: 3 })}
          />
          <AxisBottom
            top={yMax}
            scale={xScale}
            numTicks={Math.min(data.length, 8)}
            stroke={axisLineProps.stroke}
            tickStroke={axisLineProps.stroke}
            tickFormat={(v) => fmtYear(Number(v))}
            tickLabelProps={() => ({ ...numTickProps, textAnchor: "middle" as const, dy: 4 })}
          />
        </Group>
      </svg>
      <ChartTooltip tip={tip} width={width} />
    </>
  );
}

export function RevenueStack({ annual }: RevenueStackProps) {
  const data: Datum[] = (annual?.year ?? []).map((year, i) => ({
    year,
    market: annual.revenue_market[i] ?? 0,
    premium: annual.revenue_premium[i] ?? 0,
  }));
  if (data.length < 2) {
    return <EmptyState title="No revenue series" detail="Run an underwrite to price the revenue stack." />;
  }
  return (
    <div className="relative h-full min-h-[220px] w-full">
      <ParentSize>
        {({ width, height }) =>
          width > 0 && height > 0 ? <Inner data={data} width={width} height={height} /> : null
        }
      </ParentSize>
    </div>
  );
}

export default RevenueStack;
