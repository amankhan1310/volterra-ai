import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./msw";
import { installMatchMedia, setViewportWidth } from "./viewport";

installMatchMedia();

beforeAll(() => {
  // Any request without a handler is a test bug: fail loudly instead of hitting the network.
  // (MSW 3 renamed `onUnhandledRequest` to `onUnhandledFrame`.)
  server.listen({ onUnhandledFrame: "error" });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  setViewportWidth(1440);
});

afterAll(() => {
  server.close();
});
