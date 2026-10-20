/** Parse the model-behavior changelog markdown into a renderable document.
 *
 * The markdown file `docs/model-behavior-changelog.md` is the single source of
 * truth; `/changelog` re-reads it per request (`force-dynamic`) so new entries
 * appear without a build. The format is intentionally small: `#` title, `>`
 * intro paragraphs, `##` dated entries, paragraphs, and `- ` bullets that may
 * start with a backticked category tag (`[model]`, `[provider]`, ...).
 */

export type ChangelogCategory = "model" | "provider" | "harness" | "data" | "ops" | "other";

export interface ChangelogItem {
  category: ChangelogCategory;
  text: string;
}

export interface ChangelogEntry {
  title: string;
  meta: string[];
  items: ChangelogItem[];
}

export interface ChangelogDoc {
  title: string;
  intro: string[];
  entries: ChangelogEntry[];
}

export interface InlineSegment {
  kind: "text" | "bold" | "code";
  value: string;
}

const CATEGORIES = new Set<string>(["model", "provider", "harness", "data", "ops"]);
const INLINE_PATTERN = /(\*\*[^*]+\*\*|`[^`]+`)/;

/** Split `**bold**` and `` `code` `` spans out of one line. */
export function parseInline(text: string): InlineSegment[] {
  const segments: InlineSegment[] = [];
  let rest = text;
  for (;;) {
    const match = INLINE_PATTERN.exec(rest);
    if (!match) break;
    if (match.index > 0) segments.push({ kind: "text", value: rest.slice(0, match.index) });
    const token = match[0];
    if (token.startsWith("**")) segments.push({ kind: "bold", value: token.slice(2, -2) });
    else segments.push({ kind: "code", value: token.slice(1, -1) });
    rest = rest.slice(match.index + token.length);
  }
  if (rest) segments.push({ kind: "text", value: rest });
  return segments;
}

function taggedItem(line: string): ChangelogItem {
  const match = /^`\[([a-z]+)\]`\s*/.exec(line);
  if (match && CATEGORIES.has(match[1])) {
    return { category: match[1] as ChangelogCategory, text: line.slice(match[0].length) };
  }
  return { category: "other", text: line };
}

export function parseChangelog(markdown: string): ChangelogDoc {
  const doc: ChangelogDoc = { title: "", intro: [], entries: [] };
  let entry: ChangelogEntry | null = null;
  let introBuffer: string[] = [];
  const flushIntro = () => {
    if (introBuffer.length) {
      doc.intro.push(introBuffer.join(" "));
      introBuffer = [];
    }
  };
  for (const raw of markdown.split(/\r?\n/)) {
    const line = raw.trimEnd();
    if (!line.trim() || line.trim() === "---") continue;
    if (line.startsWith("> ")) {
      introBuffer.push(line.slice(2).trim());
      continue;
    }
    if (line.startsWith(">")) {
      flushIntro();
      continue;
    }
    if (line.startsWith("# ")) {
      doc.title = line.slice(2).trim();
      continue;
    }
    if (line.startsWith("## ")) {
      flushIntro();
      entry = { title: line.slice(3).trim(), meta: [], items: [] };
      doc.entries.push(entry);
      continue;
    }
    if (!entry) continue;
    if (line.startsWith("- ")) {
      entry.items.push(taggedItem(line.slice(2).trim()));
      continue;
    }
    entry.meta.push(line.trim());
  }
  flushIntro();
  return doc;
}

/** Server-side loader for the generated artifact (works on the host and in the
 *  container that mounts only `web/`). Regenerate the JSON with
 *  `python code_benchmark/build_model_behavior_changelog.py` after editing the markdown. */
export async function loadChangelog(): Promise<ChangelogDoc> {
  const { readFile } = await import("node:fs/promises");
  const path = await import("node:path");
  const file = path.join(/* turbopackIgnore: true */ process.cwd(), "data", "model-behavior-changelog.json");
  return parseChangelogDocument(JSON.parse(await readFile(file, "utf-8")) as unknown);
}

function invalid(message: string): never {
  throw new Error(`Invalid changelog artifact: ${message}`);
}

function parseItem(value: unknown): ChangelogItem {
  if (!value || typeof value !== "object") invalid("item");
  const item = value as Record<string, unknown>;
  const category = item.category;
  if (typeof category !== "string" || !(CATEGORIES.has(category) || category === "other")) invalid("item category");
  if (typeof item.text !== "string" || !item.text.trim()) invalid("item text");
  return { category: category as ChangelogCategory, text: item.text };
}

function parseEntry(value: unknown): ChangelogEntry {
  if (!value || typeof value !== "object") invalid("entry");
  const entry = value as Record<string, unknown>;
  if (typeof entry.title !== "string" || !entry.title.trim()) invalid("entry title");
  if (!Array.isArray(entry.meta) || !entry.meta.every((line) => typeof line === "string")) invalid("entry meta");
  if (!Array.isArray(entry.items)) invalid("entry items");
  return { title: entry.title, meta: entry.meta as string[], items: entry.items.map(parseItem) };
}

/** Validate the generated `web/data/model-behavior-changelog.json` shape. */
export function parseChangelogDocument(value: unknown): ChangelogDoc {
  if (!value || typeof value !== "object") invalid("document");
  const doc = value as Record<string, unknown>;
  if (typeof doc.title !== "string" || !doc.title.trim()) invalid("title");
  if (!Array.isArray(doc.intro) || !doc.intro.every((line) => typeof line === "string")) invalid("intro");
  if (!Array.isArray(doc.entries) || !doc.entries.length) invalid("entries");
  return { title: doc.title, intro: doc.intro as string[], entries: doc.entries.map(parseEntry) };
}
