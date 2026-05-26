import Link from "next/link";
import { notFound } from "next/navigation";

import { getIndex, getLeaderboards, type LeaderboardEntry } from "@/lib/api";
import { fmt } from "@/lib/format";

export const dynamic = "force-dynamic";
export const revalidate = 0;

interface PageProps {
  params: Promise<{ season: string }>;
}

export default async function SeasonLeaderboards({ params }: PageProps) {
  const { season: seasonRaw } = await params;
  const season = Number(seasonRaw);
  if (!Number.isFinite(season)) notFound();

  const [leaderboards, index] = await Promise.all([getLeaderboards(season), getIndex()]);
  if (!leaderboards) notFound();

  const seasons = index.seasons.slice().sort((a, b) => b - a);

  return (
    <main className="min-h-dvh px-6 py-12 max-w-6xl mx-auto">
      <header className="space-y-3">
        <div className="flex items-baseline gap-3 font-mono text-xs uppercase tracking-widest text-dim">
          <Link href="/" className="hover:text-accent underline-offset-4 hover:underline">
            pacelab
          </Link>
          <span className="text-line-2">/</span>
          <span className="text-muted">season {season} leaderboards</span>
        </div>
        <h1 className="font-serif text-4xl md:text-5xl leading-tight">
          {season} season — by the numbers
        </h1>
        <p className="text-muted max-w-2xl leading-relaxed">
          Ranked on each headline metric. Every entry is teammate-paired where
          applicable, so a low qualifying-delta number means the driver was faster than
          the other car in the same garage — independent of how good that car was.
        </p>
        <div className="flex flex-wrap items-center gap-2 pt-2 font-mono text-xs">
          <span className="text-dim">season:</span>
          {seasons.map((s) => (
            <Link
              key={s}
              href={`/seasons/${s}`}
              className={
                "px-2 py-1 border rounded-sm " +
                (s === season
                  ? "border-accent text-accent"
                  : "border-line text-muted hover:border-line-2 hover:text-text")
              }
            >
              {s}
            </Link>
          ))}
        </div>
      </header>

      {leaderboards.metrics.map((metric) => {
        const rows = leaderboards.leaderboards[metric.id] ?? [];
        return (
          <section key={metric.id} className="mt-12">
            <div className="border-b border-line pb-2 mb-4 flex items-baseline gap-3">
              <h2 className="font-serif text-2xl">{metric.label}</h2>
              <span className="font-mono text-xs text-muted">
                {metric.lower_is_better ? "lower is better" : "higher is better"}
              </span>
            </div>
            <LeaderboardTable rows={rows} lowerIsBetter={metric.lower_is_better} season={season} />
          </section>
        );
      })}
    </main>
  );
}

function LeaderboardTable({
  rows,
  lowerIsBetter,
  season,
}: {
  rows: LeaderboardEntry[];
  lowerIsBetter: boolean;
  season: number;
}) {
  if (rows.length === 0) {
    return <p className="font-mono text-xs text-dim">no data.</p>;
  }
  const max = Math.max(...rows.map((r) => (r.value == null ? 0 : Math.abs(r.value))), 0.01);

  return (
    <div className="border border-line rounded-md overflow-hidden bg-surface">
      <table className="w-full font-mono text-xs">
        <thead className="text-dim">
          <tr className="border-b border-line">
            <th className="text-left px-3 py-2 font-normal w-12">#</th>
            <th className="text-left px-3 py-2 font-normal w-16">code</th>
            <th className="text-left px-3 py-2 font-normal">driver</th>
            <th className="text-left px-3 py-2 font-normal">team</th>
            <th className="text-right px-3 py-2 font-normal">value</th>
            <th className="text-right px-3 py-2 font-normal hidden md:table-cell">95% CI</th>
            <th className="text-right px-3 py-2 font-normal w-14">n</th>
            <th className="px-3 py-2 font-normal w-1/4">distribution</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, idx) => {
            const v = r.value ?? 0;
            const isGood = lowerIsBetter ? v < 0 : v > 0;
            const isBad = lowerIsBetter ? v > 0 : v < 0;
            const widthPct = r.value == null ? 0 : (Math.abs(v) / max) * 100;
            const valColor =
              r.value == null ? "text-dim" : isGood ? "text-positive" : isBad ? "text-negative" : "";

            return (
              <tr key={r.driver_code} className="border-b border-line last:border-b-0">
                <td className="px-3 py-1.5 text-dim">{idx + 1}</td>
                <td className="px-3 py-1.5">
                  <Link
                    href={`/drivers/${season}/${r.driver_code}`}
                    className="text-accent hover:underline underline-offset-4"
                  >
                    {r.driver_code}
                  </Link>
                </td>
                <td className="px-3 py-1.5">{r.full_name}</td>
                <td className="px-3 py-1.5 text-muted">
                  <span
                    className="inline-block w-1 h-3 align-middle mr-2 rounded-sm"
                    style={{ background: `#${r.team_color || "555"}` }}
                  />
                  {r.team_name}
                </td>
                <td className={`px-3 py-1.5 text-right ${valColor}`}>
                  {r.value == null
                    ? "—"
                    : Math.abs(v) >= 1
                    ? fmt.signedSeconds(v, 2)
                    : fmt.signedSeconds(v, 3)}
                </td>
                <td className="px-3 py-1.5 text-right hidden md:table-cell text-dim">
                  {r.ci_lo == null || r.ci_hi == null
                    ? "—"
                    : fmt.ci(r.ci_lo, r.ci_hi)}
                </td>
                <td className="px-3 py-1.5 text-right text-dim">{r.n}</td>
                <td className="px-3 py-1.5">
                  <div className="h-1.5 bg-surface-2 rounded-sm overflow-hidden">
                    <div
                      className={`h-full ${isGood ? "bg-positive" : isBad ? "bg-negative" : "bg-muted"}`}
                      style={{
                        width: `${widthPct}%`,
                        backgroundColor: isGood
                          ? "var(--color-positive)"
                          : isBad
                          ? "var(--color-negative)"
                          : "var(--color-text-muted)",
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
