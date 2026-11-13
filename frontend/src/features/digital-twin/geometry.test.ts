import { describe, expect, it } from "vitest";
import { miniChartGeometry } from "../../components/charts/MiniLineChart";
import { fixtures } from "../../test/msw";
import { LEGEND, packColor } from "./DigitalTwinPage";
import { moduleFaces, platePoints, project } from "./geometry";
import { moduleMessage } from "./PackStatePanel";

describe("isometric pack geometry (prototype Q())", () => {
  it("projects with one decimal", () => {
    expect(project(0, 0, 0)).toBe("0.0,0.0");
    expect(project(40, 0, 26)).toBe("34.6,-6.0");
    expect(project(-10, 194, 0)).toBe("-176.7,92.0");
  });

  it("draws the prototype's 24-module base plate", () => {
    expect(platePoints(24)).toBe(
      "0.0,-10.0 259.8,140.0 83.1,242.0 -176.7,92.0",
    );
    expect(platePoints(0)).toBe(platePoints(6));
  });

  it("places modules six per row on a 48-unit pitch", () => {
    expect(moduleFaces(0).top).toBe(
      `${project(0, 0, 26)} ${project(40, 0, 26)} ${project(40, 40, 26)} ${project(0, 40, 26)}`,
    );
    expect(moduleFaces(7).left).toBe(
      `${project(48, 88, 0)} ${project(88, 88, 0)} ${project(88, 88, 26)} ${project(48, 88, 26)}`,
    );
    expect(moduleFaces(23).right).toContain(project(280, 144, 0));
  });
});

describe("pack colours and text", () => {
  it("colours by the API's health level or temperature band", () => {
    const latest = fixtures.twin[319];
    const warm = fixtures.twin[170];
    if (!latest || !warm) throw new Error("fixture missing");
    expect(packColor(latest, "soh")).toBe("var(--gr)");

    expect(packColor(warm, "temp")).toBe("var(--am)");
    expect(packColor({ ...warm, temperature_band: "hot" }, "temp")).toBe(
      "var(--rd)",
    );
    expect(packColor({ ...warm, health_level: "caution" }, "soh")).toBe(
      "var(--am)",
    );
    expect(LEGEND.temp.map((r) => r.label)).toEqual([
      "< 30 °C",
      "30–40 °C",
      "> 40 °C",
    ]);
  });

  it("explains a selected module honestly", () => {
    expect(moduleMessage(null)).toBe("No module selected.");
    expect(moduleMessage(4)).toBe(
      "Module 5: no cell-level measurement exists, so this shows the pack value (illustrative).",
    );
  });
});

describe("mini chart geometry (prototype chart())", () => {
  it("pads the data range by 8% and labels five grid lines", () => {
    const g = miniChartGeometry([90, 100], { height: 150, cursor: 1 });
    expect(g.grid.map((l) => l.label)).toEqual([
      "89.2",
      "92.1",
      "95.0",
      "97.9",
      "100.8",
    ]);
    expect(g.path).toBe("M44.0 119.9L708.0 18.1");
    expect(g.cursorX).toBe(708);
    expect(g.lastIndex).toBe(1);
  });

  it("handles flat and empty series", () => {
    const flat = miniChartGeometry([5, 5, 5], { height: 100 });
    expect(flat.grid[0]?.label).toBe("4.0");
    expect(flat.cursorX).toBeNull();
    expect(miniChartGeometry([], { height: 100 }).path).toBe("");
    expect(miniChartGeometry([3], { height: 100 }).path).toBe("M44.0 44.0");
  });
});
