/**
 * Dossier loading skeleton (§3, §11 /farm/[id]): left 340px identity column +
 * right tabbed area with KPI-card ghosts. Pulse on bg2 blocks.
 */
export default function Loading() {
  return (
    <div className="flex h-full w-full" aria-busy="true" aria-label="Loading dossier">
      {/* left identity column */}
      <div className="w-[340px] shrink-0 space-y-3 border-r border-line bg-bg1 p-4">
        <div className="h-6 w-3/4 animate-pulse rounded bg-bg2" />
        <div className="h-4 w-1/2 animate-pulse rounded bg-bg2" />
        <div className="mt-4 space-y-2">
          {Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="flex justify-between gap-3">
              <div className="h-4 w-24 animate-pulse rounded bg-bg2" />
              <div className="h-4 w-20 animate-pulse rounded bg-bg2" />
            </div>
          ))}
        </div>
        <div className="mt-6 h-9 w-full animate-pulse rounded bg-bg2" />
      </div>

      {/* right: tabs + KPI grid + chart */}
      <div className="min-w-0 flex-1 p-6">
        <div className="flex gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-8 w-20 animate-pulse rounded bg-bg2" />
          ))}
        </div>
        <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded border border-line bg-bg2" />
          ))}
        </div>
        <div className="mt-6 h-72 animate-pulse rounded border border-line bg-bg2" />
      </div>
    </div>
  );
}
