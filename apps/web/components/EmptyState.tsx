/**
 * EmptyState (§3.4): quiet placeholder for absent data. No gold, no drama.
 */

export interface EmptyStateProps {
  title: string;
  detail?: string;
  action?: React.ReactNode;
}

export function EmptyState({ title, detail, action }: EmptyStateProps) {
  return (
    <div className="flex h-full min-h-[120px] w-full flex-col items-center justify-center gap-1 rounded border border-dashed border-line bg-bg1 px-6 py-8 text-center">
      <span className="text-base text-mid">{title}</span>
      {detail ? <span className="max-w-md text-2xs text-low">{detail}</span> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export default EmptyState;
