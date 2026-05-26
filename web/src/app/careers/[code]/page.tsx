import Link from "next/link";
import { notFound } from "next/navigation";

import { getBayesSkill, getCareer, type DriverCareer } from "@/lib/api";
import { fmt } from "@/lib/format";

export const dynamic = "force-dynamic";
export const revalidate = 0;

interface PageProps {
  params: Promise<{ code: string }>;
}

export default async function CareerPage({ params }: PageProps) {
  const { code: codeRaw } = await params;
  const code = codeRaw.toUpperCase();
  const [bayes, descriptive] = await Promise.all([getBayesSkill(), getCareer(code)]);

  const bayesDriver = bayes?.drivers.find((d) => d.driver_code === code);
  if (!bayesDriver && !descriptive) notFound();

  return (
    <main className="min-h-dvh px-6 py-12 max-w-6xl mx-auto">
      <header className="space-y-3">
        <div className="flex items-baseline gap-3 font-mono text-xs uppercase tracking-widest text-dim">
          <Link href="/" className="hover:text-accent underline-offset-4 hover:underline">
            pacelab
          </Link>
          <span className="text-line-2">/</span>
          <span className="text-muted">{code}</span>
        </div>
        <h1 className="font-serif text-4xl md:text-5xl leading-tight">
          {descriptive?.full_name ?? code}
        </h1>
        {bayesDriver && (
          <p className="text-muted leading-relaxed max-w-3xl">
            Career-pooled skill posterior:{" "}
            <span className="font-mono text-accent">{fmt.signedSeconds(bayesDriver.skill_seconds_per_lap)}</span>{" "}
            per lap relative to the implied field-median driver
            (95% HDI [{bayesDriver.hdi_lo_seconds.toFixed(2)}, {bayesDriver.hdi_hi_seconds.toFixed(2)}]),
            with car pace, track, era and lap-time noise explicitly subtracted.
          </p>
        )}
      </header>

      {bayesDriver?.per_season && bayesDriver.per_season.length > 0 && (
        <section className="mt-10">
          <h2 className="font-serif text-2xl border-b border-line pb-2 mb-4">
            Skill trajectory (Bayesian random walk posterior)
          </h2>
          <p className="text-muted text-sm mb-4 max-w-3xl">
            Per-season posterior of <code className="font-mono text-accent">driver_skill</code>{" "}
            for {code}. Bar is the 95% HDI; dot is the median. The team strip shows where
            {" "}they raced that year — the skill estimate is car-adjusted, so the same
            driver moving to a new team doesn&apos;t artificially jump.
          </p>
          <SkillTrajectory perSeason={bayesDriver.per_season} />
        </section>
      )}

      {descriptive && descriptive.seasons.length > 0 && (
        <section className="mt-12">
          <h2 className="font-serif text-2xl border-b border-line pb-2 mb-4">
            Team timeline
          </h2>
          <div className="flex flex-wrap gap-2">
            {descriptive.seasons.map((s) => (
              <div
                key={s.season}
                className="flex items-center gap-2 border border-line rounded-sm px-2 py-1 bg-surface"
              >
                <span
                  className="w-1 h-4 rounded-sm"
                  style={{ background: `#${s.team_color || "555"}` }}
                />
                <span className="font-mono text-xs text-muted">{s.season}</span>
                <span className="font-mono text-xs">{s.team_name}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {descriptive && (
        <section className="mt-12">
          <details className="group">
            <summary className="font-mono text-xs text-muted cursor-pointer hover:text-accent">
              ▸ raw teammate-paired metrics per season (descriptive view)
            </summary>
            <div className="mt-4 overflow-x-auto border border-line rounded-md bg-surface">
              <DescriptiveTable career={descriptive} />
            </div>
          </details>
        </section>
      )}

      <footer className="mt-16 pt-6 border-t border-line font-mono text-xs text-dim">
        <p>
          {descriptive?.seasons.length ?? 0} season(s) in the descriptive frame ·{" "}
          {bayesDriver?.seasons_raced?.length ?? 0} season(s) in the Bayesian fit ·{" "}
          <Link href="/" className="hover:text-accent underline-offset-4 hover:underline">
            ← all-time skill ranking
          </Link>
        </p>
      </footer>
    </main>
  );
}

function SkillTrajectory({
  perSeason,
}: {
  perSeason: NonNullable<NonNullable<Awaited<ReturnType<typeof getBayesSkill>>>["drivers"][number]["per_season"]>;
}) {
  if (perSeason.length === 0) return null;

  const widest = Math.max(
    ...perSeason.flatMap((s) => [Math.abs(s.hdi_lo), Math.abs(s.hdi_hi)]),
    0.5
  );
  const toPct = (v: number) => 50 + (v / widest) * 50;

  return (
    <div className="border border-line rounded-md bg-surface overflow-hidden">
      <table className="w-full font-mono text-xs">
        <thead className="text-dim">
          <tr className="border-b border-line">
            <th className="text-left px-3 py-2 font-normal w-16">year</th>
            <th className="text-left px-3 py-2 font-normal">team</th>
            <th className="text-right px-3 py-2 font-normal w-24">median</th>
            <th className="text-right px-3 py-2 font-normal w-32 hidden md:table-cell">
              95% HDI
            </th>
            <th className="px-3 py-2 font-normal">posterior</th>
          </tr>
        </thead>
        <tbody>
          {perSeason.map((s) => {
            const med = s.value;
            const isGood = med < 0;
            const tone = med < 0 ? "text-positive" : med > 0 ? "text-negative" : "";
            const leftPct = Math.max(0, toPct(s.hdi_lo));
            const widthPct = Math.max(
              0.5,
              Math.min(100 - leftPct, toPct(s.hdi_hi) - leftPct)
            );
            const medianPct = Math.max(0, Math.min(100, toPct(med)));
            return (
              <tr key={s.year} className="border-b border-line last:border-b-0">
                <td className="px-3 py-2 text-muted">{s.year}</td>
                <td className="px-3 py-2 text-muted">{s.team ?? "—"}</td>
                <td className={`px-3 py-2 text-right ${tone}`}>
                  {fmt.signedSeconds(med)}
                </td>
                <td className="px-3 py-2 text-right text-dim hidden md:table-cell">
                  [{s.hdi_lo.toFixed(2)}, {s.hdi_hi.toFixed(2)}]
                </td>
                <td className="px-3 py-2">
                  <div className="relative h-2.5 bg-surface-2 rounded-sm overflow-hidden">
                    <div
                      className="absolute top-0 bottom-0 w-px bg-line-2"
                      style={{ left: "50%" }}
                    />
                    <div
                      className="absolute top-0 bottom-0 rounded-sm opacity-50"
                      style={{
                        left: `${leftPct}%`,
                        width: `${widthPct}%`,
                        backgroundColor: isGood
                          ? "var(--color-positive)"
                          : "var(--color-negative)",
                      }}
                    />
                    <div
                      className="absolute top-0 bottom-0"
                      style={{
                        left: `${medianPct}%`,
                        width: "2px",
                        backgroundColor: isGood
                          ? "var(--color-positive)"
                          : "var(--color-negative)",
                        filter: "brightness(1.6)",
                      }}
                    />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DescriptiveTable({ career }: { career: DriverCareer }) {
  const metrics: Array<{
    id: keyof DriverCareer["seasons"][number]["metrics"];
    label: string;
  }> = [
    { id: "qualifying_pace_vs_teammate_s", label: "Qualifying Δ vs teammate" },
    { id: "race_pace_vs_teammate_s", label: "Race-pace Δ vs teammate" },
    { id: "stint_consistency_residual_sd_s", label: "Stint consistency (SD)" },
  ];
  return (
    <table className="w-full font-mono text-xs min-w-[640px]">
      <thead className="text-dim">
        <tr className="border-b border-line">
          <th className="text-left px-3 py-2 font-normal">metric</th>
          {career.seasons.map((s) => (
            <th key={s.season} className="text-right px-3 py-2 font-normal">
              {s.season}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {metrics.map((m) => (
          <tr key={m.id} className="border-b border-line last:border-b-0">
            <td className="px-3 py-2 text-muted whitespace-nowrap">{m.label}</td>
            {career.seasons.map((s) => {
              const v = s.metrics[m.id]?.value;
              const n = s.metrics[m.id]?.n ?? 0;
              const valid = typeof v === "number" && Number.isFinite(v);
              return (
                <td
                  key={s.season}
                  className={
                    "px-3 py-2 text-right " +
                    (valid && v < 0 ? "text-positive" : valid && v > 0 ? "text-negative" : "")
                  }
                >
                  {valid ? fmt.signedSeconds(v) : "—"}
                  <div className="text-[9px] text-dim">n={n}</div>
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
