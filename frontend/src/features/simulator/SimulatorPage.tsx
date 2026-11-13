import { useMemo, useState } from "react";
import { describeError } from "../../api/errors";
import {
  useScenarioMutations,
  useScenarios,
  useSimulation,
  useSimulations,
  useSimulatorConfig,
} from "../../api/hooks";
import type {
  Battery,
  Scenario,
  ScenarioParams,
  Simulation,
  SimulatorConfig,
} from "../../api/types";
import { getPage } from "../../app/pages";
import { ChartDataTable } from "../../components/charts/ChartDataTable";
import { EChart, useChartTheme } from "../../components/charts/EChart";
import { BatteryGate } from "../../components/layout/BatteryGate";
import { ContextBar } from "../../components/layout/ContextBar";
import { PageHeader } from "../../components/layout/PageHeader";
import { QueryFallback } from "../../components/layout/QueryFallback";
import { RunAnalysisButton } from "../../components/layout/RunAnalysisButton";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Note } from "../../components/ui/Note";
import { useToast } from "../../components/ui/Toast";
import { useDebouncedValue } from "../../lib/useDebouncedValue";
import { useScenarioDraft } from "../../state/ScenarioDraftContext";
import {
  MAX_SCENARIOS,
  NAME_MAX,
  clampedSeries,
  scenarioTone,
  simulatorOption,
  type Overlay,
} from "./options";
import { RenameDialog, SavedScenarios } from "./SavedScenarios";
import { SimulationResults } from "./SimulationResults";
import { SimulatorControls } from "./SimulatorControls";
import styles from "./Simulator.module.css";

/** Slider changes wait until the controls have been still this long (plan §3.3). */
export const SIMULATE_DEBOUNCE_MS = 150;

const LIMIT_MESSAGE = `Delete a scenario first (max ${String(MAX_SCENARIOS)}).`;

/** The model sentence under the page, with the coefficients the API reports. */
export function modelNote(config: SimulatorConfig): string {
  const c = (name: string) =>
    config.coefficients.find((k) => k.name === name)?.value;
  const num = (v: number | null | undefined) => (v == null ? "?" : String(v));
  const b = config.baseline_conditions;
  return (
    `Model: SOH(n) = SOH₀ − r·n·(1 + n/${num(c("acceleration"))}), r = recent fitted fade × ` +
    `e^(${num(c("temperature"))}·(T−${num(b.temp_c)})) × (1 + ${num(c("c_rate"))}·(C−${num(b.c_rate)})) × ` +
    `(DoD/${num(b.dod_pct)})^${num(c("dod"))}. The temperature, C-rate and DoD coefficients are ` +
    "assumed, not fitted. Outputs are simulated estimates."
  );
}

function ScenarioChart({
  sim,
  overlays,
}: {
  sim: Simulation;
  overlays: readonly Overlay[];
}) {
  const theme = useChartTheme();
  const option = useMemo(
    () => simulatorOption(theme, sim, overlays),
    [theme, sim, overlays],
  );
  const t = sim.trajectories;
  const current = clampedSeries(t?.cycles ?? [], t?.scenario ?? []);
  const baseline = clampedSeries(t?.cycles ?? [], t?.baseline ?? []);
  return (
    <>
      <EChart
        option={option}
        height={400}
        label={`Simulated SOH over ${String(sim.params.horizon_cycles)} cycles: baseline, current scenario${overlays.length ? ` and ${String(overlays.length)} saved scenarios` : ""}, with the ${String(sim.params.eol_pct)}% end-of-life line.`}
      />
      <ChartDataTable
        caption="Scenario SOH trajectories (%)"
        columns={[
          "Cycle",
          "Baseline",
          "Current",
          ...overlays.map((o) => o.name),
        ]}
        rows={current.map(([c, v], i) => [
          String(c),
          (baseline[i]?.[1] ?? NaN).toFixed(2),
          v.toFixed(2),
          ...overlays.map((o) =>
            Math.max(0, o.sim.trajectories?.scenario[i] ?? NaN).toFixed(2),
          ),
        ])}
      />
    </>
  );
}

function SimulatorWorkspace({
  battery,
  config,
  params,
}: {
  battery: Battery;
  config: SimulatorConfig;
  params: ScenarioParams;
}) {
  const draft = useScenarioDraft();
  const toast = useToast();
  const requested = useDebouncedValue(params, SIMULATE_DEBOUNCE_MS);
  const sim = useSimulation(battery.id, requested);
  // Keep the last good result on screen if a new simulation fails (plan §3.3); React's
  // "adjust state while rendering" pattern, as on the Digital Twin.
  const [lastGood, setLastGood] = useState<Simulation | undefined>(undefined);
  const fresh = sim.isPlaceholderData ? undefined : sim.data;
  if (fresh && fresh !== lastGood) setLastGood(fresh);
  const shown = sim.data ?? lastGood;
  const scenarios = useScenarios(battery.id);
  const { create, rename, remove } = useScenarioMutations(battery.id);
  const [renaming, setRenaming] = useState<Scenario | null>(null);

  const saved = scenarios.data?.items ?? [];
  const drawn = saved.slice(0, MAX_SCENARIOS);
  // Overlays follow the current horizon, as in the prototype (`ser` uses the current N).
  const overlayParams = useMemo(
    () =>
      drawn.map((s) => ({
        ...s.params,
        horizon_cycles: requested.horizon_cycles,
      })),
    [drawn, requested.horizon_cycles],
  );
  const overlaySims = useSimulations(battery.id, overlayParams);
  const overlays: Overlay[] = useMemo(
    () =>
      drawn.flatMap((s, i) => {
        const data = overlaySims[i]?.data;
        return data
          ? [{ id: s.id, name: s.name, tone: scenarioTone(i), sim: data }]
          : [];
      }),
    [drawn, overlaySims],
  );
  const overlayFailed = overlaySims.some((q) => q.isError);

  const failure = (what: string) => (error: unknown) => {
    toast(`Could not ${what}: ${describeError(error).message}`);
  };
  const mutating = create.isPending || rename.isPending || remove.isPending;
  const canSave = scenarios.isSuccess && !mutating;

  const save = (name: string, p: ScenarioParams) => {
    if (saved.length >= MAX_SCENARIOS) {
      toast(LIMIT_MESSAGE);
      return;
    }
    create.mutate(
      { name: name.slice(0, NAME_MAX), params: p },
      { onError: failure("save the scenario") },
    );
  };

  return (
    <>
      <div className={styles.layout}>
        <Card>
          <div className="lb">Scenario controls</div>
          <SimulatorControls
            sliders={config.sliders}
            params={params}
            onChange={(key, value) => {
              draft.setParam(key, value);
            }}
          />
          <div className={styles.row}>
            <Button
              disabled={!canSave}
              onClick={() => {
                save(`Scenario ${String(saved.length + 1)}`, params);
              }}
            >
              Save scenario
            </Button>
            <Button variant="outline" onClick={draft.reset}>
              Reset
            </Button>
          </div>
          <div className={styles.savedArea}>
            {scenarios.isSuccess ? (
              <SavedScenarios
                scenarios={saved}
                disabled={mutating}
                onRename={setRenaming}
                onDuplicate={(s) => {
                  save(`${s.name} copy`, s.params);
                }}
                onDelete={(s) => {
                  remove.mutate(s, { onError: failure("delete the scenario") });
                }}
              />
            ) : (
              <>
                <QueryFallback
                  queries={[scenarios]}
                  label="Loading saved scenarios"
                  height={60}
                />
                {scenarios.isError ? (
                  <p className={`mu ${styles.hint}`}>
                    Saving scenarios needs the database; the simulator itself
                    still works.
                  </p>
                ) : null}
              </>
            )}
          </div>
        </Card>
        <Card>
          <div className="lb">Predicted behaviour</div>
          {shown ? (
            <ScenarioChart sim={shown} overlays={overlays} />
          ) : (
            <QueryFallback queries={[sim]} label="Simulating" height={400} />
          )}
          {overlayFailed ? (
            <p className={`mu ${styles.hint}`} role="status">
              Some saved scenarios could not be simulated and are not drawn.
            </p>
          ) : null}
        </Card>
        <Card data-testid="page-content">
          {sim.isError && shown ? (
            <p role="alert" className={styles.inlineError}>
              {describeError(sim.error).message} Showing the previous result.
            </p>
          ) : null}
          {shown ? (
            <SimulationResults sim={shown} config={config} />
          ) : (
            <QueryFallback
              queries={[sim]}
              label="Loading results"
              height={300}
            />
          )}
        </Card>
      </div>
      <Note>{modelNote(config)}</Note>
      <RenameDialog
        scenario={renaming}
        busy={rename.isPending}
        onCancel={() => {
          setRenaming(null);
        }}
        onSave={(name) => {
          if (!renaming) return;
          rename.mutate(
            { id: renaming.id, name },
            {
              onSuccess: () => {
                setRenaming(null);
              },
              onError: failure("rename the scenario"),
            },
          );
        }}
      />
    </>
  );
}

function SimulatorContent({ battery }: { battery: Battery }) {
  const config = useSimulatorConfig(battery.id);
  const { params } = useScenarioDraft();
  if (!config.data || !params)
    return (
      <QueryFallback
        queries={[config]}
        label="Loading the simulator"
        height={420}
      />
    );
  return (
    <SimulatorWorkspace
      battery={battery}
      config={config.data}
      params={params}
    />
  );
}

export function SimulatorPage() {
  const page = getPage("sim");
  return (
    <>
      <PageHeader
        title={page.title}
        subtitle={page.subtitle}
        actions={<RunAnalysisButton />}
      />
      <ContextBar />
      <BatteryGate>
        {(battery) => <SimulatorContent battery={battery} />}
      </BatteryGate>
    </>
  );
}
