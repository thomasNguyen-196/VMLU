/** Bucket-identity slug — MUST stay identical to the static fallback template's
 *  JS `slug()` (and stayed identical to rev-1's Python): lowercase, NFD-strip
 *  combining diacritics (U+0300–U+036F = the template's literal ̀-ͯ range),
 *  non-alnum runs -> '_', trim '_'. CI asserts parity both ways
 *  (code_benchmark/test_suite.py :: TestNextContracts). */
export function slug(s: string): string {
  return s
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}
