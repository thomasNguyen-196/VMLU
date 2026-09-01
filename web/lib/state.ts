import { promises as fs } from "fs";
import path from "path";
import { SCHEMA_VERSION, type StateEnvelope } from "./types.ts";
import { slug } from "./slug.ts";

/** On-disk reviewer state: one JSON file per (reviewer, model) bucket at
 *  <repoRoot>/review_state/<slug(reviewer)>__<slug(model)>.json — gitignored,
 *  same layout rev-1's Python server used, so buckets are portable between
 *  tools. Last write wins (single researcher, single browser tab per bucket);
 *  writes are atomic (tmp file + rename) so a crash never leaves half a file. */

export function stateDir(): string {
  // The state lives at the REPO root (shared with the Python tooling), i.e.
  // one level above this Next app. The ".." is intentional; turbopackIgnore
  // tells the bundler's fs-tracer not to escalate to whole-project tracing.
  return process.env.VMLU_REVIEW_STATE_DIR ?? path.join(/* turbopackIgnore: true */ process.cwd(), "..", "review_state");
}

export function bucketPath(reviewer: string, model: string): string {
  return path.join(stateDir(), `${slug(reviewer)}__${slug(model)}.json`);
}

export interface LoadResult {
  /** null = bucket never saved (fresh start) */
  envelope: StateEnvelope | null;
  /** non-null = the file exists but is unreadable/foreign; the app must NOT
   *  treat that as empty (spec review-server "Corrupt bucket file"). */
  error?: string;
}

export async function loadBucket(reviewer: string, model: string): Promise<LoadResult> {
  let raw: string;
  try {
    raw = await fs.readFile(bucketPath(reviewer, model), "utf-8");
  } catch (e) {
    const err = e as NodeJS.ErrnoException;
    if (err.code === "ENOENT") return { envelope: null };
    return { envelope: null, error: `${err.code ?? "read error"}` };
  }
  let obj: unknown;
  try {
    obj = JSON.parse(raw);
  } catch {
    return { envelope: null, error: "file is not valid JSON — repair it or move it aside" };
  }
  const check = checkEnvelope(obj);
  if (check) return { envelope: null, error: check };
  return { envelope: obj as StateEnvelope };
}

/** -> error message, or null when the object is a valid envelope. */
export function checkEnvelope(obj: unknown): string | null {
  if (!obj || typeof obj !== "object") return "not an object";
  const o = obj as Record<string, unknown>;
  if (o.schema_version !== SCHEMA_VERSION) {
    return `schema_version ${String(o.schema_version)} ≠ ${SCHEMA_VERSION} — rebuild/upgrade first`;
  }
  if (typeof o.annotator !== "string" || typeof o.model !== "string") return "annotator/model must be strings";
  if (!o.items || typeof o.items !== "object" || Array.isArray(o.items)) return "items must be an object";
  return null;
}

export async function saveBucket(envelope: StateEnvelope): Promise<void> {
  const err = checkEnvelope(envelope);
  if (err) throw new Error(err);
  const target = bucketPath(envelope.annotator, envelope.model);
  await fs.mkdir(path.dirname(target), { recursive: true });
  const tmp = `${target}.tmp-${process.pid}-${Date.now()}`;
  await fs.writeFile(tmp, JSON.stringify(envelope), "utf-8");
  await fs.rename(tmp, target);
}

export interface BucketRow {
  file: string;
  reviewer: string;
  model: string;
  annotator: string;
  saved_at: string;
  decided: number;
  error?: string;
}

export async function listBuckets(): Promise<BucketRow[]> {
  let names: string[];
  try {
    names = await fs.readdir(stateDir());
  } catch {
    return [];
  }
  const rows: BucketRow[] = [];
  for (const name of names.sort()) {
    if (!name.endsWith(".json") || name.includes(".tmp-")) continue;
    const stem = name.slice(0, -".json".length);
    const sep = stem.indexOf("__");
    if (sep < 0) continue;
    const reviewerSlug = stem.slice(0, sep);
    const modelSlug = stem.slice(sep + 2);
    let env: StateEnvelope | null = null;
    let error: string | undefined;
    try {
      const raw = await fs.readFile(path.join(stateDir(), name), "utf-8");
      const parsed: unknown = JSON.parse(raw);
      error = checkEnvelope(parsed) ?? undefined;
      if (!error) env = parsed as StateEnvelope;
    } catch {
      error = "unreadable";
    }
    rows.push({
      file: name,
      reviewer: reviewerSlug,
      model: modelSlug,
      annotator: env?.annotator ?? "",
      saved_at: env?.saved_at ?? "",
      decided: env ? Object.values(env.items).filter((v) => v?.d).length : 0,
      ...(error ? { error } : {}),
    });
  }
  return rows;
}
