import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useDefaultBattery, useHealth } from "../../api/hooks";
import { describeError } from "../../api/errors";
import { Button } from "../ui/Button";
import { useToast } from "../ui/Toast";

/** Text shown after a successful reload (decision D6: reloading, not retraining). */
export function reloadMessage(
  dataset: string | undefined,
  algorithm: string | undefined,
  detail?: string | null,
): string {
  const source = [dataset, algorithm && `algorithm ${algorithm}`]
    .filter(Boolean)
    .join(", ");
  return `Analysis results reloaded from the API${source ? ` (${source})` : ""}${detail ? `: ${detail}` : ""}. No model was retrained.`;
}

/**
 * Legacy "Run analysis" (decision D6). The prototype re-rendered static results; here the page's
 * API queries are fetched again and the toast says exactly that.
 */
export function RunAnalysisButton({
  summarize,
}: {
  /** Key results to repeat in the toast after the reload (the prototype quoted SOH and RUL). */
  summarize?: () => string | null;
} = {}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  // Read during render: TanStack Query only re-renders for result fields the render used.
  const dataset = useDefaultBattery().battery?.dataset;
  const algorithm = useHealth().data?.algorithm_version;
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      await queryClient.refetchQueries({ type: "active" });
    } finally {
      setBusy(false);
    }
    const failed = queryClient
      .getQueryCache()
      .findAll({ type: "active" })
      .find((q) => q.state.status === "error");
    if (failed) {
      toast(`Reload failed: ${describeError(failed.state.error).message}`);
    } else {
      toast(reloadMessage(dataset, algorithm, summarize?.()));
    }
  };

  return (
    <Button onClick={() => void run()} disabled={busy} aria-busy={busy}>
      {busy ? "Reloading…" : "Run analysis"}
    </Button>
  );
}
