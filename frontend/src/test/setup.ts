import { cleanup, configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { charts } from "./echartsMock";
import { resetScenarioStore, server } from "./msw";
import { installMatchMedia, setViewportWidth } from "./viewport";

// jsdom has no canvas: every chart gets the recording fake (see echartsMock.ts).
vi.mock("../components/charts/echarts", () => import("./echartsMock"));

installMatchMedia();

// Pages are lazy-loaded routes. Under the full parallel run with v8 coverage, the first test of a
// file waits for that page's cold transform, which can exceed the 1 s default for findBy*/waitFor
// (and, from M5's 19 files, 3 s). Only the wait is longer; a missing element still fails.
configure({ asyncUtilTimeout: 10000 });

beforeAll(() => {
  // Any request without a handler is a test bug: fail loudly instead of hitting the network.
  // (MSW 3 renamed `onUnhandledRequest` to `onUnhandledFrame`.)
  server.listen({ onUnhandledFrame: "error" });
});

afterEach(() => {
  cleanup();
  charts.length = 0;
  server.resetHandlers();
  resetScenarioStore();
  setViewportWidth(1440);
  // Every test starts in the first-visit theme (dark, nothing saved).
  document.documentElement.setAttribute("data-theme", "dark");
  localStorage.clear();
});

afterAll(() => {
  server.close();
});
