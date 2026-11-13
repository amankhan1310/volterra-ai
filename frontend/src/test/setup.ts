import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { charts } from "./echartsMock";
import { server } from "./msw";
import { installMatchMedia, setViewportWidth } from "./viewport";

// jsdom has no canvas: every chart gets the recording fake (see echartsMock.ts).
vi.mock("../components/charts/echarts", () => import("./echartsMock"));

installMatchMedia();

beforeAll(() => {
  // Any request without a handler is a test bug: fail loudly instead of hitting the network.
  // (MSW 3 renamed `onUnhandledRequest` to `onUnhandledFrame`.)
  server.listen({ onUnhandledFrame: "error" });
});

afterEach(() => {
  cleanup();
  charts.length = 0;
  server.resetHandlers();
  setViewportWidth(1440);
});

afterAll(() => {
  server.close();
});
