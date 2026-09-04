import { promises as fs } from "fs";
import path from "path";
import { REVIEW_COLS } from "./export-csv.ts";
import { slug } from "./slug.ts";

/** Peer-review sync record (the split-400 workflow): committed CSVs under
 *  <repoRoot>/review_records/review_<reviewer>_<model>.csv — the same 9-column
 *  contract /api/export produces. Exporting in the app PUBLISHES your CSV there
 *  (overwrite by design: one file per reviewer×model), so `git commit + push`
 *  hands your finished items to the next reviewer, and on startup the app reads
 *  every peer CSV and locks the items they already decided (accept/reject).
 *  Blank decisions (unreviewed or flag-with-note) are NOT locks — flagged items
 *  stay open on purpose. The CSVs in git are the durable log; review_state/
 *  stays the private working bucket (gitignored, never shared — blind protocol). */

export interface PeerDecision {
  reviewer: string;
  decision: "accept" | "reject";
  /** the peer's corrected answer / note (reject rows carry `c`) */
  c: string;
  n: string;
}
/** itemKey (`dataset:item_id`) -> the peer who decided it. */
export type PeerMap = Record<string, PeerDecision>;

function recordsDir(): string {
  // repo root, one level above the Next app — same sibling logic as stateDir.
  return (
    process.env.VMLU_REVIEW_RECORDS_DIR ??
    path.join(/* turbopackIgnore: true */ process.cwd(), "..", "review_records")
  );
}

/** Minimal RFC-4180 reader: quoted cells, doubled quotes, CRLF. Only the
 *  subset makeExportCsv emits; the merge tool (`read_review`) stays the
 *  strict authority — this parser only has to recognize locks, and it
 *  fails-open: an unparseable/ragged row is skipped, which can at worst let
 *  an item be reviewed twice, never hide a peer's finished work. */
function parseCsvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i++;
        } else q = false;
      } else cell += ch;
    } else if (ch === '"') q = true;
    else if (ch === ",") {
      row.push(cell);
      cell = "";
    } else if (ch === "\r") {
      /* swallow — \n commits the row */
    } else if (ch === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else cell += ch;
  }
  if (cell !== "" || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}

interface ParsedRecord {
  annotator: string;
  model: string;
  decided: PeerMap;
}

/** -> ParsedRecord, or throws on header drift (wrong file, schema changed). */
function parseReviewCsv(text: string): ParsedRecord {
  const rows = parseCsvRows(text.replace(/^﻿/, ""));
  const head = rows.shift() ?? [];
  if (head.join(",") !== REVIEW_COLS.join(",")) {
    throw new Error(`header mismatch — expected 9 review columns, got: ${head.join(",")}`);
  }
  let annotator = "";
  let model = "";
  const decided: PeerMap = {};
  for (const r of rows) {
    if (r.length !== REVIEW_COLS.length) continue; // ragged hand-edit: skip row
    if (!annotator) [annotator, model] = r;
    const d = r[5];
    if (d === "accept" || d === "reject") decided[`${r[2]}:${r[3]}`] = { reviewer: r[0], decision: d, c: r[7], n: r[8] };
  }
  return { annotator, model, decided };
}

export interface RecordFileRow {
  file: string;
  annotator: string;
  model: string;
  decided: number;
  error?: string;
}

interface PeerScan {
  /** decisions by OTHER reviewers for `model`, `self` excluded by slug */
  peers: PeerMap;
  /** every CSV found, for the start panel + surfacing broken files */
  files: RecordFileRow[];
}

export async function loadPeerDecisions(model: string, selfReviewer: string): Promise<PeerScan> {
  const self = slug(selfReviewer);
  let names: string[];
  try {
    names = await fs.readdir(recordsDir());
  } catch {
    return { peers: {}, files: [] }; // no folder yet = nobody has exported
  }
  const peers: PeerMap = {};
  const files: RecordFileRow[] = [];
  for (const name of names.sort()) {
    if (!name.endsWith(".csv") || name.includes(".tmp-")) continue;
    let rec: ParsedRecord;
    try {
      rec = parseReviewCsv(await fs.readFile(path.join(recordsDir(), name), "utf-8"));
    } catch (e) {
      files.push({
        file: name,
        annotator: "",
        model: "",
        decided: 0,
        error: e instanceof Error ? e.message : String(e),
      });
      continue;
    }
    files.push({ file: name, annotator: rec.annotator, model: rec.model, decided: Object.keys(rec.decided).length });
    if (rec.model !== model || slug(rec.annotator) === self) continue;
    for (const [k, v] of Object.entries(rec.decided)) peers[k] ??= v; // first file wins (alphabetical)
  }
  return { peers, files };
}

/** Write this reviewer×model's CSV into the shared folder (atomic). The
 *  filename embeds both slugs so concurrent reviewers can never collide. */
export async function publishRecord(annotator: string, model: string, csv: string): Promise<string> {
  const dir = recordsDir();
  await fs.mkdir(dir, { recursive: true });
  const target = path.join(dir, `review_${slug(annotator)}_${slug(model)}.csv`);
  const tmp = `${target}.tmp-${process.pid}-${Date.now()}`;
  await fs.writeFile(tmp, csv, "utf-8");
  await fs.rename(tmp, target);
  return path.relative(path.join(dir, ".."), target);
}
