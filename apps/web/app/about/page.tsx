import type { Metadata } from "next";

/**
 * /about (§17.3) — the project story. Quiet bg1 panels, restrained:
 * no gold except one data accent. Three beats, then the tagline.
 */

export const metadata: Metadata = {
  title: "About — RHEINGOLD",
  description:
    "Why RHEINGOLD exists: two years inside wind-turbine manufacturing, now underwriting the machines.",
};

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-14">
      <header>
        <p className="text-2xs uppercase tracking-widest text-low">About</p>
        <h1 className="mt-1 font-display text-xl font-medium text-hi">
          Manufacturing → capital
        </h1>
      </header>

      <div className="mt-8 space-y-4">
        {/* Beat 1 — Suzlon, manufacturing to capital */}
        <section className="rounded border border-line bg-bg1 px-6 py-5">
          <h2 className="text-2xs uppercase tracking-wider text-low">
            Where the assumptions come from
          </h2>
          <p className="mt-2 text-md leading-relaxed text-hi">
            Before this was a finance tool, it was two years of manufacturing
            data systems across{" "}
            <span className="num text-gold-500">10+</span> wind plants at
            Suzlon — watching real turbines fail, get repaired, and recover.
            RHEINGOLD is the other side of that work: building the systems that{" "}
            <em className="font-display not-italic italic">finance</em> the
            turbines instead of the systems that build them. The availability
            and O&amp;M defaults in the engine are not literature values; they
            come from someone who has stood under the machines.
          </p>
        </section>

        {/* Beat 2 — the Senvion sentence. One sentence, no more. */}
        <section className="rounded border border-line bg-bg1 px-6 py-5">
          <h2 className="text-2xs uppercase tracking-wider text-low">
            A quiet coincidence
          </h2>
          <p className="mt-2 text-md leading-relaxed text-mid">
            Several turbines in RHEINGOLD&apos;s fleet are Senvion machines —
            formerly REpower, majority-owned by Suzlon in the early 2010s — so
            the author&apos;s employer&apos;s history is literally standing in
            the German landscape this tool underwrites.
          </p>
        </section>

        {/* Beat 3 — the tagline, Newsreader display quote */}
        <section className="rounded border border-line bg-bg1 px-6 py-10 text-center">
          <blockquote>
            <p className="font-display text-2xl italic leading-tight text-hi">
              &bdquo;Das neue Rheingold ist Wind.&ldquo;
            </p>
          </blockquote>
          <p className="mt-4 text-data text-low">
            The gold on the map is the point: every registered onshore turbine
            in Germany, underwritten with public data, a deterministic engine,
            and an agent layer that may only narrate what it can cite.
          </p>
        </section>
      </div>

      <footer className="mt-10 border-t border-line pt-4 text-data text-mid">
        <p>
          <span className="text-hi">Siddharth Jain</span> — built with public
          German energy data (MaStR, SMARD, Netztransparenz, BNetzA). Sources,
          licenses, and every formula: see Methodology.
        </p>
      </footer>
    </div>
  );
}
