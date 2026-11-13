/**
 * Tree-shaken ECharts registry: only what the prototype's charts use. The `lines` series (geo
 * flow lines) is deliberately not registered: GHSA-fgmj-fm8m-jvvx affects only its built-in
 * tooltip in ECharts < 6.1, and every tooltip here uses our own escaping formatter.
 */
import { LineChart, ScatterChart } from "echarts/charts";
import {
  DataZoomInsideComponent,
  DataZoomSliderComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  LineChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomInsideComponent,
  DataZoomSliderComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

export { echarts };
export type ChartInstance = echarts.ECharts;
export type ChartOption = echarts.EChartsCoreOption;
