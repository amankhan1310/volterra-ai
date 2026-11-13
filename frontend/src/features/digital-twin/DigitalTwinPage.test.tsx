import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { apiError, fixtures, server } from "../../test/msw";
import { renderApp } from "../../test/render";

const panel = () => screen.findByTestId("page-content");
const slider = () =>
  screen.getByRole<HTMLInputElement>("slider", { name: /Cycle/ });
const topFill = (button: HTMLElement) =>
  button.querySelectorAll("polygon")[2]?.getAttribute("fill");

function recordTwinRequests(): string[] {
  const cycles: string[] = [];
  server.events.on("request:start", ({ request }) => {
    const url = new URL(request.url);
    if (url.pathname.endsWith("/twin"))
      cycles.push(url.searchParams.get("cycle") ?? "latest");
  });
  return cycles;
}

describe("Digital Twin against the recorded API", () => {
  it("opens on the latest cycle with the prototype's values", async () => {
    renderApp("/digital-twin");
    const p = await panel();
    expect(p.textContent).toContain("Pack state at cycle 319");
    const stats = within(p).getByTestId("pack-stats").textContent;
    for (const v of ["85.9%", "1.717Ah", "26.4°C", "3.66V"])
      expect(stats).toContain(v);
    expect(
      within(p)
        .getAllByText(/^(Simulated|Pack-level)$/)
        .map((t) => [t.textContent, t.getAttribute("data-provenance")]),
    ).toEqual([
      ["Simulated", "simulated"],
      ["Pack-level", null],
    ]);
    expect(within(p).getByTestId("module-message").textContent).toBe(
      "No module selected.",
    );
    expect(
      within(p).getByRole("img", {
        name: "SOH over 320 cycles, with cycle 319 marked.",
      }),
    ).toBeTruthy();
    expect(slider().value).toBe("319");
    expect(slider().max).toBe("319");
    expect(screen.getByTestId("cycle-value").textContent).toBe("319");
    const pack = screen.getByRole("group", {
      name: "Isometric battery pack of 24 illustrative modules",
    });
    const modules = within(pack).getAllByRole("button");
    expect(modules).toHaveLength(24);
    expect(topFill(modules[0] as HTMLElement)).toBe("var(--gr)");
    expect(
      screen.getByText(/All 24 modules are drawn from the pack value/),
    ).toBeTruthy();
    expect(screen.getByText("≥ 85% healthy")).toBeTruthy();
  });

  it("debounces the slider: the label moves at once, the API is asked for the final cycle only", async () => {
    const requested = recordTwinRequests();
    renderApp("/digital-twin");
    await panel();
    fireEvent.change(slider(), { target: { value: "150" } });
    fireEvent.change(slider(), { target: { value: "160" } });
    expect(screen.getByTestId("cycle-value").textContent).toBe("160");
    await waitFor(() => {
      expect(screen.getByTestId("page-content").textContent).toContain(
        "Pack state at cycle 160",
      );
    });
    expect(screen.getByTestId("pack-stats").textContent).toContain("94.1%");
    expect(requested).toEqual(["319", "160"]);
    server.events.removeAllListeners();
  });

  it("colours modules by temperature band in Temperature mode", async () => {
    const { user } = renderApp("/digital-twin");
    await panel();
    fireEvent.change(slider(), { target: { value: "170" } });
    await waitFor(() => {
      expect(screen.getByTestId("page-content").textContent).toContain(
        "Pack state at cycle 170",
      );
    });
    const modes = screen.getByRole("group", { name: "Colour modules by" });
    await user.click(
      within(modes).getByRole("button", { name: "Temperature" }),
    );
    const first = screen.getByRole("button", { name: "Module 1" });
    expect(topFill(first)).toBe("var(--am)");
    expect(screen.getByText("30–40 °C")).toBeTruthy();
    await user.click(within(modes).getByRole("button", { name: "Health" }));
    expect(topFill(first)).toBe("var(--gr)");
  });

  it("selects a module by click, Enter or Space", async () => {
    const { user } = renderApp("/digital-twin");
    await panel();
    const third = screen.getByRole("button", { name: "Module 3" });
    await user.click(third);
    expect(third.getAttribute("aria-pressed")).toBe("true");
    expect(third.getAttribute("data-selected")).toBe("true");
    expect(screen.getByTestId("module-message").textContent).toContain(
      "Module 3: no cell-level measurement",
    );
    const fifth = screen.getByRole("button", { name: "Module 5" });
    fifth.focus();
    await user.keyboard("{Enter}");
    expect(fifth.getAttribute("aria-pressed")).toBe("true");
    expect(third.getAttribute("aria-pressed")).toBe("false");
    const sixth = screen.getByRole("button", { name: "Module 6" });
    sixth.focus();
    await user.keyboard(" ");
    expect(screen.getByTestId("module-message").textContent).toContain(
      "Module 6:",
    );
    sixth.focus();
    await user.keyboard("a");
    expect(sixth.getAttribute("aria-pressed")).toBe("true");
  });

  it("Reset view returns to the latest cycle and clears the selection", async () => {
    const { user } = renderApp("/digital-twin");
    await panel();
    await user.click(screen.getByRole("button", { name: "Module 2" }));
    fireEvent.change(slider(), { target: { value: "0" } });
    await waitFor(() => {
      expect(screen.getByTestId("page-content").textContent).toContain(
        "Pack state at cycle 0",
      );
    });
    await user.click(screen.getByRole("button", { name: "Reset view" }));
    expect(
      await screen.findByText("View reset to the latest cycle"),
    ).toBeTruthy();
    expect(slider().value).toBe("319");
    await waitFor(() => {
      expect(screen.getByTestId("page-content").textContent).toContain(
        "Pack state at cycle 319",
      );
    });
    expect(screen.getByTestId("module-message").textContent).toBe(
      "No module selected.",
    );
  });
});

describe("Digital Twin data states", () => {
  it("keeps the last good state when a slider request fails", async () => {
    server.use(
      http.get("*/api/v1/batteries/:id/twin", ({ request }) => {
        const cycle = new URL(request.url).searchParams.get("cycle");
        return cycle === "160"
          ? apiError(422, "cycle_out_of_range", "Cycle 160 not found")
          : HttpResponse.json(fixtures.twin[319]);
      }),
    );
    renderApp("/digital-twin");
    await panel();
    fireEvent.change(slider(), { target: { value: "160" } });
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Could not load cycle 160");
    expect(alert.textContent).toContain(
      "Could not load cycle 160 (Cycle 160 not found). Showing cycle 319.",
    );
    expect(screen.getByTestId("page-content").textContent).toContain(
      "Pack state at cycle 319",
    );
  });

  it("shows the API error with a retry when the first load fails", async () => {
    let fail = true;
    server.use(
      http.get("*/api/v1/batteries/:id/twin", () =>
        fail
          ? apiError(
              503,
              "database_unavailable",
              "The database is not configured",
            )
          : HttpResponse.json(fixtures.twin[319]),
      ),
    );
    const { user } = renderApp("/digital-twin");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Database unavailable");
    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await panel()).toBeTruthy();
  });

  it("shows a skeleton while loading", async () => {
    renderApp("/digital-twin");
    expect(
      await screen.findByRole("status", { name: "Loading the digital twin" }),
    ).toBeTruthy();
    await panel();
  });
});
