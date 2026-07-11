/**
 * MetricStat (§3.4): inline label + mono value + optional hint. Quieter than
 * KPICard — for secondary stats (LLCR, capture rate, gearing …).
 */

export interface MetricStatProps {
  label: string;
  value: string;
  hint?: string;
}

export function MetricStat({ label, value, hint }: MetricStatProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-2xs uppercase tracking-wider text-low">{label}</span>
      <span className="num text-md text-hi">{value}</span>
      {hint ? <span className="text-2xs text-low">{hint}</span> : null}
    </div>
  );
}

export default MetricStat;
