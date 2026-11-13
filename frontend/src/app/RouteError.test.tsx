import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { RouteError } from "./RouteError";

function Boom(): never {
  throw new Error("render exploded");
}

function renderFailing(element: React.ReactNode) {
  const router = createMemoryRouter([
    { path: "/", element, errorElement: <RouteError /> },
  ]);
  return render(<RouterProvider router={router} />);
}

describe("RouteError", () => {
  it("shows the error and offers a reload", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const reload = vi.fn();
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { href: original.href, origin: original.origin, reload },
    });
    try {
      renderFailing(<Boom />);
      const alert = await screen.findByRole("alert");
      expect(alert.textContent).toContain("Something went wrong");
      expect(alert.textContent).toContain("render exploded");
      await userEvent.click(screen.getByRole("button", { name: "Retry" }));
      expect(reload).toHaveBeenCalledTimes(1);
    } finally {
      Object.defineProperty(window, "location", {
        configurable: true,
        value: original,
      });
    }
  });

  it("handles non-Error values", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    function Throws(): never {
      // eslint-disable-next-line @typescript-eslint/only-throw-error -- deliberately not an Error
      throw "plain string";
    }
    renderFailing(<Throws />);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "The page failed to render.",
    );
  });
});
