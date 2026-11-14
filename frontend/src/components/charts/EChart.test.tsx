import { act, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { charts } from "../../test/echartsMock";
import { EChart, useChartTheme } from "./EChart";

function ThemeProbe() {
  return <span data-testid="cy">{useChartTheme().cy}</span>;
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.style.removeProperty("--cy-fill");
});

describe("EChart", () => {
  it("initialises once, applies option changes and disposes on unmount", () => {
    const { rerender, unmount, getByRole } = render(
      <EChart option={{ a: 1 }} label="Test chart" height={200} />,
    );
    const element = getByRole("img", { name: "Test chart" });
    expect(element.style.height).toBe("200px");
    expect(charts).toHaveLength(1);
    const chart = charts[0];
    expect(chart?.options).toEqual([{ a: 1 }]);
    rerender(<EChart option={{ a: 2 }} label="Test chart" />);
    expect(chart?.options).toEqual([{ a: 1 }, { a: 2 }]);
    expect(element.style.height).toBe("340px");
    unmount();
    expect(chart?.disposed).toBe(true);
  });

  it("resizes with its container", () => {
    let callback: (() => void) | undefined;
    const disconnect = vi.fn();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(cb: () => void) {
          callback = cb;
        }
        observe() {
          /* noop */
        }
        disconnect = disconnect;
      },
    );
    const { unmount } = render(<EChart option={{}} label="Sized" />);
    act(() => {
      callback?.();
    });
    expect(charts[0]?.resizes).toBe(1);
    unmount();
    expect(disconnect).toHaveBeenCalled();
  });

  it("re-reads the colours when the document theme changes", async () => {
    document.documentElement.style.setProperty("--cy-fill", "#000001");
    const { findByText } = render(<ThemeProbe />);
    expect(await findByText("#000001")).toBeTruthy();
    document.documentElement.style.setProperty("--cy-fill", "#000002");
    act(() => {
      document.documentElement.setAttribute("data-theme", "light");
    });
    expect(await findByText("#000002")).toBeTruthy();
  });
});
