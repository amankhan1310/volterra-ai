import { describe, expect, it } from "vitest";
import {
  NAV_GROUPS,
  PAGES,
  findPageByPath,
  getPage,
  pathForLegacyHash,
  type PageKey,
} from "./pages";

describe("pages", () => {
  it("lists the six legacy pages in the legacy quick-navigation order", () => {
    expect(PAGES.map((p) => p.label)).toEqual([
      "Overview",
      "Digital Twin",
      "What-If Simulator",
      "Anomaly Detection",
      "Charging Advisor",
      "About",
    ]);
  });

  it("keeps the legacy sidebar groups, each page exactly once", () => {
    expect(NAV_GROUPS.map((g) => [g.group, g.keys])).toEqual([
      ["Monitor", ["overview", "digital", "anom"]],
      ["Plan", ["sim", "advisor"]],
      ["Project", ["about"]],
    ]);
    const keys = NAV_GROUPS.flatMap((g) => g.keys).sort();
    expect(keys).toEqual(PAGES.map((p) => p.key).sort());
  });

  it("assigns every page to its approved milestone", () => {
    expect(Object.fromEntries(PAGES.map((p) => [p.key, p.milestone]))).toEqual({
      overview: 2,
      digital: 3,
      sim: 4,
      anom: 5,
      advisor: 5,
      about: 6,
    });
  });

  it("looks pages up by key and path", () => {
    expect(getPage("sim").path).toBe("/simulator");
    expect(() => getPage("nope" as PageKey)).toThrow("Unknown page: nope");
    expect(findPageByPath("/anomalies")?.key).toBe("anom");
    expect(findPageByPath("/anomalies/")?.key).toBe("anom");
    expect(findPageByPath("/")).toBeUndefined();
    expect(findPageByPath("/missing")).toBeUndefined();
  });

  it("maps legacy hashes to the new routes", () => {
    expect(pathForLegacyHash("#overview")).toBe("/overview");
    expect(pathForLegacyHash("#digital")).toBe("/digital-twin");
    expect(pathForLegacyHash("#sim")).toBe("/simulator");
    expect(pathForLegacyHash("#anom")).toBe("/anomalies");
    expect(pathForLegacyHash("#advisor")).toBe("/advisor");
    expect(pathForLegacyHash("about")).toBe("/about");
    expect(pathForLegacyHash("#unknown")).toBeUndefined();
    expect(pathForLegacyHash("")).toBeUndefined();
  });
});
