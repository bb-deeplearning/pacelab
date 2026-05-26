import Link from "next/link";
import { notFound } from "next/navigation";

import { getCareer, type CareerSeasonEntry, type DriverCareer } from "@/lib/api";
import { fmt } from "@/lib/format";

export const dynamic = "force-dynamic";
export const revalidate = 0;

interface PageProps {
  params: Promise<{ code: string }>;
}

const METRIC_DISPLAY: Array<{
  id: keyof CareerSeasonEntry["metrics"];
  label: string;
  lowerIsBetter: boolean;
  format: "signed-seconds" | "seconds" | "positions";
}> = [
  { id: "qualifying_pace_vs_teammate_s", label: "Qualifying pace vs teammate", lowerIsBetter: true,  format: "signed-seconds" },
  { id: "race_pace_vs_teammate_s",       label: "Race pace vs teammate",      lowerIsBetter: true,  format: "signed-seconds" },
  { id: "stint_consistency_residual_sd_s",label: "Stint consistency (SD)",     lowerIsBetter: true,  format: "seconds" },
  { id: "consistency_delta_vs_teammate_s",label: "Consistency Δ vs teammate",  lowerIsBetter: true,  format: "signed-seconds" },
  { id: "positions_gained_per_race",     label: "Positions gained / race",     lowerIsBetter: false, format: "positions" },
];

export default async function CareerPage({ params }: PageProps) {
  const { code: codeRaw } = await params;
  const code = codeRaw.toUpperCase();
  const career = await getCareer(code);
  if (!career) notFound();

  return (
    <main className="min-h-dvh px-6 py-12 max-w-6xl mx-auto">
      <header className="space-y-3">
        <div className="flex items-baseline gap-3 font-mono text-xs uppercase tracking-widest text-dim">
          <Link href="/" className="hover:text-accent underline-offset-4 hover:underline">
            pacelab
          </Link>
          <span className="text-line-2">/</span>
          <Link href="/alltime" className="hover:text-accent underline-offset-4 hover:underline">
            all-time
          </Link>
          <span className="text-line-2">/</span>
          <span className="text-muted">{career.driver_code}</span>
        </div>
        <h1 className="font-serif text-4xl md:text-5xl leading-tight">
          {career.full_name} — career arc
        </h1>
        <p className="text-muted leading-relaxed">
          Each row is a season profile. The metric is the teammate-paired delta for that
          season (so the comparator changes when the driver swaps teams). Hover a season
          number to see the linked profile.
        </p>
      </header>

      <section className="mt-10">
        <TeamTimeline career={career} />
      </section>

      <section className="mt-10">
        <h2 className="font-serif text-2xl border-b border-line pb-2 mb-4">Per-season metrics</h2>
        <div className="overflow-x-auto border border-line rounded-md bg-surface">
          <table className="w-full font-mono text-xs min-w-[800px]">
            <thead className="text-dim">
              <tr className="border-b border-line">
                <th className="text-left px-3 py-2 font-normal">metric</th>
                {career.seasons.map((s) => (
                  <th key={s.season} className="text-right px-3 py-2 font-normal">
                    <Link
                      href={`/drivers/${s.season}/${career.driver_code}`}
                      className="text-accent hover:underline underline-offset-4"
                    >
                      {s.season}
                    </Link>
                  </th>
                ))}
              </tr>
              <tr className="border-b border-line text-dim">
                <th className="text-left px-3 py-2 font-normal text-[10px] uppercase tracking-wider">team</th>
                {career.seasons.map((s) => (
                  <th key={s.season} className="text-right px-3 py-2 font-normal">
                    <span
                      className="inline-block w-1 h-3 align-middle mr-1 rounded-sm"
                      style={{ background: `#${s.team_color || "555"}` }}
                    />
                    {s.team_name.replace("Racing", "").replace("F1 Team", "").trim()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {METRIC_DISPLAY.map((m) => (
                <tr key={m.id} className="border-b border-line last:border-b-0">
                  <td className="px-3 py-2 text-muted whitespace-nowrap">{m.label}</td>
                  {career.seasons.map((s) => {
                    const v = s.metrics[m.id]?.value;
                    const n = s.metrics[m.id]?.n ?? 0;
                    const ciLo = s.metrics[m.id]?.ci_lo;
                    const ciHi = s.metrics[m.id]?.ci_hi;
                    const valid = typeof v === "number" && Number.isFinite(v);
                    const isGood = valid && (m.lowerIsBetter ? v < 0 : v > 0);
                    const isBad = valid && (m.lowerIsBetter ? v > 0 : v < 0);
                    const tone = isGood
                      ? "text-positive"
                      : isBad
                      ? "text-negative"
                      : "";
                    const formatted =
                      v == null || !Number.isFinite(v)
                        ? "—"
                        : m.format === "signed-seconds"
                        ? fmt.signedSeconds(v)
                        : m.format === "seconds"
                        ? fmt.seconds(v)
                        : fmt.positions(v);
                    return (
                      <td
                        key={s.season}
                        className={`px-3 py-2 text-right ${tone}`}
                        title={
                          ciLo != null && ciHi != null
                            ? `n=${n} CI=[${ciLo.toFixed(3)}, ${ciHi.toFixed(3)}]`
                            : `n=${n}`
                        }
                      >
                        {formatted}
                        <div className="text-[9px] text-dim font-mono">n={n}</div>
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className="border-b border-line">
                <td className="px-3 py-2 text-muted whitespace-nowrap">Teammates that season</td>
                {career.seasons.map((s) => (
                  <td key={s.season} className="px-3 py-2 text-right text-[10px] text-dim">
                    {s.teammates.join(", ") || "—"}
                  </td>
                ))}
              </tr>
              <tr>
                <td className="px-3 py-2 text-muted whitespace-nowrap">DNFs / starts</td>
                {career.seasons.map((s) => (
                  <td key={s.season} className="px-3 py-2 text-right text-dim">
                    {s.reliability?.dnfs ?? "—"} / {s.reliability?.races_started ?? "—"}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <footer className="mt-16 pt-6 border-t border-line font-mono text-xs text-dim">
        <p>
          {career.seasons.length} season(s) ingested.
          {" "}
          <Link href="/alltime" className="hover:text-accent underline-offset-4 hover:underline">
            ← all-time leaderboards
          </Link>
        </p>
      </footer>
    </main>
  );
}

function TeamTimeline({ career }: { career: DriverCareer }) {
  if (career.seasons.length === 0) return null;
  return (
    <div className="border border-line rounded-md bg-surface p-4">
      <div className="font-mono text-[10px] uppercase tracking-widest text-dim mb-3">
        team timeline
      </div>
      <div className="flex flex-wrap gap-2">
        {career.seasons.map((s) => (
          <div
            key={s.season}
            className="flex items-center gap-2 border border-line rounded-sm px-2 py-1 bg-surface-2"
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
    </div>
  );
}
