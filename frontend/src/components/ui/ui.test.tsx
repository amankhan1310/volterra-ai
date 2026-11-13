import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Button } from "./Button";
import { Card } from "./Card";
import { Dialog } from "./Dialog";
import { InfoTip } from "./InfoTip";
import { Note } from "./Note";
import { ProvenanceTag } from "./ProvenanceTag";
import { Segmented } from "./Segmented";
import { Stat } from "./Stat";
import { EmptyState, ErrorState, Skeleton } from "./States";
import { TOAST_MS, ToastProvider, useToast } from "./Toast";

describe("Button and Card", () => {
  it("renders the legacy primary and outline buttons", () => {
    render(
      <>
        <Button>Run</Button>
        <Button variant="outline" type="submit">
          Reset
        </Button>
      </>,
    );
    const run = screen.getByRole("button", { name: "Run" });
    const reset = screen.getByRole("button", { name: "Reset" });
    expect(run.getAttribute("type")).toBe("button");
    expect(reset.getAttribute("type")).toBe("submit");
    expect(reset.className).not.toBe(run.className);
  });

  it("adds the hover lift only when asked", () => {
    render(
      <>
        <Card data-testid="plain">a</Card>
        <Card data-testid="hover" hover className="extra">
          b
        </Card>
      </>,
    );
    expect(screen.getByTestId("hover").className).toContain("extra");
    expect(
      screen.getByTestId("hover").className.split(" ").length,
    ).toBeGreaterThan(screen.getByTestId("plain").className.split(" ").length);
  });
});

describe("ProvenanceTag", () => {
  it.each([
    ["simulated", "Simulated"],
    ["fitted", "Fitted"],
    ["predicted", "Predicted"],
    ["measured", "Measured"],
    ["assumed", "Assumed"],
  ] as const)("labels %s values", (provenance, label) => {
    render(<ProvenanceTag provenance={provenance} />);
    expect(screen.getByText(label).getAttribute("data-provenance")).toBe(
      provenance,
    );
  });

  it("uses distinct legacy tones for simulated, fitted and predicted, neutral otherwise", () => {
    render(
      <>
        <ProvenanceTag provenance="simulated" />
        <ProvenanceTag provenance="fitted" />
        <ProvenanceTag provenance="predicted" />
        <ProvenanceTag provenance="measured" />
        <ProvenanceTag>Uncertainty: not quantified</ProvenanceTag>
      </>,
    );
    const cls = (t: string) => screen.getByText(t).className;
    expect(
      new Set([cls("Simulated"), cls("Fitted"), cls("Predicted")]).size,
    ).toBe(3);
    expect(cls("Measured")).toBe(cls("Uncertainty: not quantified"));
    expect(
      screen
        .getByText("Uncertainty: not quantified")
        .hasAttribute("data-provenance"),
    ).toBe(false);
  });
});

describe("Note and Stat", () => {
  it("render their content", () => {
    render(
      <>
        <Note>Coefficients are assumed.</Note>
        <Stat label="Fade rate" value="0.054" unit="%/cycle" />
        <Stat label="Cycles" value={320} />
      </>,
    );
    expect(screen.getByText("Coefficients are assumed.")).toBeTruthy();
    expect(screen.getByText("%/cycle")).toBeTruthy();
    expect(screen.getByText("320")).toBeTruthy();
  });
});

describe("Segmented", () => {
  it("exposes the selection with aria-pressed and reports changes", async () => {
    const onChange = vi.fn();
    render(
      <Segmented
        label="Range"
        options={[
          { value: "all", label: "Full" },
          { value: "120", label: "Last 120" },
        ]}
        value="all"
        onChange={onChange}
      />,
    );
    expect(screen.getByRole("group", { name: "Range" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Full" }).getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      screen
        .getByRole("button", { name: "Last 120" })
        .getAttribute("aria-pressed"),
    ).toBe("false");
    await userEvent.click(screen.getByRole("button", { name: "Last 120" }));
    expect(onChange).toHaveBeenCalledWith("120");
  });
});

describe("InfoTip", () => {
  it("links the tooltip to its trigger and can be dismissed with Escape", () => {
    render(
      <InfoTip tip="Slope ±1.96 standard errors.">95% fit interval</InfoTip>,
    );
    const trigger = screen.getByText("95% fit interval");
    const tooltip = screen.getByRole("tooltip");
    expect(trigger.getAttribute("tabindex")).toBe("0");
    expect(trigger.getAttribute("aria-describedby")).toBe(tooltip.id);
    const before = trigger.className;
    fireEvent.keyDown(trigger, { key: "Escape" });
    expect(trigger.className).not.toBe(before);
    fireEvent.blur(trigger);
    expect(trigger.className).toBe(before);
    fireEvent.keyDown(trigger, { key: "Escape" });
    fireEvent.mouseLeave(trigger);
    expect(trigger.className).toBe(before);
    fireEvent.keyDown(trigger, { key: "a" });
    expect(trigger.className).toBe(before);
  });
});

describe("Dialog", () => {
  function Harness({ onClose }: { onClose?: () => void }) {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button
          type="button"
          onClick={() => {
            setOpen(true);
          }}
        >
          Rename
        </button>
        <Dialog
          open={open}
          title="Rename scenario"
          onClose={() => {
            onClose?.();
            setOpen(false);
          }}
          footer={<button type="button">Save</button>}
        >
          <p>Body</p>
        </Dialog>
      </>
    );
  }

  it("opens as a labelled dialog and closes on Escape (cancel)", async () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: "Rename" }));
    const dialog = screen.getByRole("dialog", { name: "Rename scenario" });
    expect(dialog.hasAttribute("open")).toBe(true);
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
    fireEvent(dialog, new Event("cancel", { cancelable: true }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(dialog.hasAttribute("open")).toBe(false);
  });

  it("works without native showModal/close support", () => {
    const proto = HTMLDialogElement.prototype as unknown as Record<
      string,
      unknown
    >;
    const saved = { showModal: proto["showModal"], close: proto["close"] };
    proto["showModal"] = undefined;
    proto["close"] = undefined;
    try {
      const { rerender } = render(
        <Dialog open title="T" onClose={() => undefined}>
          x
        </Dialog>,
      );
      const dialog = screen.getByText("x").closest("dialog");
      expect(dialog?.hasAttribute("open")).toBe(true);
      rerender(
        <Dialog open={false} title="T" onClose={() => undefined}>
          x
        </Dialog>,
      );
      expect(dialog?.hasAttribute("open")).toBe(false);
    } finally {
      proto["showModal"] = saved.showModal;
      proto["close"] = saved.close;
    }
  });
});

describe("Toast", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows one message at a time for 3.4 s", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useToast(), { wrapper: ToastProvider });
    const region = screen.getByRole("status");
    act(() => {
      result.current("First");
    });
    expect(region.textContent).toBe("First");
    act(() => {
      vi.advanceTimersByTime(TOAST_MS - 100);
      result.current("Second");
    });
    expect(region.textContent).toBe("Second");
    act(() => {
      vi.advanceTimersByTime(TOAST_MS - 1);
    });
    expect(region.textContent).toBe("Second");
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(region.textContent).toBe("");
  });

  it("must be used inside its provider", () => {
    expect(() => renderHook(() => useToast())).toThrow(
      "inside <ToastProvider>",
    );
  });
});

describe("state components", () => {
  it("renders loading, error and empty states", async () => {
    const onRetry = vi.fn();
    render(
      <>
        <Skeleton label="Loading chart" />
        <ErrorState
          title="API unreachable"
          message="Down"
          code="api_unreachable"
          hint="Start it"
          onRetry={onRetry}
        />
        <ErrorState title="Plain" message="No extras" />
        <EmptyState title="Nothing">Seed it</EmptyState>
      </>,
    );
    expect(screen.getByRole("status", { name: "Loading chart" })).toBeTruthy();
    const [first, second] = screen.getAllByRole("alert");
    expect(first?.textContent).toContain("Error code: api_unreachable");
    expect(first?.textContent).toContain("Start it");
    expect(second?.textContent).not.toContain("Error code");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Seed it")).toBeTruthy();
  });
});
