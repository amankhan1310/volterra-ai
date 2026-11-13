import { useId, useState } from "react";
import { useCycles, useTwin } from "../../api/hooks";
import type { Battery, Twin } from "../../api/types";
import { getPage } from "../../app/pages";
import { BatteryGate } from "../../components/layout/BatteryGate";
import { ContextBar } from "../../components/layout/ContextBar";
import { PageHeader } from "../../components/layout/PageHeader";
import { QueryFallback } from "../../components/layout/QueryFallback";
import { RunAnalysisButton } from "../../components/layout/RunAnalysisButton";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Note } from "../../components/ui/Note";
import { Segmented } from "../../components/ui/Segmented";
import { useToast } from "../../components/ui/Toast";
import { describeError } from "../../api/errors";
import { BAND_COLOR, HEALTH_COLOR } from "../../lib/health";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import styles from "./DigitalTwin.module.css";
import { IsometricPack } from "./IsometricPack";
import { PackStatePanel } from "./PackStatePanel";

/** Slider requests wait until the cycle has been still this long (plan §3.2). */
export const TWIN_DEBOUNCE_MS = 120;

export type TwinMode = "soh" | "temp";

const MODES = [
  { value: "soh", label: "Health" },
  { value: "temp", label: "Temperature" },
] as const;

/** Legend rows per mode (prototype text; the thresholds themselves live in the backend). */
export const LEGEND: Record<TwinMode, { label: string; color: string }[]> = {
  soh: [
    { label: "≥ 85% healthy", color: "var(--gr)" },
    { label: "80–85% caution", color: "var(--am)" },
    { label: "< 80% below threshold", color: "var(--rd)" },
  ],
  temp: [
    { label: "< 30 °C", color: "var(--cy)" },
    { label: "30–40 °C", color: "var(--am)" },
    { label: "> 40 °C", color: "var(--rd)" },
  ],
};

export function packColor(twin: Twin, mode: TwinMode): string {
  return mode === "soh"
    ? HEALTH_COLOR[twin.health_level]
    : BAND_COLOR[twin.temperature_band];
}

function TwinContent({ battery }: { battery: Battery }) {
  const toast = useToast();
  const sliderId = useId();
  const cycles = useCycles(battery.id);
  const lastCycle = cycles.data?.items.at(-1)?.cycle;
  const [mode, setMode] = useState<TwinMode>("soh");
  const [selected, setSelected] = useState<number | null>(null);
  // `null` follows the latest cycle; the slider sets a specific one.
  const [picked, setPicked] = useState<number | null>(null);
  const cycle = picked ?? lastCycle;
  // Slider moves are debounced; the first load asks for the latest cycle straight away.
  const requested = useDebouncedValue(cycle, TWIN_DEBOUNCE_MS) ?? lastCycle;
  const twin = useTwin(battery.id, requested);

  // Keep the last good state on screen if a slider-driven request fails (plan §3.2).
  const [lastGood, setLastGood] = useState<Twin | undefined>(undefined);
  // (React's "adjust state while rendering" pattern: no effect, no extra commit.)
  const fresh = twin.isPlaceholderData ? undefined : twin.data;
  if (fresh && fresh !== lastGood) setLastGood(fresh);
  const shown = twin.data ?? lastGood;

  if (!cycles.data || lastCycle === undefined || cycle === undefined || !shown)
    return (
      <QueryFallback
        queries={[cycles, twin]}
        label="Loading the digital twin"
        height={420}
      />
    );

  const color = packColor(shown, mode);
  return (
    <>
      <div className={styles.layout}>
        <Card>
          <div className={styles.toolbar}>
            <Segmented
              label="Colour modules by"
              options={MODES}
              value={mode}
              onChange={setMode}
            />
            <Button
              variant="outline"
              onClick={() => {
                setSelected(null);
                setPicked(null);
                toast("View reset to the latest cycle");
              }}
            >
              Reset view
            </Button>
          </div>
          <div className={styles.scene}>
            <IsometricPack
              count={shown.modules.count}
              color={color}
              selected={selected}
              onSelect={setSelected}
            />
          </div>
          <label htmlFor={sliderId} className={styles.cycleLabel}>
            Cycle <span data-testid="cycle-value">{cycle}</span>
          </label>
          <input
            id={sliderId}
            className={styles.slider}
            type="range"
            min={cycles.data.items[0]?.cycle ?? 0}
            max={lastCycle}
            step={1}
            value={cycle}
            onChange={(e) => {
              setPicked(Number(e.target.value));
            }}
          />
          <div className={styles.legend} aria-label="Colour legend">
            {LEGEND[mode].map((row) => (
              <span key={row.label}>
                <i style={{ background: row.color }} aria-hidden="true" />
                {row.label}
              </span>
            ))}
          </div>
        </Card>
        <Card data-testid="page-content" aria-busy={twin.isFetching}>
          {twin.isError ? (
            <p role="alert" className={styles.inlineError}>
              Could not load cycle {requested} (
              {describeError(twin.error).message}). Showing cycle {shown.cycle}.
            </p>
          ) : null}
          <PackStatePanel
            twin={shown}
            cycles={cycles.data}
            selected={selected}
          />
        </Card>
      </div>
      <Note>
        The dataset holds pack-level measurements only. All{" "}
        {shown.modules.count} modules are drawn from the pack value; nothing
        here is a per-cell measurement. Select a module to lift it.
      </Note>
    </>
  );
}

export function DigitalTwinPage() {
  const page = getPage("digital");
  return (
    <>
      <PageHeader
        title={page.title}
        subtitle={page.subtitle}
        actions={<RunAnalysisButton />}
      />
      <ContextBar />
      <BatteryGate>
        {(battery) => <TwinContent battery={battery} />}
      </BatteryGate>
    </>
  );
}
