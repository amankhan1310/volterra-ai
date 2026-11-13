import { act, screen, waitFor, within } from "@testing-library/react";
import { http } from "msw";
import { describe, expect, it } from "vitest";
import { apiError, server } from "../test/msw";
import { renderApp } from "../test/render";
import { setViewportWidth } from "../test/viewport";

const sidebar = () =>
  screen.getByRole("complementary", { name: "Sidebar", hidden: true });

describe("desktop sidebar", () => {
  it("collapses to icons and expands again", async () => {
    const { user } = renderApp("/overview");
    expect(sidebar().getAttribute("data-collapsed")).toBe("false");
    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(sidebar().getAttribute("data-collapsed")).toBe("true");
    // Collapsed links keep their names and gain a hover tooltip.
    const link = within(sidebar()).getByRole("link", {
      name: "Anomaly Detection",
    });
    expect(link.getAttribute("title")).toBe("Anomaly Detection");
    await user.click(screen.getByRole("button", { name: "Expand sidebar" }));
    expect(sidebar().getAttribute("data-collapsed")).toBe("false");
  });

  it("is never inert on desktop", () => {
    renderApp("/overview");
    expect(sidebar().hasAttribute("inert")).toBe(false);
  });
});

describe("mobile drawer (≤ 860px)", () => {
  it("is closed and inert until the burger opens it", async () => {
    setViewportWidth(390);
    const { user } = renderApp("/overview");
    expect(sidebar().hasAttribute("inert")).toBe(true);
    const burger = screen.getByRole("button", { name: "Open menu" });
    expect(burger.getAttribute("aria-expanded")).toBe("false");
    await user.click(burger);
    expect(sidebar().hasAttribute("inert")).toBe(false);
    expect(
      screen
        .getByRole("button", { name: "Close menu" })
        .getAttribute("aria-expanded"),
    ).toBe("true");
  });

  it("closes after navigating, like the legacy router", async () => {
    setViewportWidth(390);
    const { user, router } = renderApp("/overview");
    await user.click(screen.getByRole("button", { name: "Open menu" }));
    await user.click(within(sidebar()).getByRole("link", { name: "About" }));
    expect(router.state.location.pathname).toBe("/about");
    expect(sidebar().hasAttribute("inert")).toBe(true);
  });

  it("closes on Escape and on the backdrop", async () => {
    setViewportWidth(390);
    const { user, container } = renderApp("/overview");
    await user.click(screen.getByRole("button", { name: "Open menu" }));
    await user.keyboard("{Escape}");
    expect(sidebar().hasAttribute("inert")).toBe(true);

    await user.click(screen.getByRole("button", { name: "Open menu" }));
    const backdrop = container.querySelector(
      '[aria-hidden="true"][class*="backdrop"]',
    );
    expect(backdrop).not.toBeNull();
    await user.click(backdrop as Element);
    expect(sidebar().hasAttribute("inert")).toBe(true);
  });

  it("ignores other keys while open", async () => {
    setViewportWidth(390);
    const { user } = renderApp("/overview");
    await user.click(screen.getByRole("button", { name: "Open menu" }));
    await user.keyboard("x"); // focus is on the burger; Enter/Space would activate it
    expect(sidebar().hasAttribute("inert")).toBe(false);
  });

  it("follows the viewport when it crosses the breakpoint", () => {
    renderApp("/overview");
    expect(sidebar().hasAttribute("inert")).toBe(false);
    act(() => {
      setViewportWidth(800);
    });
    expect(sidebar().hasAttribute("inert")).toBe(true);
  });

  it("closes the drawer when navigating with quick navigation", async () => {
    setViewportWidth(390);
    const { user, router } = renderApp("/overview");
    await user.click(screen.getByRole("button", { name: "Open menu" }));
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Quick navigation" }),
      "/simulator",
    );
    expect(router.state.location.pathname).toBe("/simulator");
    expect(sidebar().hasAttribute("inert")).toBe(true);
  });
});

describe("accessibility helpers", () => {
  it("moves focus to the main content from the skip link", async () => {
    const { user } = renderApp("/overview");
    await user.click(screen.getByRole("link", { name: "Skip to content" }));
    expect(document.activeElement).toBe(screen.getByRole("main"));
  });

  it("scrolls the main area back to the top on navigation", async () => {
    const { user } = renderApp("/overview");
    const main = screen.getByRole("main");
    main.scrollTop = 500;
    await user.click(within(sidebar()).getByRole("link", { name: "About" }));
    await waitFor(() => {
      expect(main.scrollTop).toBe(0);
    });
  });
});

describe("status indicator (U8)", () => {
  it("reports an unreachable API", async () => {
    server.use(
      http.get("*/api/v1/health", () => new Response("", { status: 502 })),
    );
    renderApp("/overview");
    const status = screen.getByRole("group", { name: "System status" });
    expect(await within(status).findByText("API unreachable")).toBeTruthy();
  });

  it("reports a database problem while the API is up", async () => {
    server.use(
      http.get("*/api/v1/health", () =>
        Response.json({
          status: "ok",
          version: "0.3.0",
          database: {
            status: "unavailable",
            latency_ms: null,
            error: "OSError",
          },
        }),
      ),
    );
    renderApp("/overview");
    const status = screen.getByRole("group", { name: "System status" });
    expect(
      await within(status).findByText("API online · database unavailable"),
    ).toBeTruthy();
  });

  it("keeps working when only some requests fail", async () => {
    server.use(
      http.get("*/api/v1/batteries", () =>
        apiError(503, "database_unavailable", "down"),
      ),
    );
    renderApp("/overview");
    expect(await screen.findByRole("alert")).toBeTruthy();
    const status = screen.getByRole("group", { name: "System status" });
    expect(
      await within(status).findByText("API and database online"),
    ).toBeTruthy();
    expect(within(status).getByText("Data source")).toBeTruthy();
  });
});
