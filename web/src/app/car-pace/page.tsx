import Link from "next/link";
import { notFound } from "next/navigation";

import { getBayesCarPace, type CarPaceTeam } from "@/lib/api";
import { fmt } from "@/lib/format";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function CarPacePage() {
  const data = await getBayesCarPace();
  if (!data) notFound();

  // Sort teams by best (most-negative = fastest) season they ever had.
  const ranked = [...data.teams].sort((a, b) => {
    const aMin = Math.min(...a.per_season.map((s) => s.value));
    const bMin = Math.min(...b.per_season.map((s) => s.value));
    return aMin - bMin;
  });

  const seasons = data.seasons_used.slice().sort((a, b) => a - b);
  const widest = Math.max(
    ...ranked.flatMap((t) =>
      t.per_season.flatMap((s) => [Math.abs(s.hdi_lo), Math.abs(s.hdi_hi)])
    ),
    0.5
  );

  return (
    <main className="min-h-dvh px-6 py-12 max-w-6xl mx-auto">
      <header className="space-y-3">
        <div className="flex items-baseline gap-3 font-mono text-xs uppercase tracking-widest text-dim">
          <Link href="/" className="hover:text-accent underline-offset-4 hover:underline">
            pacelab
          </Link>
          <span className="text-line-2">/</span>
          <span className="text-muted">car pace per team per season</span>
        </div>
        <h1 className="font-serif text-4xl md:text-5xl leading-tight">
          The cars, by the maths.
        </h1>
        <p className="text-muted max-w-3xl leading-relaxed">
          From the same Bayesian fit: <code className="font-mono text-accent">car_pace[team, season]</code>{" "}
          — the pace each team&apos;s car contributed, after the driver&apos;s skill, the
          track baseline, and session noise are subtracted. Identified through teammate
          variation within session and driver transfers across seasons. Negative = fast.
        </p>
      </header>

      <section className="mt-10">
        <div className="border border-line rounded-md bg-surface overflow-hidden">
          <table className="w-full font-mono text-xs">
            <thead className="text-dim">
              <tr className="border-b border-line">
                <th className="text-left px-3 py-2 font-normal">team</th>
                {seasons.map((y) => (
                  <th key={y} className="text-center px-2 py-2 font-normal" colSpan={1}>
                    {y}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ranked.map((team) => (
                <TeamRow key={team.team_name} team={team} seasons={seasons} widest={widest} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <footer className="mt-12 pt-6 border-t border-line font-mono text-xs text-dim">
        <p>
          generated {new Date(data.generated_at_utc).toISOString().replace("T", " ").slice(0, 19)} UTC
          · methodology:{" "}
          <Link href="/methodology" className="hover:text-accent underline-offset-4 hover:underline">
            /methodology
          </Link>
        </p>
      </footer>
    </main>
  );
}

function TeamRow({
  team,
  seasons,
  widest,
}: {
  team: CarPaceTeam;
  seasons: number[];
  widest: number;
}) {
  const byYear = Object.fromEntries(team.per_season.map((s) => [s.year, s]));
  return (
    <tr className="border-b border-line last:border-b-0">
      <td className="px-3 py-2">
        <div className="text-muted whitespace-nowrap">{team.team_name}</div>
      </td>
      {seasons.map((year) => {
        const s = byYear[year];
        if (!s || s.value == null) {
          return (
            <td key={year} className="px-2 py-2 text-dim text-center">
              —
            </td>
          );
        }
        const v = s.value;
        const tone = v < 0 ? "text-positive" : v > 0 ? "text-negative" : "";
        return (
          <td key={year} className={`px-2 py-2 text-right ${tone}`}>
            <div>{fmt.signedSeconds(v, 2)}</div>
            <div className="text-[9px] text-dim">
              [{s.hdi_lo.toFixed(1)}, {s.hdi_hi.toFixed(1)}]
            </div>
            <PaceBar lo={s.hdi_lo} hi={s.hdi_hi} median={v} widest={widest} />
          </td>
        );
      })}
    </tr>
  );
}

function PaceBar({
  lo,
  hi,
  median,
  widest,
}: {
  lo: number;
  hi: number;
  median: number;
  widest: number;
}) {
  const toPct = (v: number) => 50 + (v / widest) * 50;
  const leftPct = Math.max(0, toPct(lo));
  const widthPct = Math.max(0.5, Math.min(100 - leftPct, toPct(hi) - leftPct));
  const medianPct = Math.max(0, Math.min(100, toPct(median)));
  return (
    <div className="relative h-1.5 bg-surface-2 rounded-sm overflow-hidden mt-1">
      <div className="absolute top-0 bottom-0 w-px bg-line-2" style={{ left: "50%" }} />
      <div
        className="absolute top-0 bottom-0 rounded-sm opacity-50"
        style={{
          left: `${leftPct}%`,
          width: `${widthPct}%`,
          backgroundColor: median < 0 ? "var(--color-positive)" : "var(--color-negative)",
        }}
      />
      <div
        className="absolute top-0 bottom-0"
        style={{
          left: `${medianPct}%`,
          width: "2px",
          backgroundColor: median < 0 ? "var(--color-positive)" : "var(--color-negative)",
          filter: "brightness(1.6)",
        }}
      />
    </div>
  );
}
