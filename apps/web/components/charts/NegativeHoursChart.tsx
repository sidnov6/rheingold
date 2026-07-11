"use client";

import { useMemo, useState } from "react";
import { ParentSize } from "@visx/responsive";
import { Group } from "@visx/group";
import { scaleBand, scaleLinear } from "@visx/scale";
import { Bar } from "@visx/shape";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { fmtInt, fmtYear } from "@/lib/format";
import { EmptyState } from "@/components/EmptyState";
import { C, axisLineProps, numTickProps } from "./theme";
import { ChartTooltip, TipRow, type TipState } from "./ChartTooltip";

/**
 * NegativeHoursChart (§11 Revenue): hours of negative day-ahead prices per
 * year — §51 EEG risk. Warn color: this is a hazard series, not a data hero.
 */

export interface NegativeHoursChartProps {
  byYear: { year: number; hours: number }[];
}

const MARGIN = { top: 12, right: 12, bottom: 30, left: 46 };

function Inner({
  byYear,
  width,
  height,
}: NegativeHoursChartProps & { width: number; height: number }) {
  const [tip, setTip] = useState<TipState | null>(null);
  const xMax = width - MARGIN.left - MARGIN.right;
  const yMax = height - MARGIN.top - MARGIN.bottom;

  const xScale = useMemo(
    () =>
      scaleBand<number>({
        domain: byYear.map((d) => d.year),
        range: [0, xMax],
        padding: 0.35,
      }),
    [byYear, xMax],
  );
  const yScale = useMemo(
    () =>
      scaleLinear<number>({
        domain: [0, Math.max(...byYear.map((d) => d.hours)) * 1.12 || 1],
        range: [yMax, 0],
        nice: true,
      }),
    [byYear, yMax],
  );
  const everyN = Math.max(1, Math.ceil(byYear.length / Math.floor(xMax / 44)));

  return (
    <>
      <svg width={width} height={height} role="img" aria-label="Negative price hours by year">
        <Group left={MARGIN.left} top={MARGIN.top}>
          {byYear.map((d) => {
            const y = yScale(d.hours);
            return (
              <Bar
                key={d.year}
                x={xScale(d.year) ?? 0}
                y={y}
                width={xScale.bandwidth()}
                height={Math.max(1, yMax - y)}
                fill={C.warn}
                fillOpacity={0.75}
                onMouseMove={(e) => {
                  const r = (e.currentTarget as SVGElement).ownerSVGElement?.getBoundingClientRect();
                  if (!r) return;
                  setTip({
                    x: e.clientX - r.left,
                    y: e.clientY - r.top,
                    content: (
                      <TipRow label={fmtYear(d.year)} value={`${fmtInt(d.hours)} h`} accent={C.warn} />
                    ),
                  });
                }}
                onMouseLeave={() => setTip(null)}
              />
            );
          })}
          <AxisLeft
            scale={yScale}
            numTicks={4}
            stroke={axisLineProps.stroke}
            tickStroke={axisLineProps.stroke}
            tickFormat={(v) => fmtInt(Number(v))}
            tickLabelProps={() => ({ ...numTickProps, textAnchor: "end" as const, dx: -4, dy: 3 })}
          />
          <AxisBottom
            top={yMax}
            scale={xScale}
            stroke={axisLineProps.stroke}
            tickStroke={axisLineProps.stroke}
            tickValues={byYear.map((d) => d.year).filter((_, i) => i % everyN === 0)}
            tickFormat={(v) => fmtYear(Number(v))}
            tickLabelProps={() => ({ ...numTickProps, textAnchor: "middle" as const, dy: 4 })}
          />
        </Group>
      </svg>
      <ChartTooltip tip={tip} width={width} />
    </>
  );
}

export function NegativeHoursChart({ byYear }: NegativeHoursChartProps) {
  if (!byYear || byYear.length === 0) {
    return <EmptyState title="No negative-hours data" detail="SMARD negative-price hours unavailable." />;
  }
  return (
    <div className="relative h-full min-h-[180px] w-full">
      <ParentSize>
        {({ width, height }) =>
          width > 0 && height > 0 ? <Inner byYear={byYear} width={width} height={height} /> : null
        }
      </ParentSize>
    </div>
  );
}

export default NegativeHoursChart;
