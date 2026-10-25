export type ExpansionCellStatus =
  | "scored"
  | "awaiting_server_grade"
  | "running"
  | "pending_score"
  | "queued"
  | "paused"
  | "awaiting_user_review";

export interface ExpansionCell {
  profile_id: string;
  dataset_id: string;
  status: ExpansionCellStatus;
  expected_n: number;
  completed_n: number;
  request_error_n: number;
  correct?: number;
  accuracy?: number | null;
  accuracy_ci95?: [number, number] | null;
  parse_valid_n?: number | null;
  parse_valid_pct?: number | null;
  truncated_n?: number | null;
  latency_s_p50?: number | null;
  latency_s_p90?: number | null;
  card_id?: string | null;
}

export interface ExpansionDataset {
  id: string;
  label: string;
  short_label: string;
  n: number;
  metric: string;
  gold: string;
}

export interface ExpansionProfile {
  id: string;
  display_name: string;
  provider: string;
  api_protocol: string;
  status: string;
  billing_mode: string;
  reasoning: string;
}

export interface ExpansionPilotRow {
  profile_id: string;
  status: string;
  vmlu_dev_accuracy?: number | null;
  vmlu_dev_n?: number | null;
  vmlu_dev_repeat_agreement_pct?: number | null;
  vmlu_dev_parse_valid_pct?: number | null;
  synthetic_agentic_accuracy?: number | null;
  synthetic_agentic_n?: number | null;
  synthetic_agentic_parse_valid_pct?: number | null;
  synthetic_agentic_repeat_agreement_pct?: number | null;
}

export interface ViMultimodelExpansionDashboard {
  protocol_id: string;
  protocol_version: number;
  generated_at: string;
  status: string;
  profiles: ExpansionProfile[];
  datasets: ExpansionDataset[];
  cells: ExpansionCell[];
  phases: Record<string, {
    status: string;
    expected_n: number;
    complete_n: number;
    request_error_n: number;
    card_id?: string | null;
    manifest_sha256?: string | null;
  }>;
  pilot: ExpansionPilotRow[];
  manifest_hashes: Record<string, string | null>;
  conditions: {
    execution_transport: string;
    omp_version_required: string;
    mode: string;
    system_prompt: string;
    tools: string;
    session_policy: string;
    workers_per_profile: number;
    max_parallel_opencode_profiles: number;
    reasoning_policy: string;
    sdk_retries: number;
    max_technical_recovery_attempts: number;
    max_time_seconds: number;
    completion_token_caps: Record<string, number>;
    gold_policy: Record<string, string>;
    safety_policy: string;
    submission_policy: string;
    qwen_policy: string;
    muse_data_handling_note: string;
    muse_data_handling_source: string;
  };
}

const EXPECTED_PROTOCOL_ID = "vi-multimodel-expansion-v2";
const EXPECTED_PROFILES = [
  "muse-spark-1-3-contributor",
  "mimo-v2-6-flash",
  "mimo-v2-5",
  "qwen3-5-9b-65k",
];
const EXPECTED_DATASETS = [
  { id: "vmlu_local", n: 1_047, metric: "accuracy", gold: "local" },
  { id: "vmlu_test", n: 9_833, metric: "server_accuracy", gold: "withheld" },
  { id: "vbench_mc", n: 4_141, metric: "server_accuracy", gold: "server" },
  { id: "vbench_agentic", n: 1_000, metric: "server_function_accuracy", gold: "server" },
];
const EXPECTED_GO_PROFILES = EXPECTED_PROFILES.slice(0, 3);
const CELL_STATUSES = new Set<ExpansionCellStatus>([
  "scored",
  "awaiting_server_grade",
  "running",
  "pending_score",
  "queued",
  "paused",
  "awaiting_user_review",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireNumber(value: unknown, label: string, min = 0): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min) {
    throw new Error(`Invalid V2 dashboard ${label}: expected finite number >= ${min}`);
  }
  return value;
}

function requireText(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`Invalid V2 dashboard ${label}: expected non-empty string`);
  }
  return value;
}

/** Validate the versioned local snapshot before a server page renders it. */
export function parseViMultimodelExpansionDashboard(value: unknown): ViMultimodelExpansionDashboard {
  if (!isRecord(value)) throw new Error("Invalid V2 dashboard: root must be an object");
  if (value.protocol_id !== EXPECTED_PROTOCOL_ID || value.protocol_version !== 2) {
    throw new Error("Invalid V2 dashboard: protocol identity/version mismatch");
  }
  requireText(value.generated_at, "generated_at");
  requireText(value.status, "status");
  if (!Array.isArray(value.profiles) || value.profiles.length !== EXPECTED_PROFILES.length) {
    throw new Error("Invalid V2 dashboard: expected exactly four model profiles");
  }
  const profiles = value.profiles as unknown[];
  for (let index = 0; index < EXPECTED_PROFILES.length; index += 1) {
    const profile = profiles[index];
    if (!isRecord(profile) || profile.id !== EXPECTED_PROFILES[index]) {
      throw new Error(`Invalid V2 dashboard: profile order/identity differs at row ${index}`);
    }
    requireText(profile.display_name, `profiles[${index}].display_name`);
    requireText(profile.provider, `profiles[${index}].provider`);
    requireText(profile.status, `profiles[${index}].status`);
  }
  if (!Array.isArray(value.datasets) || value.datasets.length !== EXPECTED_DATASETS.length) {
    throw new Error("Invalid V2 dashboard: expected exactly four main datasets");
  }
  const datasets = value.datasets as unknown[];
  for (let index = 0; index < EXPECTED_DATASETS.length; index += 1) {
    const dataset = datasets[index];
    const expected = EXPECTED_DATASETS[index];
    if (!isRecord(dataset) || dataset.id !== expected.id || dataset.n !== expected.n ||
        dataset.metric !== expected.metric || dataset.gold !== expected.gold) {
      throw new Error(`Invalid V2 dashboard: dataset contract differs at column ${index}`);
    }
  }
  if (!Array.isArray(value.cells) || value.cells.length !== EXPECTED_PROFILES.length * EXPECTED_DATASETS.length) {
    throw new Error("Invalid V2 dashboard: model × dataset cell count mismatch");
  }
  const cells = value.cells as unknown[];
  const seen = new Set<string>();
  for (const [index, rawCell] of cells.entries()) {
    if (!isRecord(rawCell)) throw new Error(`Invalid V2 dashboard: cells[${index}] must be an object`);
    const profileId = requireText(rawCell.profile_id, `cells[${index}].profile_id`);
    const datasetId = requireText(rawCell.dataset_id, `cells[${index}].dataset_id`);
    const key = `${profileId}\u0000${datasetId}`;
    if (seen.has(key)) throw new Error(`Invalid V2 dashboard: duplicate cell ${profileId}/${datasetId}`);
    seen.add(key);
    const dataset = EXPECTED_DATASETS.find((row) => row.id === datasetId);
    if (!EXPECTED_PROFILES.includes(profileId) || !dataset) {
      throw new Error(`Invalid V2 dashboard: unknown cell identity ${profileId}/${datasetId}`);
    }
    if (!CELL_STATUSES.has(rawCell.status as ExpansionCellStatus)) {
      throw new Error(`Invalid V2 dashboard: unknown cell status at ${profileId}/${datasetId}`);
    }
    if (rawCell.expected_n !== dataset.n) {
      throw new Error(`Invalid V2 dashboard: denominator drift at ${profileId}/${datasetId}`);
    }
    requireNumber(rawCell.completed_n, `cells[${index}].completed_n`);
    requireNumber(rawCell.request_error_n, `cells[${index}].request_error_n`);
    if (rawCell.accuracy !== null && rawCell.accuracy !== undefined) {
      requireNumber(rawCell.accuracy, `cells[${index}].accuracy`);
      if (dataset.gold !== "local" || rawCell.status !== "scored") {
        throw new Error(`Invalid V2 dashboard: local accuracy attached to withheld-gold cell ${profileId}/${datasetId}`);
      }
    }
  }
  if (!isRecord(value.phases)) throw new Error("Invalid V2 dashboard: phases must be an object");
  for (const profileId of EXPECTED_GO_PROFILES) {
    for (const phase of ["vmlu", "vbench"]) {
      const key = `${phase}:${profileId}`;
      const row = value.phases[key];
      if (!isRecord(row)) throw new Error(`Invalid V2 dashboard: missing phase ${key}`);
      requireText(row.status, `phases.${key}.status`);
      requireNumber(row.complete_n, `phases.${key}.complete_n`);
      requireNumber(row.expected_n, `phases.${key}.expected_n`, 1);
      requireNumber(row.request_error_n, `phases.${key}.request_error_n`);
    }
  }
  if (!Array.isArray(value.pilot)) throw new Error("Invalid V2 dashboard: pilot must be an array");
  if (!isRecord(value.manifest_hashes) || !isRecord(value.conditions)) {
    throw new Error("Invalid V2 dashboard: manifest hashes or conditions missing");
  }

  return value as unknown as ViMultimodelExpansionDashboard;
}
