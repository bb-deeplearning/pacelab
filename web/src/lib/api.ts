// Shared data fetchers + types for the pacelab web client.

export type Estimate = {
  value: number;
  ci_lo: number;
  ci_hi: number;
  n: number;
};

export type MetricBlock = Estimate & {
  definition: string;
  lower_is_better: boolean;
};

export type DriverIndexEntry = {
  season: number;
  driver_code: string;
  full_name: string;
  team_name: string;
  team_color: string;
  country_code: string;
};

export type IndexPayload = {
  schema_version: number;
  generated_at_utc: string;
  seasons: number[];
  drivers: DriverIndexEntry[];
};

export type DriverProfile = {
  schema_version: number;
  generated_at_utc: string;
  driver: {
    code: string;
    full_name: string;
    team_name: string;
    team_color: string;
    country_code: string;
    season: number;
    teammates: string[];
  };
  headline_metrics: {
    qualifying_pace_vs_teammate_s: MetricBlock;
    race_pace_vs_teammate_s: MetricBlock;
    stint_consistency_residual_sd_s: MetricBlock;
    consistency_delta_vs_teammate_s: MetricBlock;
    positions_gained_per_race: MetricBlock;
  };
  tyre_management: {
    by_compound_deg_delta_s_per_lap: Record<string, MetricBlock>;
  };
  wet_vs_dry: {
    wet_pace_vs_teammate_s: MetricBlock;
    dry_pace_vs_teammate_s: MetricBlock;
    wet_minus_dry_s: MetricBlock;
  };
  track_type?: {
    pace_vs_teammate_by_archetype_s: Record<string, MetricBlock & { label: string }>;
  };
  reliability: {
    dnfs: number;
    races_started: number;
    dnf_rate: number;
  };
  per_session: {
    qualifying: Array<{
      session_key: string;
      driver_code: string;
      teammate_code: string;
      team_name: string;
      best_time_s: number;
      teammate_best_s: number;
      delta_s: number;
      compared_segment: number;
    }>;
    race: Array<{
      session_key: string;
      teammate_code: string;
      pace_delta_median: number;
      deg_delta_median: number;
      n_overlap_laps: number;
      n_compounds: number;
    }>;
    race_results: Array<{
      session_key: string;
      year: number;
      round: number;
      driver_code: string;
      team_name: string;
      grid_position: number;
      finish_position: number;
      classified_position: string;
      dnf: boolean;
      positions_gained: number;
    }>;
  };
  last_race: {
    session_key: string;
    year: number;
    round: number;
    grid_position: number;
    finish_position: number;
    classified_position: string;
    dnf: boolean;
    positions_gained: number;
  } | null;
};

const API_BASE = process.env.PACELAB_API_URL ?? "http://127.0.0.1:8200";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`pacelab API ${res.status} for ${path}`);
  }
  return res.json() as Promise<T>;
}

export async function getIndex(): Promise<IndexPayload> {
  return fetchJson<IndexPayload>("/api/index");
}

export async function getDriver(season: number, code: string): Promise<DriverProfile> {
  return fetchJson<DriverProfile>(`/api/drivers/${season}/${code.toUpperCase()}`);
}
