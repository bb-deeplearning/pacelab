import Link from "next/link";
import { notFound } from "next/navigation";

import { getDriver, type DriverProfile, type MetricBlock } from "@/lib/api";
import { deltaTone, fmt } from "@/lib/format";

export const dynamic = "force-dynamic";
export const revalidate = 0;

interface PageProps {
  params: Promise<{ season: string; code: string }>;
}

export default async function DriverPage({ params }: PageProps) {
  const { season: seasonRaw, code: codeRaw } = await params;
  const season = Number(seasonRaw);
  const code = codeRaw.toUpperCase();

  let profile;
  try {
    profile = await getDriver(season, code);
  } catch {
    notFound();
  }

  const teamHex = profile.driver.team_color ? `#${profile.driver.team_color}` : "#555";

  return (
    <main className="min-h-dvh">
      {/* Identity strip */}
      <section
        className="border-b border-line-2 px-6 pt-10 pb-10 relative grid-bg"
        style={{
          background: `radial-gradient(900px circle at 80% 0%, ${teamHex}25, transparent 60%)`,
        }}
      >
        <div className="max-w-6xl mx-auto">
          <Link
            href="/"
            className="font-mono text-xs text-muted hover:text-accent underline-offset-4 hover:underline"
          >
            ← all drivers
          </Link>

          <div className="mt-6 flex flex-wrap items-end gap-6 md:gap-12">
            <div
              className="font-mono text-[9rem] leading-none tracking-tighter"
              style={{ color: teamHex }}
            >
              {profile.driver.code}
            </div>
            <div className="flex-1 min-w-[260px]">
              <h1 className="font-serif text-4xl md:text-5xl leading-tight">
                {profile.driver.full_name}
              </h1>
              <p className="mt-2 font-mono text-sm uppercase tracking-wider text-muted">
                {profile.driver.team_name} · {season}
              </p>
              {profile.driver.teammates.length > 0 && (
                <p className="mt-1 font-mono text-xs text-dim">
                  teammates this season: {profile.driver.teammates.join(", ")}
                </p>
              )}
            </div>
            <RecencyStrip last={profile.last_race} />
          </div>
        </div>
      </section>

      <div className="max-w-6xl mx-auto px-6 py-10 space-y-12">
        {/* Headline metrics */}
        <section>
          <SectionHeader title="Headline metrics" kicker="five numbers, teammate-paired" />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <MetricCard
              label="Qualifying pace vs teammate"
              unit="seconds per lap"
              block={profile.headline_metrics.qualifying_pace_vs_teammate_s}
              format="signed-seconds"
            />
            <MetricCard
              label="Race pace vs teammate"
              unit="seconds per lap, α-aligned"
              block={profile.headline_metrics.race_pace_vs_teammate_s}
              format="signed-seconds"
            />
            <MetricCard
              label="Stint consistency"
              unit="seconds, residual SD"
              block={profile.headline_metrics.stint_consistency_residual_sd_s}
              format="seconds"
            />
            <MetricCard
              label="Consistency Δ vs teammate"
              unit="seconds, lower = more consistent"
              block={profile.headline_metrics.consistency_delta_vs_teammate_s}
              format="signed-seconds"
            />
            <MetricCard
              label="Positions gained / race"
              unit="grid − finish"
              block={profile.headline_metrics.positions_gained_per_race}
              format="signed-positions"
            />
            <ReliabilityCard
              dnfs={profile.reliability.dnfs}
              races={profile.reliability.races_started}
              rate={profile.reliability.dnf_rate}
            />
          </div>
        </section>

        {/* Tyre management */}
        <section>
          <SectionHeader
            title="Tyre management"
            kicker="degradation slope Δ vs teammate, per compound"
          />
          {Object.keys(profile.tyre_management.by_compound_deg_delta_s_per_lap).length === 0 ? (
            <p className="font-mono text-xs text-dim">No matched stint pairs in this season yet.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {Object.entries(profile.tyre_management.by_compound_deg_delta_s_per_lap).map(
                ([compound, block]) => (
                  <MetricCard
                    key={compound}
                    label={compound}
                    unit="seconds per lap of stint age"
                    block={block}
                    format="signed-s-per-lap"
                  />
                )
              )}
            </div>
          )}
        </section>

        {/* Wet vs dry */}
        <section>
          <SectionHeader title="Wet vs dry" kicker="conditions-conditioned pace deltas" />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <MetricCard
              label="Wet pace vs teammate"
              unit="seconds per lap"
              block={profile.wet_vs_dry.wet_pace_vs_teammate_s}
              format="signed-seconds"
            />
            <MetricCard
              label="Dry pace vs teammate"
              unit="seconds per lap"
              block={profile.wet_vs_dry.dry_pace_vs_teammate_s}
              format="signed-seconds"
            />
            <MetricCard
              label="Wet − Dry (skill in conditions)"
              unit="seconds per lap"
              block={profile.wet_vs_dry.wet_minus_dry_s}
              format="signed-seconds"
            />
          </div>
        </section>

        {/* Track-type breakdown */}
        {profile.track_type &&
          Object.keys(profile.track_type.pace_vs_teammate_by_archetype_s).length > 0 && (
            <section>
              <SectionHeader
                title="By circuit archetype"
                kicker="pace delta vs teammate, partitioned by track type"
              />
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {Object.entries(profile.track_type.pace_vs_teammate_by_archetype_s).map(
                  ([arch, block]) => (
                    <MetricCard
                      key={arch}
                      label={block.label}
                      unit="seconds per lap"
                      block={block}
                      format="signed-seconds"
                    />
                  )
                )}
              </div>
            </section>
          )}

        {/* Style (telemetry-derived) */}
        {profile.style && hasFiniteStyle(profile.style) && (
          <section>
            <SectionHeader
              title="Driving style fingerprint"
              kicker="telemetry-derived deltas vs teammate (phase 2 — partial coverage)"
            />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <MetricCard
                label="Throttle smoothness"
                unit={profile.style.throttle_smoothness_delta.unit}
                block={profile.style.throttle_smoothness_delta}
                format="signed-seconds"
              />
              <MetricCard
                label="Brake dwell"
                unit={profile.style.brake_dwell_delta_s.unit}
                block={profile.style.brake_dwell_delta_s}
                format="signed-seconds"
              />
              <MetricCard
                label="Full-throttle fraction"
                unit={profile.style.full_throttle_fraction_delta.unit}
                block={profile.style.full_throttle_fraction_delta}
                format="signed-seconds"
              />
            </div>
          </section>
        )}

        {/* Per-session tables */}
        <section>
          <SectionHeader
            title="Per-session results"
            kicker="every comparison this season is auditable"
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <QualSessionTable
              rows={profile.per_session.qualifying}
              code={profile.driver.code}
            />
            <RaceResultsTable rows={profile.per_session.race_results} />
          </div>
        </section>
      </div>

      <footer className="border-t border-line max-w-6xl mx-auto px-6 py-6 mt-12 font-mono text-xs text-dim">
        <p>
          generated {new Date(profile.generated_at_utc).toISOString().replace("T", " ").slice(0, 19)} UTC.
          data via{" "}
          <a
            href="https://github.com/theOehrly/Fast-F1"
            className="hover:text-accent underline-offset-4 hover:underline"
          >
            FastF1
          </a>{" "}
          ·{" "}
          <a
            href="https://github.com/bb-deeplearning/pacelab/blob/main/docs/methodology.md"
            className="hover:text-accent underline-offset-4 hover:underline"
          >
            methodology
          </a>
        </p>
      </footer>
    </main>
  );
}

function hasFiniteStyle(
  style: NonNullable<DriverProfile["style"]>
): boolean {
  return (
    Number.isFinite(style.throttle_smoothness_delta.value) ||
    Number.isFinite(style.brake_dwell_delta_s.value) ||
    Number.isFinite(style.full_throttle_fraction_delta.value)
  );
}

function SectionHeader({ title, kicker }: { title: string; kicker?: string }) {
  return (
    <div className="mb-5 flex flex-wrap items-baseline gap-4 border-b border-line pb-2">
      <h2 className="font-serif text-2xl">{title}</h2>
      {kicker && <span className="font-mono text-xs text-muted">{kicker}</span>}
    </div>
  );
}

function MetricCard({
  label,
  unit,
  block,
  format,
}: {
  label: string;
  unit?: string;
  block: MetricBlock;
  format: "signed-seconds" | "seconds" | "signed-s-per-lap" | "signed-positions";
}) {
  const tone = deltaTone(block.value, block.lower_is_better);
  const toneClass =
    tone === "positive" ? "text-positive" : tone === "negative" ? "text-negative" : "text-text";

  const valueText =
    format === "signed-seconds"
      ? fmt.signedSeconds(block.value)
      : format === "seconds"
      ? fmt.seconds(block.value)
      : format === "signed-s-per-lap"
      ? fmt.signedSPerLap(block.value)
      : fmt.positions(block.value);

  const ciText =
    format === "signed-positions"
      ? fmt.ci(block.ci_lo, block.ci_hi, 2, "")
      : format === "signed-s-per-lap"
      ? fmt.ci(block.ci_lo, block.ci_hi, 3, " s/lap")
      : fmt.ci(block.ci_lo, block.ci_hi);

  return (
    <article className="border border-line rounded-md bg-surface p-5 flex flex-col gap-4">
      <header>
        <div className="font-mono text-[10px] uppercase tracking-widest text-dim">{label}</div>
        {unit && <div className="font-mono text-[10px] text-dim mt-0.5">{unit}</div>}
      </header>

      <div className="flex items-baseline gap-3">
        <span className={`font-mono text-3xl ${toneClass}`}>{valueText}</span>
        {block.n < 4 && Number.isFinite(block.value) && (
          <span className="font-mono text-[10px] uppercase tracking-wider text-warning">
            low n
          </span>
        )}
      </div>

      <div className="font-mono text-[11px] text-muted leading-relaxed">
        <div>
          <span className="text-dim">95% CI:</span> {ciText}
        </div>
        <div>
          <span className="text-dim">sample size:</span> n = {block.n}
        </div>
      </div>

      <p className="text-[12px] text-muted leading-relaxed border-t border-line pt-3">
        {block.definition}
      </p>
    </article>
  );
}

function ReliabilityCard({ dnfs, races, rate }: { dnfs: number; races: number; rate: number }) {
  return (
    <article className="border border-line rounded-md bg-surface p-5 flex flex-col gap-4">
      <header>
        <div className="font-mono text-[10px] uppercase tracking-widest text-dim">Reliability</div>
        <div className="font-mono text-[10px] text-dim mt-0.5">races, DNFs, failure rate</div>
      </header>
      <div className="flex items-baseline gap-3">
        <span className="font-mono text-3xl">
          {dnfs}/{races}
        </span>
        <span className="font-mono text-sm text-muted">DNFs</span>
      </div>
      <div className="font-mono text-[11px] text-muted">
        DNF rate: {fmt.pct(rate)}
      </div>
      <p className="text-[12px] text-muted leading-relaxed border-t border-line pt-3">
        Race starts and retirements per FastF1 classified-position field. DNF includes
        retirements, DSQs, and non-starts.
      </p>
    </article>
  );
}

function RecencyStrip({
  last,
}: {
  last: {
    session_key: string;
    year: number;
    round: number;
    grid_position: number;
    finish_position: number;
    classified_position: string;
    dnf: boolean;
    positions_gained: number;
  } | null;
}) {
  if (!last) return null;
  return (
    <div className="border border-line-2 rounded-md bg-surface px-4 py-3 min-w-[200px]">
      <div className="font-mono text-[10px] uppercase tracking-widest text-dim">last race</div>
      <div className="font-mono text-sm mt-1">
        round {last.round} · grid {last.grid_position || "—"} → finish{" "}
        <span className={last.dnf ? "text-warning" : ""}>
          {last.dnf ? last.classified_position : last.finish_position}
        </span>
      </div>
      <div className={`font-mono text-xs mt-1 ${last.positions_gained > 0 ? "text-positive" : last.positions_gained < 0 ? "text-negative" : "text-muted"}`}>
        Δ {fmt.positions(last.positions_gained)} positions
      </div>
    </div>
  );
}

function QualSessionTable({
  rows,
  code,
}: {
  rows: Array<{
    session_key: string;
    teammate_code: string;
    best_time_s: number;
    teammate_best_s: number;
    delta_s: number;
    compared_segment: number;
  }>;
  code: string;
}) {
  return (
    <div className="border border-line rounded-md bg-surface overflow-hidden">
      <div className="border-b border-line px-4 py-2 font-mono text-xs text-muted">
        qualifying — per-session teammate delta
      </div>
      <table className="w-full font-mono text-xs">
        <thead className="text-dim">
          <tr className="border-b border-line">
            <th className="text-left px-4 py-2 font-normal">session</th>
            <th className="text-left px-4 py-2 font-normal">vs</th>
            <th className="text-right px-4 py-2 font-normal">{code}</th>
            <th className="text-right px-4 py-2 font-normal">team</th>
            <th className="text-right px-4 py-2 font-normal">Δ</th>
            <th className="text-right px-4 py-2 font-normal">seg</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-4 py-6 text-center text-dim">
                no comparable qualifying sessions yet
              </td>
            </tr>
          ) : (
            rows.map((r) => (
              <tr key={r.session_key} className="border-b border-line last:border-b-0">
                <td className="px-4 py-1.5 text-muted">{r.session_key}</td>
                <td className="px-4 py-1.5 text-muted">{r.teammate_code}</td>
                <td className="px-4 py-1.5 text-right">{fmt.seconds(r.best_time_s)}</td>
                <td className="px-4 py-1.5 text-right">{fmt.seconds(r.teammate_best_s)}</td>
                <td
                  className={`px-4 py-1.5 text-right ${r.delta_s < 0 ? "text-positive" : r.delta_s > 0 ? "text-negative" : ""}`}
                >
                  {fmt.signedSeconds(r.delta_s)}
                </td>
                <td className="px-4 py-1.5 text-right text-dim">Q{r.compared_segment}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function RaceResultsTable({
  rows,
}: {
  rows: Array<{
    session_key: string;
    round: number;
    grid_position: number;
    finish_position: number;
    classified_position: string;
    dnf: boolean;
    positions_gained: number;
  }>;
}) {
  return (
    <div className="border border-line rounded-md bg-surface overflow-hidden">
      <div className="border-b border-line px-4 py-2 font-mono text-xs text-muted">
        race results — grid, finish, delta
      </div>
      <table className="w-full font-mono text-xs">
        <thead className="text-dim">
          <tr className="border-b border-line">
            <th className="text-left px-4 py-2 font-normal">session</th>
            <th className="text-right px-4 py-2 font-normal">round</th>
            <th className="text-right px-4 py-2 font-normal">grid</th>
            <th className="text-right px-4 py-2 font-normal">finish</th>
            <th className="text-right px-4 py-2 font-normal">Δ pos</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={5} className="px-4 py-6 text-center text-dim">
                no race results yet
              </td>
            </tr>
          ) : (
            rows.map((r) => (
              <tr key={r.session_key} className="border-b border-line last:border-b-0">
                <td className="px-4 py-1.5 text-muted">{r.session_key}</td>
                <td className="px-4 py-1.5 text-right text-muted">{r.round}</td>
                <td className="px-4 py-1.5 text-right">{r.grid_position || "—"}</td>
                <td
                  className={`px-4 py-1.5 text-right ${r.dnf ? "text-warning" : ""}`}
                >
                  {r.dnf ? r.classified_position : r.finish_position}
                </td>
                <td
                  className={`px-4 py-1.5 text-right ${r.positions_gained > 0 ? "text-positive" : r.positions_gained < 0 ? "text-negative" : ""}`}
                >
                  {fmt.positions(r.positions_gained)}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
