import Link from "next/link";

import { getIndex } from "@/lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function Home() {
  let index;
  try {
    index = await getIndex();
  } catch (err) {
    return (
      <main className="min-h-dvh px-6 py-12 max-w-5xl mx-auto">
        <Header />
        <div className="mt-12 border border-line-2 rounded-md p-6 bg-surface">
          <p className="font-mono text-sm text-warning">metrics index not built yet.</p>
          <p className="font-mono text-sm text-muted mt-2">
            run: <span className="text-accent">pacelab metrics build</span>
          </p>
          <p className="font-mono text-xs text-dim mt-4">
            {(err as Error).message}
          </p>
        </div>
      </main>
    );
  }

  const seasons = [...index.seasons].sort((a, b) => b - a);
  const driversBySeason = new Map<number, typeof index.drivers>();
  for (const d of index.drivers) {
    const list = driversBySeason.get(d.season) ?? [];
    list.push(d);
    driversBySeason.set(d.season, list);
  }

  return (
    <main className="min-h-dvh px-6 py-12 max-w-6xl mx-auto">
      <Header />

      {seasons.map((season) => {
        const list = (driversBySeason.get(season) ?? []).slice().sort((a, b) => {
          if (a.team_name === b.team_name) return a.full_name.localeCompare(b.full_name);
          return a.team_name.localeCompare(b.team_name);
        });

        // Group by team for visual structure.
        const byTeam = new Map<string, typeof list>();
        for (const d of list) {
          const t = byTeam.get(d.team_name) ?? [];
          t.push(d);
          byTeam.set(d.team_name, t);
        }

        return (
          <section key={season} className="mt-16">
            <div className="flex items-baseline gap-4 border-b border-line pb-2 mb-6">
              <h2 className="font-mono text-sm text-muted">SEASON</h2>
              <h2 className="font-serif text-3xl">{season}</h2>
            <div className="ml-auto flex items-center gap-3">
              <Link
                href={`/seasons/${season}`}
                className="font-mono text-xs px-3 py-1 border border-line rounded-sm text-muted hover:border-accent hover:text-accent transition-colors"
              >
                view {season} leaderboards →
              </Link>
              <span className="font-mono text-xs text-dim">
                {list.length} drivers
              </span>
            </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {[...byTeam.entries()]
                .sort((a, b) => a[0].localeCompare(b[0]))
                .flatMap(([team, drivers]) =>
                  drivers.map((d) => (
                    <div
                      key={`${season}-${d.driver_code}`}
                      className="group flex items-stretch gap-4 border border-line rounded-md p-4 bg-surface hover:bg-surface-2 hover:border-line-2 transition-colors"
                    >
                      <div
                        className="w-1 rounded-sm"
                        style={{ background: `#${d.team_color || "555"}` }}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="font-mono text-[10px] text-dim uppercase tracking-wider">
                          {team}
                        </div>
                        <Link
                          href={`/drivers/${season}/${d.driver_code}`}
                          className="font-serif text-xl truncate block hover:underline underline-offset-4"
                        >
                          {d.full_name}
                        </Link>
                        <Link
                          href={`/careers/${d.driver_code}`}
                          className="font-mono text-[10px] text-dim hover:text-accent underline-offset-4 hover:underline"
                        >
                          career →
                        </Link>
                      </div>
                      <Link
                        href={`/drivers/${season}/${d.driver_code}`}
                        className="font-mono text-2xl text-muted group-hover:text-accent transition-colors self-center"
                      >
                        {d.driver_code}
                      </Link>
                    </div>
                  ))
                )}
            </div>
          </section>
        );
      })}

      <Footer generatedAt={index.generated_at_utc} />
    </main>
  );
}

function Header() {
  return (
    <header className="space-y-4">
      <div className="flex items-baseline gap-3 font-mono text-xs uppercase tracking-widest text-dim">
        <span>pacelab</span>
        <span className="text-line-2">/</span>
        <span className="text-muted">evidence-based F1 driver scouting</span>
      </div>
      <h1 className="font-serif text-5xl md:text-6xl leading-tight">
        Driver profiles, with the maths.
      </h1>
      <p className="text-muted max-w-2xl leading-relaxed">
        Every number on every profile page carries a derivation, a sample size, and a 95%
        confidence interval. Wherever possible, the comparison is teammate-paired so the
        car-driver collinearity is broken. Punditry is fine; this site is not punditry.
      </p>
      <p className="font-mono text-xs text-muted pt-1">
        compare any two drivers in a season: <span className="text-dim">/compare/2024/VER-vs-HAM</span>
      </p>
      <div className="flex flex-wrap gap-x-6 gap-y-2 font-mono text-xs text-muted pt-2">
        <Link
          href="/alltime"
          className="text-accent hover:underline underline-offset-4"
        >
          → all-time leaderboards
        </Link>
        <Link
          href="/bayes"
          className="text-accent hover:underline underline-offset-4"
        >
          → bayesian skill posterior
        </Link>
        <a
          href="https://github.com/bb-deeplearning/pacelab"
          className="hover:text-accent underline-offset-4 hover:underline"
        >
          github.com/bb-deeplearning/pacelab
        </a>
        <Link
          href="/methodology"
          className="hover:text-accent underline-offset-4 hover:underline"
        >
          methodology
        </Link>
      </div>
    </header>
  );
}

function Footer({ generatedAt }: { generatedAt: string }) {
  return (
    <footer className="mt-24 pt-6 border-t border-line font-mono text-xs text-dim space-y-1">
      <p>
        data generated {new Date(generatedAt).toISOString().replace("T", " ").slice(0, 19)} UTC.
        sourced via{" "}
        <a
          href="https://github.com/theOehrly/Fast-F1"
          className="hover:text-accent underline-offset-4 hover:underline"
        >
          FastF1
        </a>
        .
      </p>
      <p>
        pacelab is unofficial. Formula 1, F1, GRAND PRIX and related marks are trade marks
        of Formula One Licensing B.V.
      </p>
    </footer>
  );
}
