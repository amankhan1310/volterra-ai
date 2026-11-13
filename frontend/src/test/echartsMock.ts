/**
 * Stand-in for `components/charts/echarts` in unit tests (jsdom has no canvas). Each `init`
 * records a fake instance, so tests can assert on the options a chart received. Real canvas
 * rendering is covered by the Playwright suites. Plain functions (not `vi.fn`) so the config's
 * `restoreMocks` cannot reset them between tests.
 */
export interface FakeChart {
  element: HTMLElement;
  options: unknown[];
  resizes: number;
  disposed: boolean;
  setOption: (option: unknown) => void;
  resize: () => void;
  dispose: () => void;
}

export const charts: FakeChart[] = [];

export const echarts = {
  init: (element: HTMLElement): FakeChart => {
    const chart: FakeChart = {
      element,
      options: [],
      resizes: 0,
      disposed: false,
      setOption: (option) => {
        chart.options.push(option);
      },
      resize: () => {
        chart.resizes += 1;
      },
      dispose: () => {
        chart.disposed = true;
      },
    };
    charts.push(chart);
    return chart;
  },
};

/** The live chart whose container has an accessible name matching `label`. */
export function chartByLabel(label: RegExp): FakeChart | undefined {
  return charts.findLast(
    (c) =>
      !c.disposed && label.test(c.element.getAttribute("aria-label") ?? ""),
  );
}

/** The latest option a chart received. */
export function lastOption(chart: FakeChart | undefined): unknown {
  const option = chart?.options.at(-1);
  if (option === undefined) throw new Error("The chart received no option");
  return option;
}
