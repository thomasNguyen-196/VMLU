/** Explicit model × task matrix for the frozen vi-multimodel-v1 protocol.
 *
 * The selector accepts only one completed main run per profile/task. It never
 * picks the newest run implicitly, so a pilot or alternate condition cannot
 * silently take the place of a headline score.
 */
import { getDatasets, getModels, getRuns, getSummary } from "@/lib/db.ts";

export const MULTIMODEL_PROTOCOL_ID = "vi-multimodel-v1";

export const MULTIMODEL_PROFILES = [
  { id: "muse-spark-1-3-contributor", name: "Muse Spark 1.3", tier: "Contributor" },
  { id: "mimo-v2-6-flash", name: "MiMo V2.6", tier: "Flash" },
  { id: "mimo-v2-5", name: "MiMo V2.5", tier: "" },
  { id: "qwen3-5-9b-65k", name: "Qwen3.5-9B", tier: "65K" },
] as const;

export const MULTIMODEL_DATASETS = [
  { id: "vi-multimodel-v1-vmlu-valid", label: "VMLU", shortLabel: "kiến thức", n: 744, metric: "accuracy" },
  { id: "vi-multimodel-v1-vi-squad-200", label: "Vi-SQuAD", shortLabel: "đọc hiểu", n: 200, metric: "reading" },
  { id: "vi-multimodel-v1-vi-drop-200", label: "Vi-DROP", shortLabel: "suy luận", n: 200, metric: "reading" },
  { id: "vi-multimodel-v1-legal-mc-146", label: "Legal MC", shortLabel: "pháp luật", n: 146, metric: "accuracy" },
  { id: "vi-multimodel-v1-legal-nli-150", label: "Legal NLI", shortLabel: "pháp luật NLI", n: 150, metric: "accuracy" },
  { id: "vi-multimodel-v1-bidlqa-test", label: "ViBidLQA", shortLabel: "đấu thầu", n: 603, metric: "reading" },
] as const;

export type MultiModelCellStatus = "scored" | "not_run" | "summary_missing" | "incomplete" | "ambiguous";

export interface MultiModelCell {
  profile_id: string;
  dataset_id: string;
  run_id: string | null;
  card_id: string | null;
  status: MultiModelCellStatus;
  expected_n: number;
  n: number;
  correct?: number;
  unparsed_n?: number;
  empty_answer_n?: number;
  accuracy?: number;
  accuracy_ci95?: [number, number] | null;
  em?: number;
  em_count?: number;
  em_ci95?: [number, number] | null;
  token_f1?: number;
  token_f1_ci95?: [number, number] | null;
  legacy_em?: number;
  legacy_char_f1?: number;
  coverage_pct?: number;
  request_error_n?: number;
  truncated_n?: number;
  latency_s_p50?: number | null;
  latency_s_p90?: number | null;
  prompt_tokens_mean?: number | null;
  completion_tokens_mean?: number | null;
  tier: string;
  endpoint: string;
  measurement_card_hash?: string;
}

export interface MultiModelMatrix {
  protocol_id: string;
  protocol_version: number;
  profiles: Array<{ id: string; display_name: string; tier: string }>;
  datasets: Array<(typeof MULTIMODEL_DATASETS)[number]>;
  cells: MultiModelCell[];
}

function readRows(summary: Record<string, unknown> | null, key: string): Array<Record<string, unknown>> {
  const rows = summary?.[key];
  return Array.isArray(rows) ? rows as Array<Record<string, unknown>> : [];
}

function ciPair(value: unknown): [number, number] | null {
  if (!Array.isArray(value) || value.length !== 2 ||
      typeof value[0] !== "number" || typeof value[1] !== "number") return null;
  return [value[0], value[1]];
}

export async function getViMultimodelMatrix(): Promise<MultiModelMatrix> {
  const [modelDocs, datasetDocs, runs] = await Promise.all([getModels(), getDatasets(), getRuns()]);
  const modelById = new Map(modelDocs.map((model) => [model._id, model]));
  const datasetById = new Map(datasetDocs.map((dataset) => [dataset._id, dataset]));
  const chosenRuns = new Map<string, (typeof runs)[number][]>();

  for (const run of runs) {
    if (run.config.protocol_id !== MULTIMODEL_PROTOCOL_ID || run.config.phase !== "main") continue;
    const key = run.model_id + "\u0000" + run.dataset_id;
    chosenRuns.set(key, [...(chosenRuns.get(key) ?? []), run]);
  }

  const matrixCells: MultiModelCell[] = [];
  const requests: Array<Promise<void>> = [];
  for (const profile of MULTIMODEL_PROFILES) {
    const model = modelById.get(profile.id);
    for (const dataset of MULTIMODEL_DATASETS) {
      const matches = chosenRuns.get(profile.id + "\u0000" + dataset.id) ?? [];
      const base: MultiModelCell = {
        profile_id: profile.id,
        dataset_id: dataset.id,
        run_id: null,
        card_id: null,
        status: matches.length > 1 ? "ambiguous" : matches.length === 0 ? "not_run" : "summary_missing",
        expected_n: dataset.n,
        n: 0,
        tier: profile.tier,
        endpoint: model?.endpoint ?? "",
      };
      if (matches.length !== 1) {
        matrixCells.push(base);
        continue;
      }

      const run = matches[0];
      const cell: MultiModelCell = {
        ...base,
        run_id: run._id,
        card_id: run.card_id,
        n: run.n,
        measurement_card_hash: run.measurement_card_hash,
      };
      requests.push(getSummary(run._id).then((summary) => {
        if (!summary) {
          matrixCells.push(cell);
          return;
        }
        if (run.n !== dataset.n) {
          cell.status = "incomplete";
          matrixCells.push(cell);
          return;
        }
        if (dataset.metric === "accuracy") {
          const overall = readRows(summary, "accuracy_rows").find((row) => row.level === "overall");
          if (overall && Number(overall.n) === dataset.n && typeof overall.accuracy === "number") {
            cell.status = "scored";
            cell.n = Number(overall.n);
            cell.correct = Number(overall.correct);
            cell.unparsed_n = Number(overall.unparsed_n ?? 0);
            cell.accuracy = Number(overall.accuracy);
            cell.accuracy_ci95 = ciPair(summary.ci95);
          } else {
            cell.status = "incomplete";
          }
        } else {
          const overall = readRows(summary, "reading_rows").find((row) => row.dataset === "ALL");
          if (overall && Number(overall.n) === dataset.n
              && typeof overall.em === "number" && typeof overall.token_f1 === "number") {
            cell.status = "scored";
            cell.n = Number(overall.n);
            cell.em = Number(overall.em);
            cell.em_count = Number(overall.em_count);
            cell.empty_answer_n = Number(overall.empty_answer_n ?? 0);
            cell.em_ci95 = ciPair(overall.em_ci95);
            cell.token_f1 = Number(overall.token_f1);
            cell.token_f1_ci95 = ciPair(overall.token_f1_ci95);
            cell.legacy_em = typeof overall.legacy_final_em === "number" ? Number(overall.legacy_final_em) : undefined;
            cell.legacy_char_f1 = typeof overall.legacy_final_char_f1 === "number"
              ? Number(overall.legacy_final_char_f1)
              : undefined;
          } else {
            cell.status = "incomplete";
          }
        }
        matrixCells.push(cell);
      }));
    }
  }
  await Promise.all(requests);

  // Promise completion order must never change row or column order.
  const cellByKey = new Map(
    matrixCells.map((cell) => [cell.profile_id + "\u0000" + cell.dataset_id, cell]),
  );
  const cells = MULTIMODEL_PROFILES.flatMap((profile) =>
    MULTIMODEL_DATASETS.map((dataset) =>
      cellByKey.get(profile.id + "\u0000" + dataset.id)!,
    ),
  );
  return {
    protocol_id: MULTIMODEL_PROTOCOL_ID,
    protocol_version: 1,
    profiles: MULTIMODEL_PROFILES.map((profile) => ({
      id: profile.id,
      display_name: modelById.get(profile.id)?.display_name ?? profile.name,
      tier: profile.tier,
    })),
    datasets: [...MULTIMODEL_DATASETS],
    cells,
  };
}
