/** Shared formatting utilities for numbers and metrics across the VMLU web app.
 *  Enforces Vietnamese locale standards: comma (,) as decimal separator,
 *  dot (.) as thousands separator, and clean delta formatting.
 */

/** Format a number with comma decimal separator and dot thousand separator. */
export function fmtNum(
  value: number | string | null | undefined,
  digits: number = 2,
): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";

  return n.toLocaleString("vi-VN", {
    minimumFractionDigits: Number.isInteger(n) && digits === 0 ? 0 : digits,
    maximumFractionDigits: digits,
  });
}

/** Format an integer count with dot thousands separator (e.g. 1.047). */
export function fmtInt(value: number | string | null | undefined): string {
  return fmtNum(value, 0);
}

/** Format a percentage with % sign and comma decimal (e.g. 73,35%). */
export function fmtPct(
  value: number | string | null | undefined,
  digits: number = 2,
): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  return `${fmtNum(n, digits)}%`;
}

/** Format a delta with sign (+ or -) and comma decimal (e.g. +2,12 or -9,22). */
export function fmtDelta(
  value: number | string | null | undefined,
  digits: number = 2,
): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  const prefix = n > 0 ? "+" : "";
  return `${prefix}${fmtNum(n, digits)}`;
}

/** Format a delta percentage with sign and % (e.g. +2,12% or -9,22%). */
export function fmtDeltaPct(
  value: number | string | null | undefined,
  digits: number = 2,
): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  const prefix = n > 0 ? "+" : "";
  return `${prefix}${fmtNum(n, digits)}%`;
}
