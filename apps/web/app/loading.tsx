/**
 * Root loading skeleton (§3): pulse on bg2 blocks over the map-explorer
 * layout — filter bar top-left, stats strip top-right, map field behind.
 */
export default function Loading() {
  return (
    <div className="map-glow relative h-full w-full bg-bg0" aria-busy="true" aria-label="Loading">
      {/* filter bar ghost */}
      <div className="absolute left-4 top-4 flex gap-2">
        <div className="h-8 w-40 animate-pulse rounded bg-bg2" />
        <div className="h-8 w-28 animate-pulse rounded bg-bg2" />
        <div className="h-8 w-28 animate-pulse rounded bg-bg2" />
      </div>
      {/* fleet stats strip ghost */}
      <div className="absolute right-4 top-4 flex gap-2">
        <div className="h-8 w-24 animate-pulse rounded bg-bg2" />
        <div className="h-8 w-24 animate-pulse rounded bg-bg2" />
        <div className="h-8 w-32 animate-pulse rounded bg-bg2" />
      </div>
      {/* map field ghost */}
      <div className="flex h-full items-center justify-center">
        <div className="h-72 w-72 animate-pulse rounded-full bg-bg2 opacity-40" />
      </div>
    </div>
  );
}
