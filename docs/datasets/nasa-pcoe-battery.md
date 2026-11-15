# Dataset card: NASA PCoE Li-ion Battery Aging Datasets

| Field                      | Value                                                                                                                                                                        |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Slug / version             | `nasa-pcoe-battery` / `2022-09-18` (Last-Modified of the published archive)                                                                                                  |
| Source (`datasets.source`) | `nasa_pcoe`                                                                                                                                                                  |
| Publisher                  | NASA Ames Research Center, Prognostics Center of Excellence (PCoE)                                                                                                           |
| Landing page               | <https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/> (item 5)                                                     |
| Catalogue record           | <https://data.nasa.gov/dataset/li-ion-battery-aging-datasets> (identifier `DASHLINK_133`, issued 2010-09-13)                                                                 |
| Data type                  | Real experimental measurements (`is_synthetic = false`, provenance `measured`)                                                                                               |
| Chemistry                  | **Not stated by the publisher.** NASA describes "commercially available Li-ion 18650 sized rechargeable batteries" only; the chemistry is recorded as unknown, not inferred. |
| Rated capacity             | 2 Ah ("30% fade in rated capacity (from 2 Ah to 1.4 Ah)")                                                                                                                    |

## Citation

> B. Saha and K. Goebel (2007). "Battery Data Set", NASA Prognostics Data Repository, NASA Ames
> Research Center, Moffett Field, CA

(the citation the NASA PCoE repository gives for this data set).

## Licence and usage

- **Licence: not specified.** The data.nasa.gov catalogue record states "License not
  specified" with access level "public". No licence is assumed.
- Usage: cite as above. This project does not redistribute the data (decision D8).

## Files (pinned)

| File                     | URL                                                                  | Bytes       | SHA-256                                                            |
| ------------------------ | -------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------ |
| `5_Battery_Data_Set.zip` | <https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip> | 209,708,670 | `82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e` |

Published as `5. Battery Data Set.zip`; stored under a name without spaces, content
byte-identical. Downloaded and verified 2026-11-15 (zip CRC check passed).

## Format and measurements

A zip containing six zips (battery groups `BatteryAgingARC-FY08Q4`, `_25_26_27_28_P1`,
`_25-44`, `_45_46_47_48`, `_49_50_51_52`, `_53_54_55_56`) with 38 MATLAB `.mat` files and 10
`.txt` readme files. **B0025–B0028 appear in two groups**, so the archive holds 34 distinct cells
(B0005–B0007, B0018, B0025–B0034, B0036, B0038–B0056).

Per cell, `cycle` is a structure array; each entry has `type` (`charge`, `discharge` or
`impedance`), `ambient_temperature` (°C), `time` (start, MATLAB date vector) and `data`:

| Operation | Fields (units as published)                                                                                                         |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| charge    | `Voltage_measured` (V), `Current_measured` (A), `Temperature_measured` (°C), `Current_charge` (A), `Voltage_charge` (V), `Time` (s) |
| discharge | the same plus `Capacity` (Ah, "for discharge till 2.7V"); here `Current_charge` / `Voltage_charge` are measured at the load         |
| impedance | `Sense_current`, `Battery_current` (A), `Current_ratio`, `Battery_impedance`, `Rectified_impedance` (Ω), `Re`, `Rct` (Ω, estimated) |

Data acquisition rate is about 10 Hz (publisher). Discharges ran at different current loads to
preset voltage thresholds, some below the 2.7 V OEM recommendation; experiments stopped at 30%
fade in rated capacity.

## Notes for M2 (parsing; not done in M1)

- B0025–B0028 exist in two groups: compare the two copies and record which one is used.
- Capacity regeneration after rest periods is widely reported for this data set (ARCHITECTURE_PLAN
  §9.1); detect and flag it in M2, never remove it.
- The v1/v2 analytics need at least 221 cycles. Cells with fewer discharge cycles (to be counted
  in M2) get the data views only (decision D4).
