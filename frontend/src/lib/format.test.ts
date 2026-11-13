import { describe, expect, it } from "vitest";
import { HEALTH_COLOR } from "./health";
import { finite, fixed, round2, roundedOr } from "./format";

describe("formatters", () => {
  it("treats null, undefined and the API's non-finite strings as missing", () => {
    for (const v of [
      null,
      undefined,
      NaN,
      Infinity,
      "NaN",
      "Infinity",
      "-Infinity",
    ])
      expect(finite(v)).toBeNull();
    expect(finite("1.5")).toBe(1.5);
    expect(finite(0)).toBe(0);
  });

  it("formats with toFixed, as the prototype did", () => {
    expect(fixed(86.08941987140724, 1)).toBe("86.1");
    expect(fixed(0.05401766159185438, 3)).toBe("0.054");
    expect(fixed(1.005, 2)).toBe((1.005).toFixed(2));
    expect(fixed("NaN", 2)).toBe("n/a");
    expect(fixed(null, 2, "–")).toBe("–");
  });

  it("rounds like `x ? Math.round(x) : fallback`, so 0 is not a value", () => {
    expect(roundedOr(112.73016439359348, "n/a")).toBe("113");
    expect(roundedOr(111.46112593857329, "–")).toBe("111");
    expect(roundedOr(0, "n/a")).toBe("n/a");
    expect(roundedOr(null, "–")).toBe("–");
    expect(roundedOr("Infinity", "n/a")).toBe("n/a");
  });

  it("rounds chart values to two decimals", () => {
    expect(round2(99.8966312480066)).toBe(99.9);
    expect(round2(86.08941987140724)).toBe(86.09);
  });

  it("maps every API health level to a token", () => {
    expect(HEALTH_COLOR).toEqual({
      healthy: "var(--gr)",
      caution: "var(--am)",
      critical: "var(--rd)",
    });
  });
});
