/**
 * SourceBadge (§3.4): tiny license-aware chip attached to registry facts and
 * chart footers. Quiet chrome — no gold (gold is data, not badges).
 */

export interface SourceBadgeProps {
  label: string;
  url?: string;
  license?: string;
}

export function SourceBadge({ label, url, license }: SourceBadgeProps) {
  const body = (
    <>
      <span className="text-mid">{label}</span>
      {license ? <span className="text-low"> · {license}</span> : null}
    </>
  );
  const cls =
    "inline-flex items-center gap-1 rounded-sm border border-line bg-bg2 px-1.5 py-0.5 text-[10px] leading-none tracking-wide";
  if (url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className={`${cls} transition-colors hover:border-rhine-500`}
        title={license ? `${label} — ${license}` : label}
      >
        {body}
        <span aria-hidden className="text-low">
          ↗
        </span>
      </a>
    );
  }
  return <span className={cls}>{body}</span>;
}

export default SourceBadge;
