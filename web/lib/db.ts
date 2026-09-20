/** DB-backed results reader (change results-db-frontend) — one deep module.
 *
 * Interface: getModels(), getDatasets(), getRuns(model?, dataset?),
 * getSummary(run_id), getItem(run_id, item_id). Read-only: never aggregates
 * at read time (dashboard numbers come from precomputed `summaries`).
 * One shared client behind the seam; route handlers stay thin pass-throughs.
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
