/**
 * IdentityCard (§11 /farm/[id] left column): registry facts from MaStR with
 * license-aware SourceBadges. Quiet chrome — values in mono where numeric,
 * no gold (gold is data heroes, not labels; the KPIs carry it).
 */

import type { FarmDetail } from "@/lib/types";
import { fmt2, fmtInt, fmtMw } from "@/lib/format";
import { SourceBadge } from "@/components/SourceBadge";

export interface IdentityCardProps {
  farm: FarmDetail;
}

function Fact({
  label,
  value,
  num = false,
}: {
  label: string;
  value: string | null;
  num?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line py-1.5 last:border-b-0">
      <dt className="shrink-0 text-2xs uppercase tracking-wider text-low">{label}</dt>
      {value === null ? (
        <dd className="text-data text-low">–</dd>
      ) : (
        <dd className={`text-right text-data text-hi ${num ? "num" : ""}`}>{value}</dd>
      )}
    </div>
  );
}

export function IdentityCard({ farm }: IdentityCardProps) {
  return (
    <section aria-label="Farm identity">
      <header>
        <h1 className="font-display text-lg leading-tight text-hi">{farm.name}</h1>
        <p className="num mt-1 text-2xs text-low">{farm.farm_id}</p>
      </header>

      <dl className="mt-4">
        <Fact label="Capacity" value={fmtMw(farm.mw_total)} num />
        <Fact label="Units" value={fmtInt(farm.n_units)} num />
        <Fact label="Manufacturer" value={farm.manufacturer} />
        <Fact label="Turbine type" value={farm.turbine_type} />
        <Fact
          label="Hub height"
          value={farm.hub_height_m !== null ? `${fmtInt(farm.hub_height_m)} m` : null}
          num
        />
        <Fact
          label="Rotor Ø"
          value={farm.rotor_d_m !== null ? `${fmtInt(farm.rotor_d_m)} m` : null}
          num
        />
        <Fact
          label="Commissioned"
          value={farm.commissioning_year !== null ? String(farm.commissioning_year) : null}
          num
        />
        <Fact label="Bundesland" value={farm.bundesland} />
        <Fact label="Operator" value={farm.operator} />
        <Fact label="Coordinates" value={`${fmt2(farm.lat)}° N · ${fmt2(farm.lon)}° E`} num />
      </dl>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <SourceBadge
          label="MaStR"
          url="https://www.marktstammdatenregister.de"
          license="DL-DE/BY-2-0"
        />
        {farm.sources.map((s) => (
          <SourceBadge key={s.label + s.url} label={s.label} url={s.url} />
        ))}
      </div>
    </section>
  );
}

export default IdentityCard;
