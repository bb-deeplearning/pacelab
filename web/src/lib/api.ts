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

export type LeaderboardEntry = {
  driver_code: string;
  full_name: string;
  team_name: string;
  team_color: string;
  value: number | null;
  ci_lo: number | null;
  ci_hi: number | null;
  n: number;
};

export type LeaderboardPayload = {
  schema_version: number;
  generated_at_utc: string;
  season: number;
  metrics: Array<{
    id: string;
    label: string;
    section: string;
    lower_is_better: boolean;
  }>;
  leaderboards: Record<string, LeaderboardEntry[]>;
};

export type TeammatePair = {
  team_name: string;
  driver_a: string;
  driver_b: string;
  qualifying: { a_wins: number; b_wins: number; compared: number };
  race_pace: { a_wins: number; b_wins: number; compared: number };
  finish_position: { a_wins: number; b_wins: number; compared: number };
  dnfs: { a: number; b: number };
};

export type TeammatesPayload = {
  schema_version: number;
  generated_at_utc: string;
  season: number;
  pairs: TeammatePair[];
};

export type SeasonMetricSnapshot = {
  value: number | null;
  ci_lo: number | null;
  ci_hi: number | null;
  n: number;
};

export type CareerSeasonEntry = {
  season: number;
  team_name: string;
  team_color: string;
  teammates: string[];
  metrics: Record<string, SeasonMetricSnapshot>;
  reliability?: { dnfs: number; races_started: number; dnf_rate: number };
};

export type DriverCareer = {
  driver_code: string;
  full_name: string;
  country_code: string;
  seasons: CareerSeasonEntry[];
};

export type CareersPayload = {
  schema_version: number;
  generated_at_utc: string;
  drivers: DriverCareer[];
};

export type AlltimeEntry = {
  driver_code: string;
  full_name: string;
  latest_team: string;
  latest_team_color: string;
  value: number | null;
  ci_lo: number | null;
  ci_hi: number | null;
  n: number;
  seasons_count: number;
  seasons: number[];
  teams: string[];
};

export type AlltimePayload = {
  schema_version: number;
  generated_at_utc: string;
  metrics: Array<{
    id: string;
    label: string;
    section: string;
    lower_is_better: boolean;
  }>;
  leaderboards: Record<string, AlltimeEntry[]>;
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
  style?: {
    throttle_smoothness_delta: MetricBlock & { unit: string };
    brake_dwell_delta_s: MetricBlock & { unit: string };
    full_throttle_fraction_delta: MetricBlock & { unit: string };
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

export async function getLeaderboards(season: number): Promise<LeaderboardPayload | null> {
  try {
    return await fetchJson<LeaderboardPayload>(`/api/seasons/${season}/leaderboards`);
  } catch {
    return null;
  }
}

export async function getTeammates(season: number): Promise<TeammatesPayload | null> {
  try {
    return await fetchJson<TeammatesPayload>(`/api/seasons/${season}/teammates`);
  } catch {
    return null;
  }
}

export async function getCareer(code: string): Promise<DriverCareer | null> {
  try {
    return await fetchJson<DriverCareer>(`/api/careers/${code.toUpperCase()}`);
  } catch {
    return null;
  }
}

export async function getAlltime(): Promise<AlltimePayload | null> {
  try {
    return await fetchJson<AlltimePayload>("/api/alltime");
  } catch {
    return null;
  }
}
