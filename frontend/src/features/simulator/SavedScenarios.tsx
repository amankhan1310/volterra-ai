import { useId, useState } from "react";
import type { Scenario } from "../../api/types";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { NAME_MAX, scenarioColor } from "./options";
import styles from "./Simulator.module.css";

/** "25°C · 1C · 80%": the conditions a saved scenario differs by (prototype list text). */
export const scenarioSummary = (s: Scenario) =>
  `${String(s.params.temp_c)}°C · ${String(s.params.c_rate)}C · ${String(s.params.dod_pct)}%`;

/** Accessible in-page replacement for the prototype's `prompt()` (plan §2.2), 30 characters (U2). */
export function RenameDialog({
  scenario,
  busy,
  onCancel,
  onSave,
}: {
  scenario: Scenario | null;
  busy: boolean;
  onCancel: () => void;
  onSave: (name: string) => void;
}) {
  const inputId = useId();
  const [draft, setDraft] = useState<{ id: string; name: string } | null>(null);
  // Start from the scenario's name whenever a different scenario is opened.
  const name =
    scenario && draft?.id === scenario.id
      ? draft.name
      : (scenario?.name.slice(0, NAME_MAX) ?? "");
  const trimmed = name.trim();
  const submit = (e: { preventDefault: () => void }) => {
    e.preventDefault();
    if (!trimmed) return;
    setDraft(null);
    onSave(trimmed);
  };
  const cancel = () => {
    setDraft(null);
    onCancel();
  };
  const formId = `${inputId}-form`;
  return (
    <Dialog
      open={scenario !== null}
      title="Rename scenario"
      onClose={cancel}
      footer={
        <>
          <Button variant="outline" onClick={cancel}>
            Cancel
          </Button>
          <Button type="submit" form={formId} disabled={!trimmed || busy}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={submit}>
        <label htmlFor={inputId} className={styles.fieldLabel}>
          Scenario name
        </label>
        <input
          id={inputId}
          className={styles.textInput}
          value={name}
          maxLength={NAME_MAX}
          autoFocus
          onChange={(e) => {
            if (scenario) setDraft({ id: scenario.id, name: e.target.value });
          }}
          aria-describedby={`${inputId}-count`}
        />
        <p id={`${inputId}-count`} className={`mu ${styles.count}`}>
          {name.length}/{NAME_MAX} characters
        </p>
      </form>
    </Dialog>
  );
}

interface SavedScenariosProps {
  scenarios: readonly Scenario[];
  disabled: boolean;
  onRename: (scenario: Scenario) => void;
  onDuplicate: (scenario: Scenario) => void;
  onDelete: (scenario: Scenario) => void;
}

/** The saved-scenario list under the controls (legacy `#sl`). */
export function SavedScenarios({
  scenarios,
  disabled,
  onRename,
  onDuplicate,
  onDelete,
}: SavedScenariosProps) {
  if (scenarios.length === 0)
    return (
      <p className={`mu ${styles.hint}`}>
        Adjust the controls, then save a scenario to overlay it on the chart.
      </p>
    );
  return (
    <div>
      <div className={`lb ${styles.savedTitle}`}>Saved scenarios</div>
      <ul className={styles.savedList}>
        {scenarios.map((s, i) => (
          <li key={s.id} className={styles.saved} data-testid="saved-scenario">
            <b style={{ color: scenarioColor(i) }}>{s.name}</b>{" "}
            <span className="mu">{scenarioSummary(s)}</span>
            <div className={styles.row}>
              {(
                [
                  ["Rename", onRename],
                  ["Duplicate", onDuplicate],
                  ["Delete", onDelete],
                ] as const
              ).map(([action, handler]) => (
                <Button
                  key={action}
                  variant="outline"
                  disabled={disabled}
                  aria-label={`${action} ${s.name}`}
                  onClick={() => {
                    handler(s);
                  }}
                >
                  {action}
                </Button>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
