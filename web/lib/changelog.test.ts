import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { parseChangelog, parseChangelogDocument, parseInline } from "./changelog.ts";

const markdown = readFileSync(new URL("../../docs/model-behavior-changelog.md", import.meta.url), "utf-8");
const artifact = JSON.parse(readFileSync(new URL("../data/model-behavior-changelog.json", import.meta.url), "utf-8"));

describe("model behavior changelog", () => {
  test("parses the live document into dated entries", () => {
    const doc = parseChangelog(markdown);
    expect(doc.title).toBe("Model behavior changelog");
    expect(doc.entries.length).toBeGreaterThanOrEqual(4);
    const first = doc.entries[0];
    expect(first.title).toContain("MiMo V2.6 Flash");
    expect(first.meta.join(" ")).toContain("Điều kiện");
    expect(first.meta.join(" ")).toContain("Bằng chứng");
    const categories = new Set(first.items.map((item) => item.category));
    expect(categories.has("model")).toBe(true);
    expect(categories.has("harness")).toBe(true);
    expect(first.items.some((item) => item.text.includes("AttributeError"))).toBe(true);
    expect(first.items.some((item) => item.text.includes("20.000 completion token"))).toBe(true);
  });

  test("keeps the historical tail as its own entry", () => {
    const doc = parseChangelog(markdown);
    const history = doc.entries.find((entry) => entry.title.startsWith("Lịch sử"));
    expect(history).toBeDefined();
    expect(history!.items.some((item) => item.text.includes("mc80-incomplete-response-diagnosis"))).toBe(true);
  });

  test("untagged bullets stay in the other bucket", () => {
    const doc = parseChangelog(markdown);
    const first = doc.entries[0];
    const status = first.items.find((item) => item.text.startsWith("**Trạng thái:**"));
    expect(status?.category).toBe("other");
  });

  test("generated artifact matches the markdown source", () => {
    expect(parseChangelogDocument(artifact)).toEqual(parseChangelog(markdown));
  });

  test("parseInline splits bold and code spans", () => {
    const segments = parseInline("**bold** và `code` x");
    expect(segments).toEqual([
      { kind: "bold", value: "bold" },
      { kind: "text", value: " và " },
      { kind: "code", value: "code" },
      { kind: "text", value: " x" },
    ]);
  });
});
