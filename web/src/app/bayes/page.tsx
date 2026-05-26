import Link from "next/link";
import { notFound } from "next/navigation";

import { getBayesSkill, type BayesDriver } from "@/lib/api";
import { fmt } from "@/lib/format";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function BayesPage() {
  const data = await getBayesSkill();
  if (!data) notFound();

  const sortedDrivers = [...data.drivers].sort(
    (a, b) => a.skill_seconds_per_lap - b.skill_seconds_per_lap
  );
  const widest = Math.max(
    ...sortedDrivers.map((d) => Math.max(Math.abs(d.hdi_lo_seconds), Math.abs(d.hdi_hi_seconds))),
    0.01
  );

  return (
    <main className="min-h-dvh px-6 py-12 max-w-6xl mx-auto">
      <header className="space-y-3">
        <div className="flex items-baseline gap-3 font-mono text-xs uppercase tracking-widest text-dim">
          <Link href="/" className="hover:text-accent underline-offset-4 hover:underline">
            pacelab
          </Link>
          <span className="text-line-2">/</span>
          <span className="text-muted">bayesian skill posterior</span>
        </div>
        <h1 className="font-serif text-4xl md:text-5xl leading-tight">
          Driver skill, fit with hierarchical Bayes.
        </h1>
        <p className="text-muted max-w-3xl leading-relaxed">
          A NUTS-fit numpyro model on{" "}
          <strong className="text-text">{fmt.int(data.training_rows)}</strong> clean racing
          laps across <strong className="text-text">{data.seasons_used.join(", ")}</strong>.
          Each lap is modelled as{" "}
          <code className="font-mono text-accent">
            log(lap_time) = µ_session_compound + α_team[team, era] + α_driver[driver] +
            β·stint_age + γ·lap_number + ε
          </code>
          . The session-compound intercept absorbs the per-(track, compound) baseline;
          the team-era term absorbs the car. What survives is α_driver — a posterior
          distribution per driver, identified through teammate variation within a team-era
          and through driver transfers across team-eras.
        </p>
        <p className="text-muted max-w-3xl leading-relaxed">
          Reported values are <strong className="text-text">seconds per lap</strong> at a 95-second
          reference lap, with a 95% highest-density interval. Negative = faster than the
          implied field-median driver after car-quality is accounted for.
        </p>
      </header>

      <section className="mt-10 grid grid-cols-1 md:grid-cols-3 gap-3">
        <SamplerCard
          label="Training rows"
          value={fmt.int(data.training_rows)}
          sub={`${data.n_drivers} drivers · ${data.n_teams} teams · ${data.n_eras} eras`}
        />
        <SamplerCard
          label="Posterior draws"
          value={fmt.int(data.sampler.samples * data.sampler.chains)}
          sub={`NUTS · ${data.sampler.warmup} warmup · ${data.sampler.chains} chains`}
        />
        <SamplerCard
          label="σ(driver) / σ(team) / σ(ε)  [log]"
          value={`${data.scale_summaries_log.sigma_driver.toFixed(4)} / ${data.scale_summaries_log.sigma_team.toFixed(4)} / ${data.scale_summaries_log.sigma_epsilon.toFixed(4)}`}
          sub="random-effect scales in log(lap_time)"
        />
      </section>

      <section className="mt-12">
        <div className="border-b border-line pb-2 mb-4">
          <h2 className="font-serif text-2xl">Posterior skill ranking</h2>
          <p className="font-mono text-xs text-muted mt-1">
            lower = faster. shaded bar = 95% HDI. dot = posterior median.
          </p>
        </div>

        <div className="border border-line rounded-md bg-surface overflow-hidden">
          <table className="w-full font-mono text-xs">
            <thead className="text-dim">
              <tr className="border-b border-line">
                <th className="text-left px-3 py-2 font-normal w-10">#</th>
                <th className="text-left px-3 py-2 font-normal w-16">code</th>
                <th className="text-right px-3 py-2 font-normal">median</th>
                <th className="text-right px-3 py-2 font-normal">HDI lo</th>
                <th className="text-right px-3 py-2 font-normal">HDI hi</th>
                <th className="px-3 py-2 font-normal">posterior over field-median</th>
              </tr>
            </thead>
            <tbody>
              {sortedDrivers.map((d, idx) => (
                <PosteriorRow key={d.driver_code} d={d} idx={idx} widest={widest} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-12">
        <div className="border-b border-line pb-2 mb-4">
          <h2 className="font-serif text-2xl">Pairwise probabilities (sampled)</h2>
          <p className="font-mono text-xs text-muted mt-1">
            P(driver A faster than driver B), computed from the posterior draws.
            this is what proper Bayesian inference gives you that point estimates can&apos;t.
          </p>
        </div>
        <p className="text-muted text-sm">
          Hit{" "}
          <code className="font-mono text-accent">
            /api/bayes/pair/&lt;A&gt;/&lt;B&gt;
          </code>{" "}
          for any pair. Examples:{" "}
          <Link href="/api/bayes/pair/VER/HAM" className="text-accent hover:underline">
            VER vs HAM
          </Link>
          ,{" "}
          <Link href="/api/bayes/pair/HAM/RUS" className="text-accent hover:underline">
            HAM vs RUS
          </Link>
          ,{" "}
          <Link href="/api/bayes/pair/NOR/PIA" className="text-accent hover:underline">
            NOR vs PIA
          </Link>
          .
        </p>
      </section>

      <footer className="mt-16 pt-6 border-t border-line font-mono text-xs text-dim space-y-1">
        <p>
          fit on {new Date(data.generated_at_utc).toISOString().replace("T", " ").slice(0, 19)} UTC ·
          elapsed {Math.round(data.elapsed_seconds)} s
        </p>
        <p>
          full mathematical write-up:{" "}
          <Link href="/methodology" className="hover:text-accent underline-offset-4 hover:underline">
            /methodology
          </Link>
        </p>
      </footer>
    </main>
  );
}

function SamplerCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <article className="border border-line rounded-md bg-surface p-4">
      <div className="font-mono text-[10px] uppercase tracking-widest text-dim">{label}</div>
      <div className="font-mono text-2xl mt-2">{value}</div>
      <div className="font-mono text-[10px] text-muted mt-1">{sub}</div>
    </article>
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
  const pixelsPerSecond = 100 / widest;
  const leftPct = 50 + lo * pixelsPerSecond / 2;
  const widthPct = ((hi - lo) * pixelsPerSecond) / 2;
  const medianPct = 50 + med * pixelsPerSecond / 2;

  const tone = med < 0 ? "text-positive" : med > 0 ? "text-negative" : "";
  return (
    <tr className="border-b border-line last:border-b-0">
      <td className="px-3 py-1.5 text-dim">{idx + 1}</td>
      <td className="px-3 py-1.5 text-accent">{d.driver_code}</td>
      <td className={`px-3 py-1.5 text-right ${tone}`}>{fmt.signedSeconds(med)}</td>
      <td className="px-3 py-1.5 text-right text-dim">{fmt.signedSeconds(lo)}</td>
      <td className="px-3 py-1.5 text-right text-dim">{fmt.signedSeconds(hi)}</td>
      <td className="px-3 py-1.5">
        <div className="relative h-3 bg-surface-2 rounded-sm overflow-hidden">
          {/* zero line */}
          <div
            className="absolute top-0 bottom-0 w-px bg-line-2"
            style={{ left: "50%" }}
          />
          {/* HDI band */}
          <div
            className="absolute top-0 bottom-0 rounded-sm opacity-50"
            style={{
              left: `${Math.max(0, leftPct)}%`,
              width: `${Math.max(0, Math.min(100 - leftPct, widthPct))}%`,
              backgroundColor: med < 0 ? "var(--color-positive)" : "var(--color-negative)",
            }}
          />
          {/* median point */}
          <div
            className="absolute top-0 bottom-0 w-px"
            style={{
              left: `${Math.max(0, Math.min(100, medianPct))}%`,
              backgroundColor: med < 0 ? "var(--color-positive)" : "var(--color-negative)",
              filter: "brightness(1.4)",
              width: "2px",
            }}
          />
        </div>
      </td>
    </tr>
  );
}
