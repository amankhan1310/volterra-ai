# Dataset card: CALCE CS2 and CX2 prismatic cells

| Field                      | Value                                                                                    |
| -------------------------- | ---------------------------------------------------------------------------------------- |
| Slug / version             | `calce-cs2-cx2` / `2015-08-10` (Last-Modified of every pinned archive)                   |
| Source (`datasets.source`) | `calce`                                                                                  |
| Publisher                  | Center for Advanced Life Cycle Engineering (CALCE), University of Maryland               |
| Landing page               | <https://web.calce.umd.edu/batteries/data/>                                              |
| Data type                  | Real experimental measurements (`is_synthetic = false`, provenance `measured`)           |
| Chemistry                  | "LiCoO2 cathode. EDS results also showed trace elements of Manganese" (CALCE, both lots) |
| Rated capacity             | CS2: 1100 mAh; CX2: 1350 mAh                                                             |
| Form factor                | Small prismatic cells (CS2 5.4 × 33.6 × 50.6 mm, 21.1 g; CX2 6.6 × 33.8 × 50 mm, 28 g)   |

## Citation and usage

CALCE's data page states:

> "Usage of this data for publication purposes should include references to the CALCE battery
> data base and at least 3 articles referenced by CALCE and/or other contributors to this data
> collective."

Reference the data base as: CALCE Battery Research Group, University of Maryland, Battery Data,
<https://web.calce.umd.edu/batteries/data.htm>. Any publication must also cite at least three
CALCE articles describing these experiments (to be chosen from CALCE's article list when results
are published).

## Licence

- **All Rights Reserved.** The page footer reads "Copyright © 2014 by CALCE and the University
  of Maryland, All Rights Reserved"; no open licence is granted.
- Use: local research use with the citations above. This project does not redistribute the data
  (decision D8).

## Test protocol (CALCE)

All CS2 tests: CC 0.5C to 4.2 V, then CV 4.2 V until the current fell below 0.05 A; discharge
cut-off 2.7 V unless specified. Selected cells (the 12 constant-current cells with xlsx data):

| Cells                 | Discharge (as stated)           |
| --------------------- | ------------------------------- |
| CS2_33, CS2_34        | constant current of 0.5C        |
| CS2_35–CS2_38         | constant current of 1C          |
| CX2_33, CX2_35        | constant current discharge 0.5C |
| CX2_34, CX2_36–CX2_38 | constant current discharge 1C   |

Not selected: variable-current, partial-cycle and pulsed tests (CS2_3, 5–9, 21, 24, 25; CX2_3,
4, 8, 16, 31, 32), the PL/PLN pouch cells, and the A123/K2 LFP cells.

## Files (pinned)

URL pattern `https://web.calce.umd.edu/batteries/data/<cell>.zip`; downloaded and verified
2026-11-15 (zip CRC check passed); total 695,088,031 bytes.

| File         | Bytes      | SHA-256                                                            |
| ------------ | ---------- | ------------------------------------------------------------------ |
| `CS2_33.zip` | 45,345,047 | `ce375e3826e840ff0986ceade0d324ba6515f0446697c947353aca097f232505` |
| `CS2_34.zip` | 43,836,986 | `229dcdc836f140f746c26316569c357b346994fddd3be1223b1e457805c484b4` |
| `CS2_35.zip` | 37,056,519 | `84d88cb98a43c02049f16c78806a78ec19084776ea5df8a4b7c2f8f7ba4589e5` |
| `CS2_36.zip` | 37,881,685 | `2e674f58bb6dc005c73bef10e87edbbd97afd041dde77a1d461a3c4ecac1b027` |
| `CS2_37.zip` | 41,513,048 | `8ed8aecbcbea2bcb17f455923a974be01ea21d7389210e1912d177de5b6af4a5` |
| `CS2_38.zip` | 42,811,100 | `98787427c10478425efd4f54d823805724daff1d2fcbd822b3a2d7006a1051d8` |
| `CX2_33.zip` | 86,700,450 | `f4dbca063a3731045b8a631f69532f7f43f0b3ada9736c0cfe3e07302d10b5da` |
| `CX2_34.zip` | 65,932,032 | `6e4be14140071843891b6a7395c9561754b45036b17e840bae33d253f615939d` |
| `CX2_35.zip` | 96,794,651 | `043e84ccd518f5e00fcee94ae8d2765ffe25fd11a87e028ad6903a8c61a8f15e` |
| `CX2_36.zip` | 73,909,895 | `45b9249cd0353ea0285484868e5a74c54d43c8ed153bf2d40e9376e9a1daf6ad` |
| `CX2_37.zip` | 53,311,138 | `d7989beff30881e1d0d50bc2d7c028e8237ca402004ffcefe693bbce35b9776d` |
| `CX2_38.zip` | 69,995,480 | `2bd64c8cc9ffe4f63664caf9ec51889ca32245c321151a361147755ad6f00e3f` |

## Format and measurements

One zip per cell holding Arbin tester exports: 414 `.xlsx` workbooks in total, 23–48 per cell
(`CX2_33` also has 3 `.txt` files). CALCE: "The numbers following the second '\_' is the date
that the file was downloaded which provides a chronological order of the files."

All 414 workbooks were checked (header row only, 2026-11-15). They share one 17-column header:

`Data_Point`, `Test_Time(s)`, `Date_Time`, `Step_Time(s)`, `Step_Index`, `Cycle_Index`,
`Current(A)`, `Voltage(V)`, `Charge_Capacity(Ah)`, `Discharge_Capacity(Ah)`,
`Charge_Energy(Wh)`, `Discharge_Energy(Wh)`, `dV/dt(V/s)`, `Internal_Resistance(Ohm)`,
`Is_FC_Data`, `AC_Impedance(Ohm)`, `ACI_Phase_Angle(Deg)`.

**There is no temperature column.** Cell temperature is not measured in these files (CALCE
provides thermocouple data only for CX2_4, which is not selected), so temperature stays null and
is reported as missing, never filled in (decision D3).

## Conversion (Phase 6 M4)

`python -m volterra_ml.loaders build calce-cs2-cx2` (about 100 s) writes
`processed/calce-cs2-cx2/2015-08-10/`: 12 batteries, **15,971 canonical discharge cycles**,
4,873,533 sample rows (219 MB). Verified facts it relies on (all 414 workbooks):

- Workbooks are ordered by their first sample time; the `M_D_YY` name sorts wrongly as text
  for every cell. Data is taken from the sheet with the Arbin header (`CX2_34_8_16_10.xlsx`:
  `Sheet1`); midnight `Date_Time` cells read as dates and are converted.
- `Cycle_Index` restarts in every workbook; a canonical cycle is a (workbook, `Cycle_Index`)
  group with discharge samples; its capacity is the increase of the workbook's cumulative
  `Discharge_Capacity(Ah)` over the group. Groups without discharge stay in the samples only.
- `CS2_35_2_10_11.xlsx` and `CS2_38_2_10_11.xlsx` repeat the `_2_4_11` workbooks row for row:
  recorded (`duplicate_of`) and skipped (4,885,068 − 11,535 rows). Any other overlap stops the
  loader.
- One empty cell in 4.9 million rows (`CS2_33_11_10_10.xlsx`, row 2, `Test_Time(s)`): null and
  flagged `empty_source_cells`.
- Temperature is null throughout and the per-cycle resistance is null (the tester's value is a
  held reading; the full series is in the samples). SOH uses the rated 1.1 / 1.35 Ah.
- CX2_33's three `.txt` exports are recorded as unconverted source files; the battery is
  flagged `earlier_history_not_converted`.

Flags: 292 `capacity_above_rated` (fresh CS2 cells deliver ~1.14 Ah), 489 `capacity_jump_up`,
134 `file_ends_during_discharge`, 1 `empty_source_cells`. Since migration 0004 (Phase 6 M5,
decision D3) all 15,971 cycles import with temperature and mean voltage null. The v1/v2
analytics need both, so the API answers `missing_measurement` for every CALCE cell and the app
shows its measured data on the Battery Data page only. The local
`test_calce_realdata.py` compares every sample value and every cycle capacity with the
workbooks.
