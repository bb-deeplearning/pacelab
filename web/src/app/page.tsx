import Link from "next/link";

import {
  getBayesSkill,
  getIndex,
  type BayesDriver,
  type BayesPayload,
} from "@/lib/api";
import { fmt } from "@/lib/format";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function Home() {
  const [bayes, index] = await Promise.all([getBayesSkill(), getIndex().catch(() => null)]);

  if (!bayes) {
    return (
      <main className="min-h-dvh px-6 py-12 max-w-5xl mx-auto">
        <Header />
        <div className="mt-12 border border-line-2 rounded-md p-6 bg-surface">
          <p className="font-mono text-sm text-warning">
            posterior not built yet. run: <span className="text-accent">pacelab bayes fit</span>
          </p>
          <p className="font-mono text-xs text-muted mt-2">
            in the meantime, the descriptive metrics are at{" "}
            <Link href="/alltime" className="text-accent">/alltime</Link>.
          </p>
        </div>
      </main>
    );
  }

  // Top 10 by skill (lower is better). drivers list is already sorted ascending.
  const top = bayes.drivers.slice(0, 12);
  const bottom = bayes.drivers.slice(-8).reverse();

  const seasons = bayes.seasons_used.sort((a, b) => a - b);
  const sigmaDrift = bayes.scale_summaries_log.sigma_drift_skill;

  return (
    <main className="min-h-dvh px-6 py-12 max-w-6xl mx-auto">
      <Header />

      <section className="mt-10 grid grid-cols-1 md:grid-cols-4 gap-3">
        <Stat label="Drivers ranked" value={fmt.int(bayes.n_drivers)} />
        <Stat label="Seasons modelled" value={`${seasons[0]} → ${seasons.at(-1)}`} />
        <Stat label="Posterior draws" value={fmt.int(bayes.sampler.samples * bayes.sampler.chains)} />
        <Stat
          label="Lap-time noise (σε, log)"
          value={bayes.scale_summaries_log.sigma_epsilon.toFixed(4)}
        />
      </section>

      <section className="mt-10">
        <div className="border-b border-line pb-2 mb-4 flex items-baseline gap-3 flex-wrap">
          <h2 className="font-serif text-3xl">The ranking</h2>
          <span className="font-mono text-xs text-muted">
            driver_skill posterior, pooled across seasons raced · lower = faster
          </span>
        </div>
        <p className="text-muted leading-relaxed max-w-3xl mb-4">
          Each row is a driver&apos;s pooled posterior skill, in seconds-per-lap relative to
          the implied field-median driver, after subtracting their car&apos;s pace and the
          per-track baseline. Identified from teammate variation within sessions{" "}
          <em>and</em> from driver transfers across teams across {seasons.length} seasons.
          The bar is the 95% HDI; the line through it is the posterior median.
        </p>

        <PosteriorRanking drivers={bayes.drivers} />
      </section>

      <section className="mt-12 grid grid-cols-1 lg:grid-cols-2 gap-6">
        <FactCard
          title="Top 5"
          drivers={top.slice(0, 5)}
          tone="positive"
        />
        <FactCard
          title="Bottom 5"
          drivers={bottom.slice(0, 5)}
          tone="negative"
        />
      </section>

      <section className="mt-12">
        <h2 className="font-serif text-2xl border-b border-line pb-2 mb-4">
          Pairwise probabilities
        </h2>
        <p className="text-muted leading-relaxed mb-4 max-w-3xl">
          Computed directly from the posterior draws. P(A faster than B) is the share of
          posterior samples where A&apos;s pooled skill is lower (better) than B&apos;s. A
          probability near 0.5 means the CIs overlap and there&apos;s no statistical
          separation.
        </p>
        <PairwiseGrid bayes={bayes} drivers={top.slice(0, 6)} />
      </section>

      <section className="mt-12 grid grid-cols-1 md:grid-cols-2 gap-6 border-t border-line pt-6">
        <div>
          <h3 className="font-mono text-[10px] uppercase tracking-widest text-dim">More views</h3>
          <ul className="mt-3 space-y-2 font-mono text-sm">
            <li>
              <Link href="/car-pace" className="text-accent hover:underline">
                → car pace per team per season
              </Link>
            </li>
            <li>
              <Link href="/alltime" className="text-accent hover:underline">
                → descriptive teammate-paired leaderboards (raw view)
              </Link>
            </li>
            {index && index.seasons.length > 0 && (
              <li>
                <Link
                  href={`/seasons/${Math.max(...index.seasons)}`}
                  className="text-accent hover:underline"
                >
                  → season{" "}
                  {Math.max(...index.seasons)} per-driver descriptive metrics
                </Link>
              </li>
            )}
          </ul>
        </div>
        <div>
          <h3 className="font-mono text-[10px] uppercase tracking-widest text-dim">Reference</h3>
          <ul className="mt-3 space-y-2 font-mono text-sm">
            <li>
              <Link href="/methodology" className="text-accent hover:underline">
                → methodology (how the maths works)
              </Link>
            </li>
            <li>
              <a
                href="https://github.com/bb-deeplearning/pacelab"
                className="text-accent hover:underline"
              >
                → github.com/bb-deeplearning/pacelab
              </a>
            </li>
            <li className="text-dim">
              σ_drift (per-driver skill year-over-year, log): {sigmaDrift?.toFixed(4) ?? "—"}
            </li>
          </ul>
        </div>
      </section>

      <footer className="mt-16 pt-6 border-t border-line font-mono text-xs text-dim space-y-1">
        <p>
          model: {bayes.model_version ?? "v?"} · fit{" "}
          {new Date(bayes.generated_at_utc).toISOString().replace("T", " ").slice(0, 19)} UTC ·
          training rows {fmt.int(bayes.training_rows)} · elapsed{" "}
          {Math.round(bayes.elapsed_seconds)}s
        </p>
        <p>
          pacelab is unofficial. Formula 1 and related marks are trade marks of Formula
          One Licensing B.V.
        </p>
      </footer>
    </main>
  );
}

function Header() {
  return (
    <header className="space-y-4">
      <div className="flex items-baseline gap-3 font-mono text-xs uppercase tracking-widest text-dim">
        <span>pacelab</span>
        <span className="text-line-2">/</span>
        <span className="text-muted">F1 driver skill, car-pace-adjusted</span>
      </div>
      <h1 className="font-serif text-5xl md:text-6xl leading-tight">
        Who&apos;s actually fast — independent of the car.
      </h1>
      <p className="text-muted max-w-3xl leading-relaxed">
        A hierarchical Bayesian model on every clean racing lap from 2018 onwards. Each
        driver gets a posterior skill distribution after the car&apos;s pace, the track,
        the era, and session noise are explicitly modelled and subtracted. No bell-curve
        age assumption — a per-driver Gaussian random walk lets the data shape every
        career trajectory.
      </p>
    </header>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <article className="border border-line rounded-md bg-surface p-4">
      <div className="font-mono text-[10px] uppercase tracking-widest text-dim">{label}</div>
      <div className="font-mono text-2xl mt-2">{value}</div>
    </article>
  );
}

function FactCard({
  title,
  drivers,
  tone,
}: {
  title: string;
  drivers: BayesDriver[];
  tone: "positive" | "negative";
}) {
  return (
    <article className="border border-line rounded-md bg-surface p-4">
      <div className="font-mono text-[10px] uppercase tracking-widest text-dim">{title}</div>
      <ol className="mt-3 space-y-2">
        {drivers.map((d, idx) => {
          const cls = tone === "positive" ? "text-positive" : "text-negative";
          return (
            <li key={d.driver_code} className="flex items-baseline gap-3 font-mono text-sm">
              <span className="text-dim w-4">{idx + 1}.</span>
              <Link
                href={`/careers/${d.driver_code}`}
                className="text-accent hover:underline w-12"
              >
                {d.driver_code}
              </Link>
              <span className={`${cls} text-base`}>{fmt.signedSeconds(d.skill_seconds_per_lap)}</span>
              <span className="text-dim text-xs">
                [{d.hdi_lo_seconds.toFixed(2)}, {d.hdi_hi_seconds.toFixed(2)}]
              </span>
            </li>
          );
        })}
      </ol>
    </article>
  );
}

function PosteriorRanking({ drivers }: { drivers: BayesDriver[] }) {
  const widest = Math.max(
    ...drivers.map((d) =>
      Math.max(Math.abs(d.hdi_lo_seconds), Math.abs(d.hdi_hi_seconds))
    ),
    0.01
  );

  return (
    <div className="border border-line rounded-md bg-surface overflow-hidden">
      <table className="w-full font-mono text-xs">
        <thead className="text-dim">
          <tr className="border-b border-line">
            <th className="text-left px-3 py-2 font-normal w-10">#</th>
            <th className="text-left px-3 py-2 font-normal w-16">code</th>
            <th className="text-right px-3 py-2 font-normal">median</th>
            <th className="text-right px-3 py-2 font-normal hidden md:table-cell">HDI lo</th>
            <th className="text-right px-3 py-2 font-normal hidden md:table-cell">HDI hi</th>
            <th className="text-right px-3 py-2 font-normal w-12 hidden md:table-cell">sns</th>
            <th className="px-3 py-2 font-normal">posterior over field-median</th>
          </tr>
        </thead>
        <tbody>
          {drivers.map((d, idx) => (
            <PosteriorRow key={d.driver_code} d={d} idx={idx} widest={widest} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PosteriorRow({
  d,
  idx,
  widest,
}: {
  d: BayesDriver;
  idx: number;
  widest: number;
}) {
  const lo = d.hdi_lo_seconds;
  const hi = d.hdi_hi_seconds;
  const med = d.skill_seconds_per_lap;
  // Map [-widest, +widest] to [0%, 100%].
  const toPct = (v: number) => 50 + (v / widest) * 50;
  const leftPct = toPct(lo);
  const widthPct = toPct(hi) - leftPct;
  const medianPct = toPct(med);

  const tone = med < 0 ? "text-positive" : med > 0 ? "text-negative" : "";
  return (
    <tr className="border-b border-line last:border-b-0">
      <td className="px-3 py-1.5 text-dim">{idx + 1}</td>
      <td className="px-3 py-1.5">
        <Link href={`/careers/${d.driver_code}`} className="text-accent hover:underline">
          {d.driver_code}
        </Link>
      </td>
      <td className={`px-3 py-1.5 text-right ${tone}`}>{fmt.signedSeconds(med)}</td>
      <td className="px-3 py-1.5 text-right text-dim hidden md:table-cell">{fmt.signedSeconds(lo)}</td>
      <td className="px-3 py-1.5 text-right text-dim hidden md:table-cell">{fmt.signedSeconds(hi)}</td>
      <td className="px-3 py-1.5 text-right text-dim hidden md:table-cell">
        {d.seasons_raced?.length ?? "—"}
      </td>
      <td className="px-3 py-1.5">
        <div className="relative h-3 bg-surface-2 rounded-sm overflow-hidden">
          <div className="absolute top-0 bottom-0 w-px bg-line-2" style={{ left: "50%" }} />
          <div
            className="absolute top-0 bottom-0 rounded-sm opacity-50"
            style={{
              left: `${Math.max(0, leftPct)}%`,
              width: `${Math.max(0, Math.min(100 - leftPct, widthPct))}%`,
              backgroundColor: med < 0 ? "var(--color-positive)" : "var(--color-negative)",
            }}
          />
          <div
            className="absolute top-0 bottom-0"
            style={{
              left: `${Math.max(0, Math.min(100, medianPct))}%`,
              width: "2px",
              backgroundColor: med < 0 ? "var(--color-positive)" : "var(--color-negative)",
              filter: "brightness(1.6)",
            }}
          />
        </div>
      </td>
    </tr>
  );
}

function PairwiseGrid({
  bayes,
  drivers,
}: {
  bayes: BayesPayload;
  drivers: BayesDriver[];
}) {
  return (
    <div className="border border-line rounded-md bg-surface overflow-hidden">
      <table className="w-full font-mono text-xs">
        <thead className="text-dim">
          <tr className="border-b border-line">
            <th className="text-left px-2 py-2 font-normal">P(A faster B) →</th>
            {drivers.map((d) => (
              <th key={d.driver_code} className="text-center px-2 py-2 font-normal">
                {d.driver_code}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {drivers.map((a) => (
            <tr key={a.driver_code} className="border-b border-line last:border-b-0">
              <td className="px-2 py-1.5 text-muted">{a.driver_code}</td>
              {drivers.map((b) => {
                if (a.driver_code === b.driver_code) {
                  return (
                    <td key={b.driver_code} className="px-2 py-1.5 text-center text-dim">
                      —
                    </td>
                  );
                }
                const p =
                  bayes.pairwise_probability_a_faster_than_b[a.driver_code]?.[b.driver_code];
                if (p == null) {
                  return (
                    <td key={b.driver_code} className="px-2 py-1.5 text-center text-dim">
                      —
                    </td>
                  );
                }
                const tone = p > 0.85 ? "text-positive" : p < 0.15 ? "text-negative" : p > 0.6 ? "text-text" : p < 0.4 ? "text-muted" : "text-dim";
                return (
                  <td
                    key={b.driver_code}
                    className={`px-2 py-1.5 text-center ${tone}`}
                    style={{
                      backgroundColor:
                        p > 0.85
                          ? "rgba(74, 222, 128, 0.10)"
                          : p < 0.15
                          ? "rgba(239, 68, 68, 0.10)"
                          : undefined,
                    }}
                  >
                    {(p * 100).toFixed(0)}%
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
