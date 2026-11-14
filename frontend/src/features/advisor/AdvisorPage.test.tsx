import { screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { useScenarioDraft } from "../../state/ScenarioDraftContext";
import { apiError, fixtures, server } from "../../test/msw";
import { renderApp, renderWithProviders } from "../../test/render";
import {
  AdvisorPage,
  barGeometry,
  baselineLabel,
  compareNotice,
  deltaText,
} from "./AdvisorPage";

const content = () => screen.findByTestId("page-content");
const rowValues = () =>
  screen
    .getAllByTestId("advisor-row")
    .map((r) => [
      within(r).getByRole("img").getAttribute("aria-label"),
      within(r).getByTestId("advisor-cycles").textContent,
      within(r).getByTestId("advisor-delta").textContent,
    ]);

/** Moves the shared EOL and initial SOH, as the What-If Simulator page does (D1). */
function MoveDraft({ eol, start }: { eol: number; start: number }) {
  const draft = useScenarioDraft();
  return (
    <button
      type="button"
      onClick={() => {
        draft.setParam("eol_pct", eol);
        draft.setParam("start_soh_pct", start);
      }}
    >
      Move draft
    </button>
  );
}

function recordAdvisorRequests(): string[] {
  const requested: string[] = [];
  server.events.on("request:start", ({ request }) => {
    const url = new URL(request.url);
    if (url.pathname.endsWith("/advisor"))
      requested.push(
        `${url.searchParams.get("eol_pct") ?? ""}|${url.searchParams.get("start_soh_pct") ?? ""}`,
      );
  });
  return requested;
}

describe("advisor helpers", () => {
  it("draws the prototype's diverging bar: half of |Δ%|, capped at 50", () => {
    expect(barGeometry(73.58)).toEqual({
      left: 50,
      width: 36.79,
      positive: true,
    });
    expect(barGeometry(-43.4)).toEqual({
      left: 28.3,
      width: 21.7,
      positive: false,
    });
    expect(barGeometry(250)).toEqual({ left: 50, width: 50, positive: true });
    expect(barGeometry(-250)).toEqual({ left: 0, width: 50, positive: false });
    expect(barGeometry(0)).toEqual({ left: 50, width: 0, positive: true });
  });

  it("formats Δ% with the prototype's sign and colour rule", () => {
    expect(deltaText(73.58)).toEqual({ text: "+74%", color: "var(--gr)" });
    expect(deltaText(-16.98)).toEqual({ text: "-17%", color: "var(--rd)" });
    // The prototype shows a zero change in red, without a sign.
    expect(deltaText(0)).toEqual({ text: "0%", color: "var(--rd)" });
  });

  it("explains a change that cannot be compared, in plain language (D4)", () => {
    expect(compareNotice(184)).toBeNull();
    expect(compareNotice(null)).toBe("Beyond 5000 cycles · change shown as 0%");
    expect(compareNotice(0)).toBe(
      "Already at end of life · change shown as 0%",
    );
    expect(compareNotice(0, "every change")).toBe(
      "Already at end of life · every change shown as 0%",
    );
  });

  it("labels the baseline from the API's conditions", () => {
    expect(baselineLabel(fixtures.advisor)).toBe(
      "Baseline · 25 °C · 1C · 80% DoD from 86.1% SOH",
    );
  });
});

describe("Charging Advisor against the recorded API", () => {
  it("shows the prototype's baseline and six rows at the defaults", async () => {
    renderApp("/advisor");
    const card = await content();
    expect(screen.getByTestId("advisor-baseline-label").textContent).toBe(
      "Baseline · 25 °C · 1C · 80% DoD from 86.1% SOH",
    );
    expect(screen.getByTestId("advisor-baseline").textContent).toBe(
      "106cycles to 80% SOH",
    );
    expect(rowValues()).toEqual([
      ["+74% versus baseline", "184", "+74%"],
      ["-43% versus baseline", "60", "-43%"],
      ["+23% versus baseline", "130", "+23%"],
      ["-27% versus baseline", "77", "-27%"],
      ["+27% versus baseline", "135", "+27%"],
      ["-17% versus baseline", "88", "-17%"],
    ]);
    const rows = screen.getAllByTestId("advisor-row");
    expect(rows[0]?.textContent).toContain("Cooler: 15 °C");
    expect(rows[0]?.textContent).toContain(
      "Lower temperature slows modelled fade",
    );
    const bars = screen.getAllByTestId("advisor-bar");
    expect(bars[0]?.style.left).toBe(`${String(50)}%`);
    expect(bars[0]?.style.background).toBe("var(--gr)");
    expect(bars[1]?.style.background).toBe("var(--rd)");
    expect(
      within(card)
        .getByText("Simulated estimate")
        .getAttribute("data-provenance"),
    ).toBe("simulated");
    expect(
      within(card)
        .getByText("Coefficients assumed")
        .getAttribute("data-provenance"),
    ).toBe("assumed");
    expect(screen.queryByText(/set in the Simulator/)).toBeNull();
    expect(screen.queryByTestId("advisor-baseline-notice")).toBeNull();
    expect(screen.queryAllByTestId("advisor-row-notice")).toHaveLength(0);
    expect(screen.getByText(fixtures.advisor.note)).toBeTruthy();
  });

  it("follows the shared EOL and initial SOH, with both chips (D1, U1)", async () => {
    const requested = recordAdvisorRequests();
    const { user } = renderWithProviders(
      <>
        <MoveDraft eol={70} start={90} />
        <AdvisorPage />
      </>,
    );
    await content();
    await user.click(screen.getByRole("button", { name: "Move draft" }));
    await waitFor(() => {
      expect(screen.getByTestId("advisor-baseline").textContent).toBe(
        "308cycles to 70% SOH",
      );
    });
    expect(screen.getByTestId("advisor-baseline-label").textContent).toBe(
      "Baseline · 25 °C · 1C · 80% DoD from 90% SOH",
    );
    expect(rowValues()[0]).toEqual(["+64% versus baseline", "505", "+64%"]);
    expect(
      screen.getByText("EOL threshold 70% · set in the Simulator"),
    ).toBeTruthy();
    expect(
      screen.getByText("Initial SOH 90% · set in the Simulator"),
    ).toBeTruthy();
    expect(requested).toEqual(["80|86.1", "70|90"]);
    server.events.removeAllListeners();
  });

  it("says once, on the baseline, when nothing can be compared (D4)", async () => {
    const { user } = renderWithProviders(
      <>
        <MoveDraft eol={90} start={85} />
        <AdvisorPage />
      </>,
    );
    await content();
    await user.click(screen.getByRole("button", { name: "Move draft" }));
    await waitFor(() => {
      expect(screen.getByTestId("advisor-baseline").textContent).toBe(
        "0cycles to 90% SOH",
      );
    });
    expect(screen.getByTestId("advisor-baseline-notice").textContent).toBe(
      "Already at end of life · every change shown as 0%",
    );
    expect(screen.queryAllByTestId("advisor-row-notice")).toHaveLength(0);
    expect(rowValues().every(([, n, d]) => n === "0" && d === "0%")).toBe(true);
  });

  it("marks a single row that cannot be compared", async () => {
    server.use(
      http.get("*/api/v1/batteries/:id/advisor", () =>
        HttpResponse.json({
          ...fixtures.advisor,
          rows: fixtures.advisor.rows.map((r, i) =>
            i === 0 ? { ...r, cycles_to_eol: null, delta_pct: 0 } : r,
          ),
        }),
      ),
    );
    renderApp("/advisor");
    await content();
    const notices = screen.getAllByTestId("advisor-row-notice");
    expect(notices).toHaveLength(1);
    expect(notices[0]?.textContent).toBe(
      "Beyond 5000 cycles · change shown as 0%",
    );
    expect(rowValues()[0]).toEqual(["0% versus baseline", ">5000", "0%"]);
  });

  it("keeps the limits collapsed, in plain language without defect codes (U3, D4)", async () => {
    renderApp("/advisor");
    await content();
    const details = screen.getByText("About these results").closest("details");
    expect(details?.open).toBe(false);
    expect(details?.textContent).toContain("beyond 5000 cycles");
    expect(details?.textContent).toContain("assumed coefficients");
    expect(details?.textContent).not.toMatch(/\bF\d\b/);
  });
});

describe("Charging Advisor data states", () => {
  it("shows the API error with a retry", async () => {
    let fail = true;
    server.use(
      http.get("*/api/v1/batteries/:id/advisor", () =>
        fail
          ? apiError(
              503,
              "database_unavailable",
              "The database is not configured",
            )
          : HttpResponse.json(fixtures.advisor),
      ),
    );
    const { user } = renderApp("/advisor");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Database unavailable");
    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await content()).toBeTruthy();
  });

  it("shows a skeleton while loading", async () => {
    renderApp("/advisor");
    expect(
      await screen.findByRole("status", {
        name: "Loading the charging advisor",
      }),
    ).toBeTruthy();
    await content();
  });
});
