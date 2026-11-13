import { useId } from "react";
import type { ScenarioParams, Slider } from "../../api/types";
import { sliderValueText } from "./options";
import styles from "./Simulator.module.css";

/** Slider keys the API sends that are scenario parameters (all six today). */
export function isParamKey(
  key: string,
  params: ScenarioParams,
): key is keyof ScenarioParams {
  return Object.hasOwn(params, key);
}

function SliderField({
  slider,
  value,
  onChange,
}: {
  slider: Slider;
  value: number;
  onChange: (value: number) => void;
}) {
  const id = useId();
  return (
    <>
      <label htmlFor={id} className={styles.label}>
        {slider.label}{" "}
        <span data-testid={`value-${slider.key}`}>
          {sliderValueText(value, slider.unit)}
        </span>
      </label>
      <input
        id={id}
        className={styles.slider}
        type="range"
        min={slider.min}
        max={slider.max}
        step={slider.step}
        value={value}
        onChange={(e) => {
          onChange(Number(e.target.value));
        }}
      />
    </>
  );
}

/** The six scenario sliders, defined by the API's `GET /simulator` (bounds, steps, units). */
export function SimulatorControls({
  sliders,
  params,
  onChange,
}: {
  sliders: readonly Slider[];
  params: ScenarioParams;
  onChange: (key: keyof ScenarioParams, value: number) => void;
}) {
  return (
    <div>
      {sliders.map((slider) =>
        isParamKey(slider.key, params) ? (
          <SliderField
            key={slider.key}
            slider={slider}
            value={params[slider.key]}
            onChange={(v) => {
              onChange(slider.key as keyof ScenarioParams, v);
            }}
          />
        ) : null,
      )}
    </div>
  );
}
