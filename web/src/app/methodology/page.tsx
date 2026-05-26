import Link from "next/link";

export const dynamic = "force-static";

export default function MethodologyPage() {
  return (
    <main className="min-h-dvh px-6 py-12 max-w-3xl mx-auto">
      <header className="space-y-3">
        <div className="flex items-baseline gap-3 font-mono text-xs uppercase tracking-widest text-dim">
          <Link href="/" className="hover:text-accent underline-offset-4 hover:underline">
            pacelab
          </Link>
          <span className="text-line-2">/</span>
          <span className="text-muted">methodology</span>
        </div>
        <h1 className="font-serif text-4xl md:text-5xl leading-tight">
          How every number is computed.
        </h1>
        <p className="text-muted leading-relaxed">
          Read this before citing any pacelab metric. The full source is in
          <Link
            href="https://github.com/bb-deeplearning/pacelab/blob/main/docs/methodology.md"
            className="text-accent underline-offset-4 hover:underline ml-1"
          >
            docs/methodology.md
          </Link>
          ; this page is the short version.
        </p>
      </header>

      <article className="mt-10 space-y-10 leading-relaxed">
        <section>
          <h2 className="font-serif text-2xl mb-3">The identifiability problem</h2>
          <p>
            The naive regression is{" "}
            <code className="font-mono text-accent">
              lap_time = f(car, driver, track, weather, tyres, fuel, traffic, strategy, era, …)
            </code>
            . The car term and the driver term are essentially collinear for any given
            season because a driver drives that car and only that car. You cannot extract
            driver skill from lap time alone.
          </p>
          <p className="mt-3">The variation that breaks the collinearity, in order of signal strength:</p>
          <ol className="mt-3 ml-6 list-decimal space-y-2 text-muted">
            <li>
              <strong className="text-text">Teammate comparisons</strong> — same car, same
              garage, same engineers. This is the gold standard.
            </li>
            <li>
              <strong className="text-text">Driver transfers across teams</strong> —
              before-and-after for the same driver in different cars.
            </li>
            <li>
              <strong className="text-text">The teammate graph across seasons</strong> —
              chains of teammate pairs connect drivers who were never teammates directly,
              the same way chess Elo connects players through shared opponents.
            </li>
            <li>
              <strong className="text-text">High-variance conditions</strong> (wet, mixed,
              restarts) — the driver share of total variance rises sharply.
            </li>
          </ol>
          <p className="mt-3">
            Phase 1 (what&apos;s live now) uses (1) and (4). Phase 3 will add (2) and (3) via
            a hierarchical Bayesian model fit over the full teammate graph.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl mb-3">Lap-validity filter</h2>
          <p>A &ldquo;clean&rdquo; lap for any pace metric excludes:</p>
          <ul className="mt-3 ml-6 list-disc space-y-1 text-muted">
            <li>in-laps and out-laps</li>
            <li>the first lap on a fresh tyre (warm-up)</li>
            <li>deleted laps (track-limit penalties, etc.)</li>
            <li>any lap under a non-green track status (yellow, SC, VSC, red)</li>
            <li>any lap where FastF1&apos;s <code className="font-mono">IsAccurate</code> flag is false</li>
            <li>laps with no recorded lap time</li>
          </ul>
        </section>

        <section>
          <h2 className="font-serif text-2xl mb-3">Per-stint pace model</h2>
          <p>
            For each stint of ≥ 5 clean laps, we fit{" "}
            <code className="font-mono text-accent">
              lap_time = α + β · stint_age + γ · lap_number
            </code>{" "}
            with <code className="font-mono">γ = 0.030 s/lap</code> fixed (the well-known
            F1 fuel-burn coefficient). α is the underlying pace; β is the per-lap tyre
            degradation slope on that compound.
          </p>
          <p className="mt-3">
            The metrics derived from this fit are <strong>matched stint pairs</strong>: we
            compare driver and teammate stints on the same race, same compound, with at
            least 5 overlapping lap-number windows. The reported deltas are{" "}
            <code className="font-mono">α(driver) − α(teammate)</code> for race pace and{" "}
            <code className="font-mono">β(driver) − β(teammate)</code> for tyre management.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl mb-3">Why bootstrap CIs?</h2>
          <p>
            Most of these metrics are medians of small samples (15–25 sessions per
            season). Closed-form variance estimates for medians require strong
            assumptions about the underlying distribution. We bootstrap (10,000 resamples,
            percentile method) instead, which makes no distributional assumptions and is
            stable on samples that small.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl mb-3">What this site is not</h2>
          <ul className="ml-6 list-disc space-y-2 text-muted">
            <li>
              It is not a ranking. Headline metrics are not designed to support a scalar
              ordering of drivers, because skill is multi-dimensional.
            </li>
            <li>
              It is not a model of any individual team&apos;s car beyond what teammate
              comparisons reveal.
            </li>
            <li>
              It is not a prediction engine — phase 3 will produce probabilistic
              head-to-head comparisons but does not predict race outcomes.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="font-serif text-2xl mb-3">References</h2>
          <ul className="ml-6 list-disc space-y-2 text-muted">
            <li>
              Bell, A., Smith, J., Sampaio, C. (2016). <em>Formula for success: multilevel
              modelling of Formula One driver and constructor performance, 1950–2014.</em>{" "}
              Journal of Quantitative Analysis in Sports.
            </li>
            <li>
              Eichenberger, R., Stadelmann, D. (2009). <em>Who is the best Formula 1
              driver? An economic approach to evaluating talent.</em> Economic Analysis &
              Policy.
            </li>
            <li>
              Heilmeier, A. et al. (2018–2021). TUM race-strategy optimisation papers.
            </li>
            <li>
              Wieser, E. (2020). <em>The Formula One driver-versus-car problem.</em>
            </li>
          </ul>
        </section>

        <section>
          <h2 className="font-serif text-2xl mb-3">Found a bug?</h2>
          <p>
            Open an issue at{" "}
            <Link
              href="https://github.com/bb-deeplearning/pacelab/issues"
              className="text-accent underline-offset-4 hover:underline"
            >
              github.com/bb-deeplearning/pacelab/issues
            </Link>
            . The whole point of the site is that every number is checkable. If a metric
            is wrong, I want to know.
          </p>
        </section>
      </article>

      <footer className="mt-16 pt-6 border-t border-line font-mono text-xs text-dim">
        <p>
          pacelab is unofficial. Formula 1, F1, GRAND PRIX and related marks are trade
          marks of Formula One Licensing B.V.
        </p>
      </footer>
    </main>
  );
}
