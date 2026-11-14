import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fixtures } from "../../test/msw";
import { AnomalyTimeline } from "./AnomalyTimeline";
import { TIMELINE, timelineX } from "./options";

const events = fixtures.anomalies.events;

function stubResizeObserver() {
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
  return { fire: () => callback?.(), disconnect };
}

function setClientWidth(width: number) {
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(width);
}

const svg = () => screen.getByRole("group", { name: "Anomaly timeline" });
const dot = (cycle: number) =>
  svg().querySelector(`[data-cycle="${String(cycle)}"]`);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("anomaly timeline sizing", () => {
  it("draws at the prototype's 720 units when it cannot measure", () => {
    render(<AnomalyTimeline events={events} lastCycle={319} />);
    expect(svg().getAttribute("viewBox")).toBe("0 0 720 120");
    expect(Number(dot(319)?.getAttribute("cx"))).toBe(
      TIMELINE.width - TIMELINE.right,
    );
  });

  it("redraws at its measured width, so text keeps its size", () => {
    setClientWidth(500);
    const observer = stubResizeObserver();
    const { unmount } = render(
      <AnomalyTimeline events={events} lastCycle={319} />,
    );
    expect(svg().getAttribute("viewBox")).toBe("0 0 500 120");
    expect(svg().getAttribute("width")).toBe("500");
    expect(Number(dot(130)?.getAttribute("cx"))).toBe(timelineX(130, 319, 500));
    setClientWidth(410.6);
    act(() => {
      observer.fire();
    });
    expect(svg().getAttribute("viewBox")).toBe("0 0 410 120");
    unmount();
    expect(observer.disconnect).toHaveBeenCalled();
  });

  it("keeps a minimum width on very narrow screens (the card scrolls)", () => {
    setClientWidth(200);
    stubResizeObserver();
    render(<AnomalyTimeline events={events} lastCycle={319} />);
    expect(svg().getAttribute("viewBox")).toBe(
      `0 0 ${String(TIMELINE.minWidth)} 120`,
    );
  });

  it("ignores a zero width while hidden", () => {
    setClientWidth(0);
    stubResizeObserver();
    render(<AnomalyTimeline events={events} lastCycle={319} />);
    expect(svg().getAttribute("viewBox")).toBe("0 0 720 120");
  });

  it("keeps the tooltip inside the drawing at either end", () => {
    setClientWidth(TIMELINE.minWidth);
    stubResizeObserver();
    render(<AnomalyTimeline events={events} lastCycle={319} />);
    const last = dot(319);
    if (!last) throw new Error("No event at cycle 319");
    act(() => {
      last.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    });
    const rect = svg().querySelector("g[aria-hidden='true'] rect");
    const x = Number(rect?.getAttribute("x"));
    const w = Number(rect?.getAttribute("width"));
    expect(x).toBeGreaterThanOrEqual(0);
    expect(x + w).toBeLessThanOrEqual(TIMELINE.minWidth);
  });
});
