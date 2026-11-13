import { act, renderHook, screen, waitFor } from "@testing-library/react";
import { http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { AppProviders } from "../app/providers";
import { fixtures, server } from "../test/msw";
import { testQueryClient } from "../test/render";
import { useScenarioDraft } from "./ScenarioDraftContext";

function setup() {
  const client = testQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <AppProviders client={client}>{children}</AppProviders>
  );
  return { client, ...renderHook(() => useScenarioDraft(), { wrapper }) };
}

describe("ScenarioDraftContext (D1)", () => {
  it("starts from the API's simulator defaults", async () => {
    const { result } = setup();
    expect(result.current.params).toBeNull();
    await waitFor(() => {
      expect(result.current.params).toEqual(fixtures.simulator.defaults);
    });
    expect(result.current.defaults).toEqual(fixtures.simulator.defaults);
    expect(result.current.changed).toEqual({
      eolPct: false,
      startSohPct: false,
    });
  });

  it("tracks EOL and initial-SOH changes for the U1 chips, and resets", async () => {
    const { result } = setup();
    await waitFor(() => {
      expect(result.current.params).not.toBeNull();
    });
    act(() => {
      result.current.setParam("eol_pct", 82);
    });
    expect(result.current.params?.eol_pct).toBe(82);
    expect(result.current.changed).toEqual({
      eolPct: true,
      startSohPct: false,
    });

    act(() => {
      result.current.setParam("start_soh_pct", 90);
      result.current.setParam("temp_c", 35);
    });
    expect(result.current.changed).toEqual({ eolPct: true, startSohPct: true });
    expect(result.current.params?.temp_c).toBe(35);

    act(() => {
      result.current.setParam("eol_pct", fixtures.simulator.defaults.eol_pct);
    });
    expect(result.current.changed.eolPct).toBe(false);

    act(() => {
      result.current.reset();
    });
    expect(result.current.params).toEqual(fixtures.simulator.defaults);
  });

  it("starts again from the defaults when the battery changes", async () => {
    const { result, client } = setup();
    await waitFor(() => {
      expect(result.current.params).not.toBeNull();
    });
    act(() => {
      result.current.setParam("eol_pct", 70);
    });
    const other = {
      ...fixtures.battery,
      id: "00000000-0000-0000-0000-000000000002",
    };
    server.use(
      http.get("*/api/v1/batteries", () => Response.json({ items: [other] })),
    );
    await act(async () => {
      await client.refetchQueries();
    });
    await waitFor(() => {
      expect(result.current.params?.eol_pct).toBe(
        fixtures.simulator.defaults.eol_pct,
      );
    });
    act(() => {
      result.current.setParam("dod_pct", 60);
    });
    expect(result.current.params?.dod_pct).toBe(60);
    expect(result.current.params?.eol_pct).toBe(
      fixtures.simulator.defaults.eol_pct,
    );
  });

  it("must be used inside its provider", () => {
    expect(() => renderHook(() => useScenarioDraft())).toThrow(
      "inside <ScenarioDraftProvider>",
    );
    expect(screen.queryByText("x")).toBeNull();
  });
});
