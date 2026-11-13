import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useDefaultBattery, useSimulatorConfig } from "../api/hooks";
import type { ScenarioParams } from "../api/types";

/**
 * Shared simulator parameters (decision D1). The prototype kept them in one global, `P`: the
 * Simulator sliders edit it, Overview reads its EOL threshold and the Charging Advisor reads its
 * EOL threshold and initial SOH. Here they live in memory for the session, start from the API's
 * `GET /simulator` defaults, and reset on reload, exactly as before.
 */
export interface ScenarioDraft {
  /** API defaults; `null` until the simulator configuration has loaded. */
  defaults: ScenarioParams | null;
  /** Defaults with the user's changes applied; `null` until loaded. */
  params: ScenarioParams | null;
  /** True for each setting the user moved away from its default (drives the U1 chips). */
  changed: { eolPct: boolean; startSohPct: boolean };
  setParam: <K extends keyof ScenarioParams>(
    key: K,
    value: ScenarioParams[K],
  ) => void;
  /** Back to the API defaults (the Simulator's Reset button). */
  reset: () => void;
}

const ScenarioDraftContext = createContext<ScenarioDraft | null>(null);

interface Overrides {
  batteryId: string | undefined;
  values: Partial<ScenarioParams>;
}

export function ScenarioDraftProvider({ children }: { children: ReactNode }) {
  const { battery } = useDefaultBattery();
  const batteryId = battery?.id;
  const config = useSimulatorConfig(batteryId);
  const [overrides, setOverrides] = useState<Overrides>({
    batteryId,
    values: {},
  });

  const setParam = useCallback(
    <K extends keyof ScenarioParams>(key: K, value: ScenarioParams[K]) => {
      setOverrides((prev) => ({
        batteryId,
        values: {
          ...(prev.batteryId === batteryId ? prev.values : {}),
          [key]: value,
        },
      }));
    },
    [batteryId],
  );

  const reset = useCallback(() => {
    setOverrides({ batteryId, values: {} });
  }, [batteryId]);

  const defaults = config.data?.defaults ?? null;

  const draft = useMemo<ScenarioDraft>(() => {
    // Changes belong to one battery; switching battery starts again from its defaults.
    const values = overrides.batteryId === batteryId ? overrides.values : {};
    const params = defaults ? { ...defaults, ...values } : null;
    return {
      defaults,
      params,
      changed: {
        eolPct:
          params !== null &&
          defaults !== null &&
          params.eol_pct !== defaults.eol_pct,
        startSohPct:
          params !== null &&
          defaults !== null &&
          params.start_soh_pct !== defaults.start_soh_pct,
      },
      setParam,
      reset,
    };
  }, [defaults, overrides, batteryId, setParam, reset]);

  return (
    <ScenarioDraftContext.Provider value={draft}>
      {children}
    </ScenarioDraftContext.Provider>
  );
}

export function useScenarioDraft(): ScenarioDraft {
  const draft = useContext(ScenarioDraftContext);
  if (!draft)
    throw new Error(
      "useScenarioDraft must be used inside <ScenarioDraftProvider>",
    );
  return draft;
}
