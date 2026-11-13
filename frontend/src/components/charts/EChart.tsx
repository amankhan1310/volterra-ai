import { useEffect, useMemo, useRef, useState } from "react";
import { readChartTheme, type ChartTheme } from "./chartTheme";
import { echarts, type ChartInstance, type ChartOption } from "./echarts";
import styles from "./EChart.module.css";

/**
 * Chart colours from the CSS tokens, re-read whenever the document theme attribute changes
 * (the light theme arrives in Milestone 6).
 */
export function useChartTheme(): ChartTheme {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const observer = new MutationObserver(() => {
      setVersion((v) => v + 1);
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "class", "style"],
    });
    return () => {
      observer.disconnect();
    };
  }, []);
  // `version` is the cache key: a theme change must produce a fresh read.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => readChartTheme(), [version]);
}

interface EChartProps {
  option: ChartOption;
  /** Accessible summary of what the chart shows. */
  label: string;
  height?: number;
}

/**
 * Minimal ECharts wrapper: initialises on mount, applies option changes (series are replaced by
 * id, so a series that keeps its id animates to its new data instead of being redrawn; everything
 * else merges, so zoom changes animate as in the prototype), follows container size
 * changes, including the sidebar collapsing, and disposes on unmount.
 */
export function EChart({ option, label, height = 340 }: EChartProps) {
  const element = useRef<HTMLDivElement>(null);
  const chart = useRef<ChartInstance | null>(null);

  useEffect(() => {
    const el = element.current;
    if (!el) return;
    const instance = echarts.init(el);
    chart.current = instance;
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => {
            instance.resize();
          });
    observer?.observe(el);
    return () => {
      observer?.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    chart.current?.setOption(option, { replaceMerge: ["series"] });
  }, [option]);

  return (
    <div
      ref={element}
      className={styles.chart}
      style={{ height }}
      role="img"
      aria-label={label}
    />
  );
}
