"use client";

import { useMemo, useState } from "react";
import { ParentSize } from "@visx/responsive";
import { Group } from "@visx/group";
import { scaleLinear } from "@visx/scale";
import { Bar, Line } from "@visx/shape";
import { AxisBottom } from "@visx/axis";
import type { TornadoItem } from "@/lib/types";
import { fmtPct } from "@/lib/format";
import { EmptyState } from "@/components/EmptyState";
import { C, axisLineProps, numTickProps } from "./theme";
import { ChartTooltip, TipRow, type TipState } from "./ChartTooltip";

/**
 * TornadoChart (§3.4): horizontal diverging bars around the base equity IRR,
 * sorted by span. Downside leg rhine, upside leg gold; low/high input values
 * annotated at the bar ends.
 */

export interface TornadoChartProps {
  items: TornadoItem[];
  baseIrr: number | null;
}

const ROW_H = 34;
const MARGIN = { top: 8, right: 76, bottom: 30, left: 148 };

interface Row extends TornadoItem {
  irr_low: number;
  irr_high: number;
  span: number;
}

function Inner({ rows, baseIrr, width, height }: { rows: Row[]; baseIrr: number; width: number; height: number }) {
  const [tip, setTip] = useState<TipState | null>(null);
  const xMax = width - MARGIN.left - MARGIN.right;
  const yMax = height - MARGIN.top - MARGIN.bottom;

  const xScale = useMemo(() => {
    const vals = rows.flatMap((r) => [r.irr_low, r.irr_high]).concat(baseIrr);
    const lo = Math.min(...vals);
    const hi = Math.max(...vals);
    const pad = Math.max((hi - lo) * 0.15, 0.005);
    return scaleLinear<number>({ domain: [lo - pad, hi + pad], range: [0, xMax] });
  }, [rows, baseIrr, xMax]);

  const baseX = xScale(baseIrr);
  const barH = Math.min(16, (yMax / rows.length) * 0.55);

  return (
    <>
      <svg width={width} height={height} role="img" aria-label="IRR sensitivity tornado">
        <Group left={MARGIN.left} top={MARGIN.top}>
          {rows.map((r, i) => {
            const cy = (i + 0.5) * (yMax / rows.length);
            const y = cy - barH / 2;
            const xLow = xScale(r.irr_low);
            const xHigh = xScale(r.irr_high);
            const onMove = (e: React.MouseEvent<SVGElement>) => {
              const rect = (e.currentTarget as SVGElement).ownerSVGElement?.getBoundingClientRect();
              if (!rect) return;
              setTip({
                x: e.clientX - rect.left,
                y: e.clientY - rect.top,
                content: (
                  <>
                    <div className="mb-0.5 text-hi">{r.label}</div>
                    <TipRow label={r.low_input} value={fmtPct(r.irr_low)} accent={C.rhine} />
                    <TipRow label={r.high_input} value={fmtPct(r.irr_high)} accent={C.gold} />
                  </>
                ),
              });
            };
            return (
              <Group key={r.variable} onMouseLeave={() => setTip(null)}>
                {/* downside leg (base → low): rhine */}
                <Bar
                  x={Math.min(baseX, xLow)}
                  y={y}
                  width={Math.max(1, Math.abs(baseX - xLow))}
                  height={barH}
                  fill={C.rhine}
                  fillOpacity={0.8}
                  onMouseMove={onMove}
                />
                {/* upside leg (base → high): gold */}
                <Bar
                  x={Math.min(baseX, xHigh)}
                  y={y}
                  width={Math.max(1, Math.abs(xHigh - baseX))}
                  height={barH}
                  fill={C.gold}
                  fillOpacity={0.85}
                  onMouseMove={onMove}
                />
                {/* variable label, left */}
                <text
                  x={-10}
                  y={cy}
                  dy={3}
                  textAnchor="end"
                  fontSize={11}
                  fill={C.textMid}
                  fontFamily="var(--font-plex-sans), system-ui, sans-serif"
                >
                  {r.label}
                </text>
                {/* low/high input annotations at bar ends */}
                <text
                  x={Math.min(xLow, xHigh) - 5}
                  y={cy}
                  dy={3}
                  textAnchor="end"
                  fontSize={9}
                  fill={C.textLow}
                  fontFamily={numTickProps.fontFamily}
                >
                  {r.irr_low <= r.irr_high ? r.low_input : r.high_input}
                </text>
                <text
                  x={Math.max(xLow, xHigh) + 5}
                  y={cy}
                  dy={3}
                  textAnchor="start"
                  fontSize={9}
                  fill={C.textLow}
                  fontFamily={numTickProps.fontFamily}
                >
                  {r.irr_low <= r.irr_high ? r.high_input : r.low_input}
                </text>
              </Group>
            );
          })}
          {/* base IRR axis line */}
          <Line
            from={{ x: baseX, y: 0 }}
            to={{ x: baseX, y: yMax }}
            stroke={C.textMid}
            strokeWidth={1}
          />
          <text
            x={baseX}
            y={-2}
            textAnchor="middle"
            fontSize={9}
            fill={C.textMid}
            fontFamily={numTickProps.fontFamily}
          >
            base {fmtPct(baseIrr)}
          </text>
          <AxisBottom
            top={yMax}
            scale={xScale}
            numTicks={5}
            stroke={axisLineProps.stroke}
            tickStroke={axisLineProps.stroke}
            tickFormat={(v) => fmtPct(Number(v))}
            tickLabelProps={() => ({ ...numTickProps, textAnchor: "middle" as const, dy: 4 })}
          />
        </Group>
      </svg>
      <ChartTooltip tip={tip} width={width} />
    </>
  );
}

export function TornadoChart({ items, baseIrr }: TornadoChartProps) {
  const rows: Row[] = (items ?? [])
    .filter((it): it is TornadoItem & { irr_low: number; irr_high: number } =>
      it.irr_low !== null && it.irr_high !== null,
    )
    .map((it) => ({ ...it, span: Math.abs(it.irr_high - it.irr_low) }))
    .sort((a, b) => b.span - a.span);

  if (baseIrr === null || rows.length === 0) {
    return (
      <EmptyState
        title="No sensitivity data"
        detail={baseIrr === null ? "Base equity IRR undefined — deal does not return capital." : "No tornado items."}
      />
    );
  }
  const height = MARGIN.top + MARGIN.bottom + rows.length * ROW_H;
  return (
    <div className="relative w-full" style={{ height }}>
      <ParentSize>
        {({ width }) =>
          width > 0 ? <Inner rows={rows} baseIrr={baseIrr} width={width} height={height} /> : null
        }
      </ParentSize>
    </div>
  );
}

export default TornadoChart;
