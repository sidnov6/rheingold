"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";

/**
 * Left rail, 56px (§3.4). Quiet chrome: no gold on nav — gold is data only.
 */

const NAV = [
  { href: "/", label: "Fleet", glyph: "◈" },
  { href: "/backtest", label: "Backtest", glyph: "≋" },
  { href: "/methodology", label: "Method", glyph: "§" },
  { href: "/about", label: "About", glyph: "◦" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg0">
      <nav
        aria-label="Primary"
        className="z-20 flex w-14 shrink-0 flex-col items-center border-r border-line bg-bg1"
      >
        <Link
          href="/"
          className="flex h-14 w-14 items-center justify-center border-b border-line"
          title="RHEINGOLD"
        >
          {/* wordmark glyph — Newsreader R, text not chrome-gold */}
          <span className="font-display text-lg font-semibold text-hi">R</span>
        </Link>
        <div className="mt-2 flex flex-col gap-1">
          {NAV.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.label}
                className={clsx(
                  "group flex h-10 w-10 flex-col items-center justify-center rounded transition-colors",
                  active ? "bg-bg2 text-hi" : "text-low hover:bg-bg2 hover:text-mid",
                )}
              >
                <span aria-hidden className="text-md leading-none">
                  {item.glyph}
                </span>
                <span className="mt-0.5 text-[8px] uppercase tracking-wider">
                  {item.label}
                </span>
              </Link>
            );
          })}
        </div>
        <div className="mt-auto pb-3 text-center">
          <span
            className="inline-block h-2 w-2 rounded-full bg-rhine-500"
            title="API status"
            id="api-status-dot"
          />
        </div>
      </nav>
      <main className="relative min-w-0 flex-1 overflow-auto">{children}</main>
    </div>
  );
}
