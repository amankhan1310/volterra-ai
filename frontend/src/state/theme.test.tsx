import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderApp } from "../test/render";
import { THEME_STORAGE_KEY, applyTheme, currentTheme } from "./theme";

const root = () => document.documentElement;
const toggle = () => screen.getByRole("button", { name: "Light theme" });

describe("theme (D2)", () => {
  it("is dark on a first visit", async () => {
    renderApp("/about");
    await screen.findByTestId("page-content");
    expect(currentTheme()).toBe("dark");
    expect(toggle().getAttribute("aria-pressed")).toBe("false");
    expect(toggle().getAttribute("title")).toBe("Switch to light theme");
  });

  it("switches to light and back from the header, remembering the choice", async () => {
    const { user } = renderApp("/about");
    await screen.findByTestId("page-content");
    await user.click(toggle());
    expect(root().getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(toggle().getAttribute("aria-pressed")).toBe("true");
    expect(toggle().getAttribute("title")).toBe("Switch to dark theme");
    await user.click(toggle());
    expect(root().getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("keeps the theme across in-app navigation", async () => {
    const { user, router } = renderApp("/about");
    await screen.findByTestId("page-content");
    await user.click(toggle());
    await router.navigate("/advisor");
    await screen.findByRole("heading", { level: 1, name: "Charging Advisor" });
    expect(root().getAttribute("data-theme")).toBe("light");
    expect(toggle().getAttribute("aria-pressed")).toBe("true");
  });

  it("starts in the theme already applied to the document (saved choice)", async () => {
    root().setAttribute("data-theme", "light");
    renderApp("/about");
    await screen.findByTestId("page-content");
    expect(toggle().getAttribute("aria-pressed")).toBe("true");
  });

  it("updates the browser theme colour from the background token", () => {
    const meta = document.createElement("meta");
    meta.name = "theme-color";
    meta.content = "";
    document.head.appendChild(meta);
    root().style.setProperty("--bg", "#abcdef");
    applyTheme("light");
    expect(meta.content).toBe("#abcdef");
    root().style.removeProperty("--bg");
    meta.remove();
  });

  it("still applies the theme when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    applyTheme("light");
    expect(currentTheme()).toBe("light");
  });
});
