"use client";

import { useMemo } from "react";
import { ParentSize } from "@visx/responsive";
import { Group } from "@visx/group";
import { scaleLinear } from "@visx/scale";
import { AreaClosed, Line, LinePath } from "@visx/shape";
import { AxisBottom } from "@visx/axis";
import { curveMonotoneX } from "@visx/curve";
import { fmtGwh } from "@/lib/format";
import { EmptyState } from "@/components/EmptyState";
import { C, axisLineProps, numTickProps } from "./theme";

/**
 * EnergyDistribution (§3.4/§11 Energy): smooth normal-shaped density
 * synthesized purely for display from the P50/P75/P90 quantiles — labeled
 * "illustrative density" — with vertical exceedance markers. Gold P50.
 */

export interface EnergyDistributionProps {
  p50: number;
  p75: number;
  p90: number;
  p901yr?: number;
}

const MARGIN = { top: 26, right: 16, bottom: 34, left: 16 };
const Z90 = 1.2816; // Φ⁻¹(0.90)

function pdf(x: number, mu: number, sigma: number): number {
  const z = (x - mu) / sigma;
  return Math.exp(-0.5 * z * z);
}

function Inner({
  p50,
  p75,
  p90,
  p901yr,
  width,
  height,
}: Required<Pick<EnergyDistributionProps, "p50" | "p75" | "p90">> &
  Pick<EnergyDistributionProps, "p901yr"> & { width: number; height: number }) {
  const xMax = width - MARGIN.left - MARGIN.right;
  const yMax = height - MARGIN.top - MARGIN.bottom;

  // Display-only sigma implied by the P90 exceedance level.
  const sigma = useMemo(() => {
    const s = (p50 - p90) / Z90;
    return s > 0 ? s : Math.max(p50 * 0.08, 1e-9);
  }, [p50, p90]);

  const domainLo = Math.min(p901yr ?? p90, p50 - 3.2 * sigma);
  const domainHi = p50 + 3.2 * sigma;

  const xScale = scaleLinear<number>({ domain: [domainLo, domainHi], range: [0, xMax] });
  const yScale = scaleLinear<number>({ domain: [0, 1.05], range: [yMax, 0] });

  const curve = useMemo(() => {
    const pts: { x: number; y: number }[] = [];
    const N = 80;
    for (let i = 0; i <= N; i++) {
      const x = domainLo + ((domainHi - domainLo) * i) / N;
      pts.push({ x, y: pdf(x, p50, sigma) });
    }
    return pts;
  }, [domainLo, domainHi, p50, sigma]);

  const markers: { key: string; x: number; label: string; color: string; dashed?: boolean }[] = [
    { key: "p90", x: p90, label: "P90", color: C.rhine },
    { key: "p75", x: p75, label: "P75", color: C.rhineLight },
    { key: "p50", x: p50, label: "P50", color: C.gold },
  ];
  if (p901yr !== undefined) {
    markers.unshift({ key: "p901", x: p901yr, label: "P90 1y", color: C.warn, dashed: true });
  }

  return (
    <svg width={width} height={height} role="img" aria-label="Illustrative energy production density with exceedance markers">
      <Group left={MARGIN.left} top={MARGIN.top}>
        <AreaClosed<{ x: number; y: number }>
          data={curve}
          x={(d) => xScale(d.x)}
          y={(d) => yScale(d.y)}
          yScale={yScale}
          curve={curveMonotoneX}
          fill={C.goldDim}
        />
        <LinePath<{ x: number; y: number }>
          data={curve}
          x={(d) => xScale(d.x)}
          y={(d) => yScale(d.y)}
          curve={curveMonotoneX}
          stroke={C.textLow}
          strokeWidth={1}
        />
        {markers.map((m) => {
          const mx = xScale(m.x);
          return (
            <Group key={m.key}>
              <Line
                from={{ x: mx, y: yScale(pdf(m.x, p50, sigma)) }}
                to={{ x: mx, y: yMax }}
                stroke={m.color}
                strokeWidth={m.key === "p50" ? 1.5 : 1}
                strokeDasharray={m.dashed ? "3,3" : undefined}
              />
              <text
                x={mx}
                y={-6}
                textAnchor="middle"
                fontSize={10}
                fontFamily={numTickProps.fontFamily}
                fill={m.color}
              >
                {m.label}
              </text>
              <text
                x={mx}
                y={6}
                textAnchor="middle"
                fontSize={9}
                fontFamily={numTickProps.fontFamily}
                fill={C.textLow}
              >
                {fmtGwh(m.x)}
              </text>
            </Group>
          );
        })}
        <AxisBottom
          top={yMax}
          scale={xScale}
          numTicks={5}
          stroke={axisLineProps.stroke}
          tickStroke={axisLineProps.stroke}
          tickFormat={(v) => fmtGwh(Number(v))}
          tickLabelProps={() => ({ ...numTickProps, textAnchor: "middle" as const, dy: 4 })}
        />
      </Group>
    </svg>
  );
}

export function EnergyDistribution({ p50, p75, p90, p901yr }: EnergyDistributionProps) {
  if (!Number.isFinite(p50) || !Number.isFinite(p75) || !Number.isFinite(p90) || p50 <= 0) {
    return <EmptyState title="No energy distribution" detail="P50/P75/P90 quantiles unavailable." />;
  }
  return (
    <div className="relative h-full min-h-[200px] w-full">
      <div className="absolute right-1 top-0 z-10 text-[10px] italic text-low">
        illustrative density — shape synthesized from P50/P75/P90
      </div>
      <ParentSize>
        {({ width, height }) =>
          width > 0 && height > 0 ? (
            <Inner p50={p50} p75={p75} p90={p90} p901yr={p901yr} width={width} height={height} />
          ) : null
        }
      </ParentSize>
    </div>
  );
}

export default EnergyDistribution;
