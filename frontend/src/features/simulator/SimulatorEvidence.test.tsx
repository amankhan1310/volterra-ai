import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ScenarioParams } from "../../api/types";
import { fixtures } from "../../test/msw";
import { renderApp } from "../../test/render";
import { outOfDataRange } from "./SimulatorEvidence";

const text = (el: Element) => el.textContent;
const params = (p: Partial<ScenarioParams>) => ({
  ...fixtures.simulator.defaults,
  ...p,
});

describe("simulator evidence (Phase 8)", () => {
  it("keeps every coefficient assumed and shows the data checks and the baseline validation", async () => {
    renderApp("/simulator");
    const card = await screen.findByTestId("simulator-evidence");
    const t = fixtures.simulatorEvidence.stress.temperature.evidence;
    expect(
      text(await within(card).findByTestId("evidence-temperature")),
    ).toContain("so this is not a calibration");
    expect(text(within(card).getByTestId("evidence-temperature"))).toContain(
      `faded ×${t.observed_ratio.toFixed(2)} faster`,
    );
    expect(text(within(card).getByTestId("evidence-temperature-use"))).toMatch(
      /^exploratory only, not suitable for calibration/,
    );
    expect(text(within(card).getByTestId("evidence-c-rate"))).toContain(
      "Outside the slider's range, so not applied",
    );
    expect(card.querySelectorAll('[data-provenance="assumed"]').length).toBe(3);
    const table = within(card).getByTestId("baseline-validation");
    expect(within(table).getAllByRole("row")).toHaveLength(
      1 +
        Object.keys(fixtures.simulatorEvidence.baseline_validation.results)
          .length,
    );
    expect(text(card)).toContain("not as life predictions");
  });

  it("flags scenarios outside the conditions any dataset covered", () => {
    const e = fixtures.simulatorEvidence;
    const inside = outOfDataRange(params({ temp_c: 30, dod_pct: 100 }), e);
    expect(inside).toHaveLength(1); // C-rate is never covered by the data
    expect(inside[0]).toContain("no dataset varies the cycling C-rate");
    const outside = outOfDataRange(params({ temp_c: 10, dod_pct: 80 }), e);
    expect(outside[0]).toContain("10 °C is outside the 24–43 °C");
    expect(outside.at(-1)).toContain("Depth of discharge: not varied");
  });
});
