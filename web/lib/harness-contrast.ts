/** Harness → benchmark cross-link view layer.
 *
 * WHY this module exists: the harness study and the benchmark dashboard measure
 * the SAME cells. `arm A` of a harness row is the direct-prompt arm, and its
 * numbers coincide with the Mongo summaries (reading-400 79.75 EM, legal-mc
 * 87.67, legal-nli 90.0, bidlqa-val 32.78 for Qwen3.5-9B-28K). But the two
 * surfaces speak different vocabularies, so nothing linked them:
 *
 *   harness (frozen blob)   benchmark (live Mongo)
 *   model:  "Qwen3.5-9B-28K"   model_id:  "qwen3-5-9b-28k"
 *   dataset: "reading400"       dataset_id: "reading-400"
 *
 * This file owns that translation and nothing else: no `fs`, no DB, no
 * arithmetic. Pure, so the page can call it server-side and the client can
 * import the types.
 *
 * TWO RULES this module must not break:
 *
 * 1. Model identity joins on `display_name`, which both sides already carry —
 *    it is data, not a hand-written map. A model that exists only in the
 *    harness study (MiMo V2.5 has no Mongo runs) simply yields no contrast;
 *    a model with no harness arm (qwen38-nothink) yields none either. Neither
 *    case may be rendered as a zero.
 *
 * 2. `arm_a` is the harness study's OWN direct arm. It is NOT asserted to be
 *    the same run_id as the number in the Mongo summary — nothing in the block
 *    proves that yet (see `arm_a_run_id` in the builder). So the view-model
 *    carries `armAMatchesSummary: null`, and the UI must label arm A as the
 *    study's own arm rather than implying it is the hero number. Until the
 *    builder records the run id, that stays unresolved instead of assumed.
 */
import type { HarnessBlock, HarnessRow } from "./harness-block.ts";

/** harness `dataset` token → Mongo `dataset_id`. Every harness dataset is a
 *  benchmark dataset; the reverse is NOT true (vmlu-*, bidlqa-test, vm14k have
 *  no harness arm), which is why this map is one-directional. */
export const HARNESS_DATASET_TO_ID: Record<string, string> = {
  reading400: "reading-400",
  legal_mc: "legal-mc-146",
  legal_nli: "legal-nli-150",
  bidlqa_val: "bidlqa-val",
  vbench_mc: "vbench-public-test",
  vbench_agentic: "vbench-public-test",
};

/** One arm of one dataset, reduced to what a cross-link strip shows. */
export interface HarnessArmVM {
  arm: string;
  label: string;
  card: string | null;
  metric: string;
  n: number;
  armA: number;
  armB: number;
  delta: number;
  ci95Low: number;
  ci95High: number;
  mcnemarP: string;
  /** Anchor on /harness — `tap-<harnessDataset>`. */
  href: string;
}

/** Every harness arm measured for one (model, dataset) cell. */
export interface HarnessContrastVM {
  harnessDataset: string;
  datasetLabel: string;
  metric: string;
  n: number;
  arms: HarnessArmVM[];
  /** Always null today — see rule 2 in the module docstring. Deliberately not
   *  a boolean: "not verified" and "verified different" must not collapse. */
  armAMatchesSummary: null;
}

/** harness display_name → benchmark dataset_id → cell. One cell per pair, so a
 *  dataset measured by several arms (H2/H5/M6) stays ONE entry holding all of
 *  them — that is what makes the strip a comparison rather than a list. */
export type HarnessContrastMap = Record<string, Record<string, HarnessContrastVM>>;

function toArmVM(row: HarnessRow): HarnessArmVM {
  return {
    arm: row.arm,
    label: row.label,
    card: row.card,
    metric: row.metric,
    n: row.n,
    armA: row.arm_a,
    armB: row.arm_b,
    delta: row.delta,
    ci95Low: row.ci95_low,
    ci95High: row.ci95_high,
    mcnemarP: row.mcnemar_p,
    href: `/harness#tap-${row.dataset}`,
  };
}

/** Index the ladder by (model display_name, benchmark dataset_id).
 *
 *  `baseline` rows are skipped on purpose: they carry no paired stats and their
 *  value is `arm_a`, already carried by every `harness` row of the same cell.
 *  A cell with no `harness` row returns an empty array, which the UI must say
 *  out loud — an absent arm is not an arm scoring zero.
 *
 *  `vbench_mc` and `vbench_agentic` both map to `vbench-public-test` and so land
 *  in the same bucket, but they are different metrics on different subsets
 *  (agreement-with-arm-A vs schema validity). The rows keep their own `metric`
 *  so the strip can refuse to blend them.
 */
export function indexHarnessContrasts(
  block: HarnessBlock | null | undefined,
): HarnessContrastMap {
  const out: HarnessContrastMap = {};
  if (!block) return out;
  for (const row of block.ladder) {
    if (row.role !== "harness") continue;
    const datasetId = HARNESS_DATASET_TO_ID[row.dataset];
    if (!datasetId) continue; // unmapped harness dataset: no benchmark cell to hang on
    const byDataset = (out[row.model] ??= {});
    const cell = (byDataset[datasetId] ??= {
      harnessDataset: row.dataset,
      datasetLabel: row.dataset_label,
      metric: row.metric,
      n: row.n,
      arms: [],
      armAMatchesSummary: null,
    });
    cell.arms.push(toArmVM(row));
  }
  for (const byDataset of Object.values(out)) {
    for (const cell of Object.values(byDataset)) {
      // Worst arm first: the reason to open the strip is the biggest loss.
      cell.arms.sort((a: HarnessArmVM, b: HarnessArmVM) => a.delta - b.delta);
    }
  }
  return out;
}

/** The cross-link for one cell, or null when this dataset has no harness arm. */
export function harnessContrastFor(
  map: HarnessContrastMap | null | undefined,
  modelDisplayName: string,
  datasetId: string,
): HarnessContrastVM | null {
  return map?.[modelDisplayName]?.[datasetId] ?? null;
}