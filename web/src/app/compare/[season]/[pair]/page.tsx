import Link from "next/link";
import { notFound } from "next/navigation";

import { getDriver, type DriverProfile, type MetricBlock } from "@/lib/api";
import { deltaTone, fmt } from "@/lib/format";

export const dynamic = "force-dynamic";
export const revalidate = 0;

interface PageProps {
  params: Promise<{ season: string; pair: string }>;
}

export default async function ComparePage({ params }: PageProps) {
  const { season: seasonRaw, pair } = await params;
  const season = Number(seasonRaw);

  const codes = pair.split("-vs-").map((s) => s.trim().toUpperCase()).filter(Boolean);
  if (codes.length !== 2 || !Number.isFinite(season)) notFound();

  const [a, b] = await Promise.all([
    getDriver(season, codes[0]).catch(() => null),
    getDriver(season, codes[1]).catch(() => null),
  ]);
  if (!a || !b) notFound();

  return (
    <main className="min-h-dvh px-6 py-12 max-w-6xl mx-auto">
      <header className="space-y-3">
        <div className="flex items-baseline gap-3 font-mono text-xs uppercase tracking-widest text-dim">
          <Link href="/" className="hover:text-accent underline-offset-4 hover:underline">
            pacelab
          </Link>
          <span className="text-line-2">/</span>
          <span className="text-muted">compare</span>
        </div>
        <h1 className="font-serif text-4xl md:text-5xl leading-tight">
          {a.driver.full_name} vs {b.driver.full_name}
        </h1>
        <p className="text-muted max-w-2xl leading-relaxed">
          Side-by-side {season} season profiles. Note: each driver&apos;s metric is computed
          against <em>their own teammate</em>, not against the other side of this
          comparison. Two negative values both mean &quot;faster than my teammate&quot; — and
          the more negative number wins the head-to-head intent.
        </p>
      </header>

      <div className="mt-10 grid grid-cols-1 md:grid-cols-2 gap-3">
        <DriverStrip profile={a} />
        <DriverStrip profile={b} />
      </div>

      <ComparisonBlock title="Qualifying pace vs teammate" lowerIsBetter
        a={a.headline_metrics.qualifying_pace_vs_teammate_s}
        b={b.headline_metrics.qualifying_pace_vs_teammate_s}
        format="signed-seconds"
      />
      <ComparisonBlock title="Race pace vs teammate" lowerIsBetter
        a={a.headline_metrics.race_pace_vs_teammate_s}
        b={b.headline_metrics.race_pace_vs_teammate_s}
        format="signed-seconds"
      />
      <ComparisonBlock title="Stint consistency (residual SD)" lowerIsBetter
        a={a.headline_metrics.stint_consistency_residual_sd_s}
        b={b.headline_metrics.stint_consistency_residual_sd_s}
        format="seconds"
      />
      <ComparisonBlock title="Consistency Δ vs teammate" lowerIsBetter
        a={a.headline_metrics.consistency_delta_vs_teammate_s}
        b={b.headline_metrics.consistency_delta_vs_teammate_s}
        format="signed-seconds"
      />
      <ComparisonBlock title="Positions gained / race" lowerIsBetter={false}
        a={a.headline_metrics.positions_gained_per_race}
        b={b.headline_metrics.positions_gained_per_race}
        format="signed-positions"
      />

      <CompoundComparison
        title="Tyre management by compound (Δ slope vs teammate, s/lap)"
        a={a.tyre_management.by_compound_deg_delta_s_per_lap}
        b={b.tyre_management.by_compound_deg_delta_s_per_lap}
        leftCode={a.driver.code}
        rightCode={b.driver.code}
      />

      <footer className="mt-16 pt-6 border-t border-line font-mono text-xs text-dim">
        <p>
          <span className="text-muted">link tip:</span> /compare/{season}/X-vs-Y for any pair.
        </p>
      </footer>
    </main>
  );
}

function DriverStrip({ profile }: { profile: DriverProfile }) {
  const teamHex = profile.driver.team_color ? `#${profile.driver.team_color}` : "#555";
  return (
    <Link
      href={`/drivers/${profile.driver.season}/${profile.driver.code}`}
      className="flex items-center gap-4 border border-line rounded-md bg-surface p-4 hover:bg-surface-2"
    >
      <div className="w-1 self-stretch rounded-sm" style={{ background: teamHex }} />
      <div className="flex-1 min-w-0">
        <div className="font-mono text-[10px] uppercase tracking-widest text-dim">
          {profile.driver.team_name}
        </div>
        <div className="font-serif text-2xl">{profile.driver.full_name}</div>
        <div className="font-mono text-[11px] text-muted">
          teammates: {profile.driver.teammates.join(", ") || "—"}
        </div>
      </div>
      <div className="font-mono text-3xl text-muted">{profile.driver.code}</div>
    </Link>
  );
}

function ComparisonBlock({
  title,
  a,
  b,
  lowerIsBetter,
  format,
}: {
  title: string;
  a: MetricBlock;
  b: MetricBlock;
  lowerIsBetter: boolean;
  format: "signed-seconds" | "seconds" | "signed-positions";
}) {
  const fmtValue = (v: number) =>
    format === "signed-seconds"
      ? fmt.signedSeconds(v)
      : format === "seconds"
      ? fmt.seconds(v)
      : fmt.positions(v);

  const toneA = deltaTone(a.value, lowerIsBetter);
  const toneB = deltaTone(b.value, lowerIsBetter);
  const cls = (t: "positive" | "negative" | "neutral") =>
    t === "positive" ? "text-positive" : t === "negative" ? "text-negative" : "";

  // Winner determination
  let winner: "a" | "b" | "tie" = "tie";
  if (Number.isFinite(a.value) && Number.isFinite(b.value)) {
    winner = lowerIsBetter
      ? a.value < b.value
        ? "a"
        : a.value > b.value
        ? "b"
        : "tie"
      : a.value > b.value
      ? "a"
      : a.value < b.value
      ? "b"
      : "tie";
  }

  // CI overlap check — if intervals overlap meaningfully, flag as inconclusive
  const ciOverlap =
    Number.isFinite(a.ci_lo) && Number.isFinite(a.ci_hi) &&
    Number.isFinite(b.ci_lo) && Number.isFinite(b.ci_hi) &&
    !(a.ci_hi < b.ci_lo || b.ci_hi < a.ci_lo);

  return (
    <section className="mt-8 border border-line rounded-md bg-surface overflow-hidden">
      <header className="border-b border-line px-5 py-3 flex items-baseline gap-3">
        <h3 className="font-mono text-xs uppercase tracking-widest text-muted">{title}</h3>
        {ciOverlap && (
          <span className="ml-auto font-mono text-[10px] text-warning uppercase">
            CIs overlap — call inconclusive
          </span>
        )}
      </header>
      <div className="grid grid-cols-2 divide-x divide-line">
        <CompareCell
          value={fmtValue(a.value)}
          ci={`[${a.ci_lo?.toFixed?.(3) ?? "?"}, ${a.ci_hi?.toFixed?.(3) ?? "?"}]`}
          n={a.n}
          win={winner === "a"}
          toneClass={cls(toneA)}
        />
        <CompareCell
          value={fmtValue(b.value)}
          ci={`[${b.ci_lo?.toFixed?.(3) ?? "?"}, ${b.ci_hi?.toFixed?.(3) ?? "?"}]`}
          n={b.n}
          win={winner === "b"}
          toneClass={cls(toneB)}
        />
      </div>
      <div className="border-t border-line px-5 py-3 text-[11px] text-muted font-mono">
        {a.definition}
      </div>
    </section>
  );
}

function CompareCell({
  value,
  ci,
  n,
  win,
  toneClass,
}: {
  value: string;
  ci: string;
  n: number;
  win: boolean;
  toneClass: string;
}) {
  return (
    <div className={"px-5 py-4 " + (win ? "bg-surface-2" : "")}>
      <div className="flex items-baseline gap-3">
        <span className={`font-mono text-3xl ${toneClass}`}>{value}</span>
        {win && <span className="font-mono text-[10px] uppercase tracking-wider text-accent">winner</span>}
      </div>
      <div className="font-mono text-[10px] text-dim mt-1">
        95% CI {ci} · n = {n}
      </div>
    </div>
  );
}

function CompoundComparison({
  title,
  a,
  b,
  leftCode,
  rightCode,
}: {
  title: string;
  a: Record<string, MetricBlock>;
  b: Record<string, MetricBlock>;
  leftCode: string;
  rightCode: string;
}) {
  const compounds = Array.from(new Set([...Object.keys(a), ...Object.keys(b)])).sort();
  if (compounds.length === 0) return null;
  return (
    <section className="mt-8 border border-line rounded-md bg-surface overflow-hidden">
      <header className="border-b border-line px-5 py-3">
        <h3 className="font-mono text-xs uppercase tracking-widest text-muted">{title}</h3>
      </header>
      <table className="w-full font-mono text-xs">
        <thead className="text-dim">
          <tr className="border-b border-line">
            <th className="text-left px-5 py-2 font-normal">compound</th>
            <th className="text-right px-5 py-2 font-normal">{leftCode}</th>
            <th className="text-right px-5 py-2 font-normal">{rightCode}</th>
          </tr>
        </thead>
        <tbody>
          {compounds.map((c) => {
            const av = a[c]?.value;
            const bv = b[c]?.value;
            const aN = a[c]?.n;
            const bN = b[c]?.n;
            return (
              <tr key={c} className="border-b border-line last:border-b-0">
                <td className="px-5 py-2 text-muted">{c}</td>
                <td className={`px-5 py-2 text-right ${av != null && av < 0 ? "text-positive" : av != null && av > 0 ? "text-negative" : ""}`}>
                  {av != null ? `${fmt.signedSPerLap(av)} (n=${aN})` : "—"}
                </td>
                <td className={`px-5 py-2 text-right ${bv != null && bv < 0 ? "text-positive" : bv != null && bv > 0 ? "text-negative" : ""}`}>
                  {bv != null ? `${fmt.signedSPerLap(bv)} (n=${bN})` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
