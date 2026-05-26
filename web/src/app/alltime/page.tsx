import Link from "next/link";
import { notFound } from "next/navigation";

import { getAlltime, type AlltimeEntry } from "@/lib/api";
import { fmt } from "@/lib/format";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function AllTimePage() {
  const data = await getAlltime();
  if (!data) notFound();

  return (
    <main className="min-h-dvh px-6 py-12 max-w-6xl mx-auto">
      <header className="space-y-3">
        <div className="flex items-baseline gap-3 font-mono text-xs uppercase tracking-widest text-dim">
          <Link href="/" className="hover:text-accent underline-offset-4 hover:underline">
            pacelab
          </Link>
          <span className="text-line-2">/</span>
          <span className="text-muted">all-time</span>
        </div>
        <h1 className="font-serif text-4xl md:text-5xl leading-tight">
          All-time, across every season ingested.
        </h1>
        <p className="text-muted max-w-2xl leading-relaxed">
          Per-season point estimates are combined into a single value with an{" "}
          <strong className="text-text">inverse-variance-weighted mean</strong>: seasons
          with tighter 95% CIs contribute more to the final number, seasons with wider
          CIs contribute less. The reported CI is the pooled standard error × 1.96.
        </p>
        <p className="text-muted max-w-2xl leading-relaxed">
          Every entry shows the seasons it draws from and the teams the driver raced for
          during those seasons. The comparison is still <strong className="text-text">teammate-paired</strong>{" "}
          on each side — so VER&apos;s number is &ldquo;how much faster than his teammate-of-the-day
          across 6 seasons&rdquo;, not a global ranking.
        </p>
      </header>

      {data.metrics.map((m) => {
        const rows = data.leaderboards[m.id] ?? [];
        return (
          <section key={m.id} className="mt-12">
            <div className="border-b border-line pb-2 mb-4 flex items-baseline gap-3 flex-wrap">
              <h2 className="font-serif text-2xl">{m.label}</h2>
              <span className="font-mono text-xs text-muted">
                {m.lower_is_better ? "lower is better" : "higher is better"} ·
                inverse-variance-weighted across seasons
              </span>
            </div>
            <AlltimeTable rows={rows} lowerIsBetter={m.lower_is_better} />
          </section>
        );
      })}

      <footer className="mt-16 pt-6 border-t border-line font-mono text-xs text-dim">
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

function AlltimeTable({
  rows,
  lowerIsBetter,
}: {
  rows: AlltimeEntry[];
  lowerIsBetter: boolean;
}) {
  if (rows.length === 0) {
    return <p className="font-mono text-xs text-dim">no data yet.</p>;
  }
  const max = Math.max(...rows.map((r) => (r.value == null ? 0 : Math.abs(r.value))), 0.01);

  return (
    <div className="border border-line rounded-md overflow-hidden bg-surface">
      <table className="w-full font-mono text-xs">
        <thead className="text-dim">
          <tr className="border-b border-line">
            <th className="text-left px-3 py-2 font-normal w-10">#</th>
            <th className="text-left px-3 py-2 font-normal w-16">code</th>
            <th className="text-left px-3 py-2 font-normal">driver</th>
            <th className="text-left px-3 py-2 font-normal hidden md:table-cell">latest team</th>
            <th className="text-right px-3 py-2 font-normal">value</th>
            <th className="text-right px-3 py-2 font-normal hidden md:table-cell">95% CI</th>
            <th className="text-right px-3 py-2 font-normal w-12">sns</th>
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
            const valColor = r.value == null
              ? "text-dim"
              : isGood ? "text-positive" : isBad ? "text-negative" : "";
            return (
              <tr key={r.driver_code} className="border-b border-line last:border-b-0">
                <td className="px-3 py-1.5 text-dim">{idx + 1}</td>
                <td className="px-3 py-1.5">
                  <Link
                    href={`/careers/${r.driver_code}`}
                    className="text-accent hover:underline underline-offset-4"
                  >
                    {r.driver_code}
                  </Link>
                </td>
                <td className="px-3 py-1.5">{r.full_name}</td>
                <td className="px-3 py-1.5 text-muted hidden md:table-cell">
                  <span
                    className="inline-block w-1 h-3 align-middle mr-2 rounded-sm"
                    style={{ background: `#${r.latest_team_color || "555"}` }}
                  />
                  {r.latest_team}
                </td>
                <td className={`px-3 py-1.5 text-right ${valColor}`}>
                  {r.value == null
                    ? "—"
                    : Math.abs(v) >= 1
                    ? fmt.signedSeconds(v, 2)
                    : fmt.signedSeconds(v, 3)}
                </td>
                <td className="px-3 py-1.5 text-right hidden md:table-cell text-dim">
                  {r.ci_lo == null || r.ci_hi == null ? "—" : fmt.ci(r.ci_lo, r.ci_hi)}
                </td>
                <td className="px-3 py-1.5 text-right text-dim" title={r.seasons.join(", ")}>
                  {r.seasons_count}
                </td>
                <td className="px-3 py-1.5 text-right text-dim">{r.n}</td>
                <td className="px-3 py-1.5">
                  <div className="h-1.5 bg-surface-2 rounded-sm overflow-hidden">
                    <div
                      className="h-full"
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
