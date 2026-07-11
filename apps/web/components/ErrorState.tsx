import clsx from "clsx";

/**
 * ErrorState (§3.4). Quiet, honest failure panel — no gold, no drama.
 * Used wherever an API call fails or a data artifact is absent.
 */
export interface ErrorStateProps {
  title: string;
  detail?: string;
  hint?: string;
  action?: React.ReactNode;
  className?: string;
}

export function ErrorState({ title, detail, hint, action, className }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={clsx(
        "rounded border border-line bg-bg1 px-5 py-4",
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <span aria-hidden className="text-warn">
          ▲
        </span>
        <h3 className="text-base font-medium text-hi">{title}</h3>
      </div>
      {detail && <p className="mt-1.5 text-data text-mid">{detail}</p>}
      {hint && (
        <p className="mt-2 font-mono text-2xs text-low">
          {hint}
        </p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export default ErrorState;
