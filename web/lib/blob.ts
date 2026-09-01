import { promises as fs } from "fs";
import path from "path";
import { SCHEMA_VERSION, type ReviewBlob } from "./types.ts";

/** The app's only input: web/data/review-blob.json, written by
 *  `code_benchmark/build_review_ui.py export-blob` (which runs the whole
 *  fail-fast join validation in Python — the app never parses CSVs). */
export const BLOB_REGEN_HINT =
  "chạy: .venv/bin/python code_benchmark/build_review_ui.py export-blob (từ thư mục gốc repo)";

export function blobPath(): string {
  return process.env.VMLU_REVIEW_BLOB
    ? path.resolve(process.env.VMLU_REVIEW_BLOB)
    : path.join(process.cwd(), "data", "review-blob.json");
}

export async function loadBlob(): Promise<ReviewBlob> {
  let raw: string;
  try {
    raw = await fs.readFile(blobPath(), "utf-8");
  } catch {
    throw new Error(`không tìm thấy blob ${blobPath()} — ${BLOB_REGEN_HINT}`);
  }
  let obj: unknown;
  try {
    obj = JSON.parse(raw);
  } catch {
    throw new Error(`blob không phải JSON hợp lệ — ${BLOB_REGEN_HINT}`);
  }
  const b = obj as Partial<ReviewBlob>;
  if (b?.schema_version !== SCHEMA_VERSION) {
    throw new Error(`blob schema_version ${String(b?.schema_version)} ≠ ${SCHEMA_VERSION} — ${BLOB_REGEN_HINT}`);
  }
  if (!Array.isArray(b.items) || !b.items.length || !Array.isArray(b.models) || !b.models.length) {
    throw new Error("blob thiếu items/models — " + BLOB_REGEN_HINT);
  }
  return b as ReviewBlob;
}
