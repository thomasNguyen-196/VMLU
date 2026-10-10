import { describe, expect, it } from "bun:test";
import { fmtDelta, fmtDeltaPct, fmtInt, fmtNum, fmtPct } from "./format.ts";

describe("format utilities (vi-VN locale)", () => {
  it("formats decimal numbers with comma", () => {
    expect(fmtNum(73.35, 2)).toBe("73,35");
    expect(fmtNum(12488.5, 1)).toBe("12.488,5");
    expect(fmtNum(null)).toBe("—");
  });

  it("formats integers with dot thousands separator", () => {
    expect(fmtInt(1047)).toBe("1.047");
    expect(fmtInt(12488)).toBe("12.488");
    expect(fmtInt("400")).toBe("400");
  });

  it("formats percentages with comma", () => {
    expect(fmtPct(73.35, 2)).toBe("73,35%");
    expect(fmtPct(100, 0)).toBe("100%");
  });

  it("formats deltas with correct sign and comma", () => {
    expect(fmtDelta(2.12, 2)).toBe("+2,12");
    expect(fmtDelta(-9.22, 2)).toBe("-9,22");
    expect(fmtDelta(0, 2)).toBe("0,00");
    expect(fmtDeltaPct(2.12, 2)).toBe("+2,12%");
  });
});
