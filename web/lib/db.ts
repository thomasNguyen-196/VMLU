/** DB-backed results reader (changes results-db-frontend + results-into-benchmark).
 *
 * Interface: getModels(), getDatasets(), getRuns(model?, dataset?),
 * getSummary(run_id), getItem(run_id, item_id), getItemsPage(run_id, opts).
 * Read-only: never aggregates at read time (dashboard numbers come from
 * precomputed `summaries`). One shared client behind the seam; route
 * handlers stay thin pass-throughs.
 */
import { MongoClient, type Db } from "mongodb";

const URI = process.env.VMLU_MONGO_URI ?? "mongodb://127.0.0.1:27017/";
const DB_NAME = process.env.VMLU_MONGO_DB ?? "vmlu";

let client: MongoClient | null = null;
let db: Db | null = null;

export function getDb(): Promise<Db> {
  if (db) return Promise.resolve(db);
  if (!client) client = new MongoClient(URI);
  return client.connect().then((c) => {
    client = c;
    db = c.db(DB_NAME);
    return db;
  });
}

/** For tests: swap the adapter behind the seam. */
export function __setDbForTest(next: Db | null): void {
  db = next;
}

export interface ModelDoc {
  _id: string;
  display_name: string;
  dir_slugs: string[];
  endpoint_ids: string[];
  params?: string;
  quantization?: string;
  endpoint?: string;
  notes?: string;
}

export interface DatasetDoc {
  _id: string;
  benchmark: string;
  split: string;
  n: number;
  source_file: string;
  source_sha256: string;
  gold_kind: string;
  manifest_path: string | null;
}

export interface RunDoc {
  _id: string;
  model_id: string;
  dataset_id: string;
  card_id: string;
  prompt_condition: string;
  config: Record<string, unknown>;
  measurement_card_hash: string;
  n: number;
  source_file: string;
  created_at: string;
}

export async function getModels(): Promise<ModelDoc[]> {
  const d = await getDb();
  return d.collection<ModelDoc>("models").find({}).sort({ _id: 1 }).toArray();
}

export async function getDatasets(): Promise<DatasetDoc[]> {
  const d = await getDb();
  return d.collection<DatasetDoc>("datasets").find({}).sort({ _id: 1 }).toArray();
}

export async function getRuns(model?: string, dataset?: string): Promise<RunDoc[]> {
  const d = await getDb();
  const q: Record<string, string> = {};
  if (model) q.model_id = model;
  if (dataset) q.dataset_id = dataset;
  return d.collection<RunDoc>("runs").find(q).sort({ _id: 1 }).toArray();
}

export async function getSummary(run: string): Promise<Record<string, unknown> | null> {
  const d = await getDb();
  return d.collection("summaries").findOne({ _id: run } as never);
}

const ITEM_COLLS = ["mc_items", "reading_items", "vbench_items"] as const;

export async function getItemsPage(
  run: string,
  opts: { collection?: string; correct?: 0 | 1; skip?: number; limit?: number } = {},
): Promise<{ collection: string; total: number; docs: Array<Record<string, unknown>> }> {
  const d = await getDb();
  const limit = Math.min(Math.max(opts.limit ?? 50, 1), 200);
  const skip = Math.max(opts.skip ?? 0, 0);
  const colls = opts.collection ? [opts.collection] : [...ITEM_COLLS];
  for (const coll of colls) {
    if (!ITEM_COLLS.includes(coll as (typeof ITEM_COLLS)[number])) continue;
    const q: Record<string, unknown> = { run_id: run };
    if (opts.correct !== undefined) q.correct = opts.correct;
    const cursor = d.collection(coll).find(q).sort({ item_id: 1 }).skip(skip).limit(limit);
    const docs = (await cursor.toArray()) as Array<Record<string, unknown>>;
    if (docs.length > 0 || (await d.collection(coll).countDocuments({ run_id: run })) > 0) {
      const total = await d.collection(coll).countDocuments(q);
      return { collection: coll, total, docs };
    }
  }
  return { collection: colls[0] ?? ITEM_COLLS[0], total: 0, docs: [] };
}

export async function getItem(
  run: string,
  item: string,
): Promise<{ collection: string; doc: Record<string, unknown> } | null> {
  const d = await getDb();
  for (const coll of ITEM_COLLS) {
    const doc = await d.collection(coll).findOne({ run_id: run, item_id: item });
    if (doc) return { collection: coll, doc: doc as Record<string, unknown> };
  }
  return null;
}

// ── Model notes (nhận xét thủ công giữa các model) ────────────────────────
// Nhiều note cho mỗi cặp (model_id, dataset_id, compare_model_id); mỗi lần
// lưu là một doc mới (không ghi đè). dataset_id BẮT BUỘC non-empty: note chỉ
// hiện ở đúng dataset của nó, không có phạm vi "chung mọi dataset".

export interface ModelNoteDoc {
  _id: string;
  model_id: string;
  /** Dataset phạm vi; luôn non-empty — note chỉ hiện ở dataset này. */
  dataset_id: string;
  /** Model được so sánh; "" = nhận xét chỉ dành riêng cho model_id. */
  compare_model_id: string;
  body: string;
  author: string;
  created_at: string;
  updated_at: string;
}

/** Id duy nhất cho mỗi lần lưu — ép "thêm mới", không upsert. */
export function modelNoteId(modelId: string, compareModelId: string, datasetId: string): string {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const rand = Math.random().toString(36).slice(2, 8);
  return `${modelId}__${datasetId}__${compareModelId || "solo"}__${stamp}__${rand}`;
}

/** Mọi note của model trong ĐÚNG dataset yêu cầu (mới nhất trước). */
export async function listModelNotes(modelId: string, datasetId = ""): Promise<ModelNoteDoc[]> {
  const d = await getDb();
  if (!datasetId) return [];
  return d
    .collection<ModelNoteDoc>("model_notes")
    .find({ model_id: modelId, dataset_id: datasetId })
    .sort({ created_at: -1 })
    .toArray();
}

export async function saveModelNote(
  modelId: string,
  compareModelId: string,
  datasetId: string,
  body: string,
  author: string,
): Promise<ModelNoteDoc> {
  if (!datasetId) throw new Error("saveModelNote cần dataset non-empty (không còn note chung)");
  const now = new Date().toISOString();
  const d = await getDb();
  const coll = d.collection<ModelNoteDoc>("model_notes");
  const _id = modelNoteId(modelId, compareModelId, datasetId);
  const doc: ModelNoteDoc = {
    _id, model_id: modelId, dataset_id: datasetId, compare_model_id: compareModelId,
    body, author, created_at: now, updated_at: now,
  };
  await coll.insertOne(doc);
  return doc;
}

/** Xóa một note theo _id (chỉ khi đúng model chủ). Trả về số doc đã xóa. */
export async function deleteModelNote(modelId: string, noteId: string): Promise<number> {
  const d = await getDb();
  const r = await d.collection<ModelNoteDoc>("model_notes").deleteOne({ _id: noteId, model_id: modelId });
  return r.deletedCount;
}

