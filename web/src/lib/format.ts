// Small format helpers for rendering numeric fields with consistent precision.

export const fmt = {
  /** Signed seconds at 3-decimal precision (e.g. "-0.183 s"). */
  signedSeconds(n: number, digits = 3): string {
    if (!Number.isFinite(n)) return "—";
    const abs = Math.abs(n).toFixed(digits);
    const sign = n > 0 ? "+" : n < 0 ? "−" : "±";
    return `${sign}${abs} s`;
  },

  /** Plain seconds (unsigned) with given precision. */
  seconds(n: number, digits = 3): string {
    if (!Number.isFinite(n)) return "—";
    return `${n.toFixed(digits)} s`;
  },

  /** Signed seconds per lap. */
  signedSPerLap(n: number, digits = 3): string {
    if (!Number.isFinite(n)) return "—";
    const abs = Math.abs(n).toFixed(digits);
    const sign = n > 0 ? "+" : n < 0 ? "−" : "±";
    return `${sign}${abs} s/lap`;
  },

  /** Confidence interval as "[lo, hi] s". */
  ci(lo: number, hi: number, digits = 3, suffix = " s"): string {
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) return "—";
    return `[${lo.toFixed(digits)}, ${hi.toFixed(digits)}]${suffix}`;
  },

  /** Mean with 2-decimal precision (used for positions gained). */
  positions(n: number, digits = 2): string {
    if (!Number.isFinite(n)) return "—";
    const sign = n > 0 ? "+" : n < 0 ? "−" : "±";
    return `${sign}${Math.abs(n).toFixed(digits)}`;
  },

  /** Percent. */
  pct(n: number, digits = 1): string {
    if (!Number.isFinite(n)) return "—";
    return `${(n * 100).toFixed(digits)}%`;
  },

  /** Compact integer formatting. */
  int(n: number): string {
    if (!Number.isFinite(n)) return "—";
    return Math.round(n).toString();
  },
};

/** Decide the colour to render a "lower-is-better" delta. */
export function deltaTone(n: number, lowerIsBetter: boolean): "positive" | "negative" | "neutral" {
  if (!Number.isFinite(n)) return "neutral";
  if (Math.abs(n) < 1e-9) return "neutral";
  const good = lowerIsBetter ? n < 0 : n > 0;
  return good ? "positive" : "negative";
}
