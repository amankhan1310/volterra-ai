import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { queryKeys } from "../api/hooks";
import { apiError, fixtures, server } from "../test/msw";
import { renderApp } from "../test/render";
import { PAGES } from "./pages";

const mainNav = () => screen.getByRole("navigation", { name: "Main" });
const breadcrumb = () => screen.getByRole("navigation", { name: "Breadcrumb" });

describe("routing", () => {
  it("redirects / to the Overview", async () => {
    const { router } = renderApp("/");
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Battery Intelligence",
      }),
    ).toBeTruthy();
    expect(router.state.location.pathname).toBe("/overview");
  });

  it.each([
    ["#sim", "/simulator"],
    ["#anom", "/anomalies"],
    ["#digital", "/digital-twin"],
  ])("redirects the legacy bookmark /%s to %s", async (hash, path) => {
    const { router } = renderApp(`/${hash}`);
    await screen.findByRole("heading", { level: 1 });
    expect(router.state.location.pathname).toBe(path);
  });

  it.each(PAGES.map((p) => [p.path, p] as const))(
    "renders %s with the legacy title and a labelled placeholder",
    async (path, page) => {
      renderApp(path);
      expect(
        await screen.findByRole("heading", { level: 1, name: page.title }),
      ).toBeTruthy();
      expect(screen.getByText(page.subtitle)).toBeTruthy();
      expect(within(breadcrumb()).getByText(page.label)).toBeTruthy();
      const link = within(mainNav()).getByRole("link", { name: page.label });
      expect(link.getAttribute("aria-current")).toBe("page");
      const placeholder = await screen.findByTestId("page-placeholder");
      expect(placeholder.textContent).toContain(`Milestone ${page.milestone}`);
      expect(placeholder.textContent).toContain("shows no data yet");
      expect(document.title).toBe(`${page.label} · VOLTERRA AI`);
    },
  );

  it("shows a 404 page for unknown paths", async () => {
    renderApp("/nowhere");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Page not found" }),
    ).toBeTruthy();
    expect(screen.getByText("No page exists at /nowhere.")).toBeTruthy();
    expect(within(breadcrumb()).getByText("Page not found")).toBeTruthy();
    expect(document.title).toBe("Page not found · VOLTERRA AI");
    const select = screen.getByRole<HTMLSelectElement>("combobox", {
      name: "Quick navigation",
    });
    expect(select.value).toBe("");
    expect(
      within(screen.getByRole("main"))
        .getByRole("link", { name: "Overview" })
        .getAttribute("href"),
    ).toBe("/overview");
  });

  it("navigates from the sidebar", async () => {
    const { user, router } = renderApp("/overview");
    await user.click(
      within(mainNav()).getByRole("link", { name: "Charging Advisor" }),
    );
    expect(router.state.location.pathname).toBe("/advisor");
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Charging Advisor",
      }),
    ).toBeTruthy();
  });

  it("navigates from the quick-navigation select", async () => {
    const { user, router } = renderApp("/overview");
    const select = screen.getByRole<HTMLSelectElement>("combobox", {
      name: "Quick navigation",
    });
    expect(select.value).toBe("/overview");
    expect(
      within(select)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(PAGES.map((p) => p.label));
    await user.selectOptions(select, "/anomalies");
    expect(router.state.location.pathname).toBe("/anomalies");
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Anomaly Detection",
      }),
    ).toBeTruthy();
  });
});

describe("header and status (real API fixtures)", () => {
  it("shows the data-source pill, context bar and anomaly badge from the API", async () => {
    renderApp("/overview");
    expect(
      await screen.findByText("Simulated · 2.0 Ah cell profile"),
    ).toBeTruthy();
    expect(
      screen.getByText("Simulated · 2.0 Ah cell profile").getAttribute("title"),
    ).toBe("Seeded synthetic data, not a real vehicle");
    const context = await screen.findByLabelText("Data context");
    expect(context.textContent).toContain("Dataset synthetic-v1");
    expect(context.textContent).toContain(
      `Battery ${fixtures.battery.external_id}`,
    );
    expect(await within(context).findByText("v1")).toBeTruthy();
    expect(context.textContent).toContain("Simulated data");
    const total = fixtures.anomalies.summary.total;
    expect(
      await screen.findByRole("button", {
        name: `Notifications: ${total} anomaly events flagged`,
      }),
    ).toBeTruthy();
  });

  it("shows the legacy status card with the API/database status (U8)", async () => {
    renderApp("/overview");
    const status = screen.getByRole("group", { name: "System status" });
    expect(
      await within(status).findByText("API and database online"),
    ).toBeTruthy();
    expect(within(status).getByText("Simulation mode")).toBeTruthy();
    expect(
      within(status).getByText("Seeded dataset · no vehicle link"),
    ).toBeTruthy();
  });

  it("explains the bell like the prototype", async () => {
    const { user } = renderApp("/overview");
    const total = fixtures.anomalies.summary.total;
    await user.click(
      await screen.findByRole("button", {
        name: `Notifications: ${total} anomaly events flagged`,
      }),
    );
    expect(
      await screen.findByText(
        `${total} anomaly events flagged in the dataset. Open Anomaly Detection to review.`,
      ),
    ).toBeTruthy();
  });

  it("says when the anomaly count is unavailable", async () => {
    server.use(
      http.get("*/api/v1/batteries/:id/anomalies", () =>
        apiError(500, "internal_error", "Internal server error"),
      ),
    );
    const { user, client } = renderApp("/overview");
    await waitFor(() => {
      expect(
        client.getQueryState(queryKeys.anomalies(fixtures.battery.id))?.status,
      ).toBe("error");
    });
    await user.click(screen.getByRole("button", { name: "Notifications" }));
    expect(
      await screen.findByText(
        "Anomaly count unavailable: Internal server error",
      ),
    ).toBeTruthy();
  });

  it("says when the anomaly count is still loading", async () => {
    server.use(
      http.get(
        "*/api/v1/batteries/:id/anomalies",
        () => new Promise<never>(() => undefined),
      ),
    );
    const { user } = renderApp("/overview");
    await screen.findByText("Simulated · 2.0 Ah cell profile");
    await user.click(screen.getByRole("button", { name: "Notifications" }));
    expect(
      await screen.findByText("The anomaly count is still loading."),
    ).toBeTruthy();
  });
});

describe("data states", () => {
  it("shows the loading state, then the placeholder", async () => {
    renderApp("/overview");
    expect(
      screen.getByRole("status", { name: "Loading battery data" }),
    ).toBeTruthy();
    expect(await screen.findByTestId("page-placeholder")).toBeTruthy();
  });

  it("explains an unreachable API, with a working retry", async () => {
    server.use(http.get("*/api/v1/batteries", () => HttpResponse.error()));
    const { user } = renderApp("/overview");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("API unreachable");
    expect(alert.textContent).toContain("uvicorn");
    expect(alert.textContent).toContain("Error code: api_unreachable");
    server.resetHandlers();
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("page-placeholder")).toBeTruthy();
  });

  it("explains an unavailable database", async () => {
    server.use(
      http.get("*/api/v1/batteries", () =>
        apiError(503, "database_unavailable", "The database is not configured"),
      ),
    );
    renderApp("/simulator");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Database unavailable");
    expect(alert.textContent).toContain("The database is not configured");
  });

  it("tells the user to seed an empty database", async () => {
    server.use(
      http.get("*/api/v1/batteries", () => HttpResponse.json({ items: [] })),
    );
    renderApp("/overview");
    expect(await screen.findByText("No battery data")).toBeTruthy();
    expect(
      screen.getByText("cd backend && uv run python -m app.db.seed"),
    ).toBeTruthy();
    const status = screen.getByRole("group", { name: "System status" });
    expect(within(status).getByText("No data")).toBeTruthy();
    expect(screen.queryByLabelText("Data context")).toBeNull();
  });
});
