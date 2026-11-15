# Dataset card: Severson et al. 2019 (fast-charging LFP cycle-life data)

| Field                      | Value                                                                                                       |
| -------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Slug / version             | `severson-2019` / `2019-03-11` (creation date of the three files on data.matr.io)                           |
| Source (`datasets.source`) | `severson`                                                                                                  |
| Publisher                  | Toyota Research Institute, Stanford University and MIT; hosted on data.matr.io (TRI)                        |
| Landing page               | <https://data.matr.io/1/projects/5c48dd2bc625d700019f3204>                                                  |
| Paper                      | Nature Energy 4, 383–391 (2019), doi:[10.1038/s41560-019-0356-8](https://doi.org/10.1038/s41560-019-0356-8) |
| Data type                  | Real experimental measurements (`is_synthetic = false`, provenance `measured`)                              |
| Chemistry                  | LiFePO4/graphite, A123 APR18650M1A, 1.1 Ah nominal                                                          |
| Cells                      | 124, cycled to failure under 72 fast-charging policies in a 30 °C chamber, in three batches                 |

## Citation

> K. A. Severson, P. M. Attia, N. Jin, N. Perkins, B. Jiang, Z. Yang, M. H. Chen, M. Aykol,
> P. K. Herring, D. Fraggedakis, M. Z. Bazant, S. J. Harris, W. C. Chueh and R. D. Braatz,
> "Data-driven prediction of battery cycle life before capacity degradation", Nature Energy 4,
> 383–391 (2019). doi:10.1038/s41560-019-0356-8

## Licence and usage terms (for review before download)

| Source checked (2026-11-15)                                                                     | What it says                                                                                                                                                                                                                           |
| ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| data.matr.io platform configuration (`/1/api/v1/edp/configuration`), shown in every page footer | **"All data is released under CC BY 4"**, linking to <https://creativecommons.org/licenses/by/4.0/>                                                                                                                                    |
| Paper, Data availability statement                                                              | "The datasets used in this study are available at https://data.matr.io/1."                                                                                                                                                             |
| Paper, Code availability statement                                                              | "Code for data processing is available at https://github.com/rdbraatz/data-driven-prediction-of-battery-cycle-life-before-capacity-degradation. Code for the modelling work is available from the corresponding authors upon request." |
| Authors' repository README                                                                      | "The data is available at https://data.matr.io/1/"; modelling code under an academic licence on request; "Only the data processing code is available without agreeing to a license." (code, not data)                                  |
| data.matr.io privacy policy                                                                     | TRI privacy policy, <https://www.tri.global/privacy-policy/>                                                                                                                                                                           |

**What CC BY 4.0 means for VOLTERRA AI**

- Permitted: use, share and adapt the data for any purpose, including commercial use.
- Required: **attribution** — credit the creators (cite the paper above and data.matr.io as the
  source), link to the licence, and indicate if changes were made (for example, derived cycle
  summaries).
- No additional restrictions may be applied to others' use of what is shared.
- This project still does not redistribute the data (decision D8); the licence would allow it.

## Files (pinned)

Downloaded with the user's approval under the CC BY 4.0 terms above and verified on 2026-11-15
(two independent SHA-256 implementations agree; files read-only). The sizes equal those
data.matr.io's file metadata reported before the download. Total 8,269,341,808 bytes (8.27 GB).

| File                                                   | URL (file id)                                                          | Bytes         | SHA-256                                                            |
| ------------------------------------------------------ | ---------------------------------------------------------------------- | ------------- | ------------------------------------------------------------------ |
| `2017-05-12_batchdata_updated_struct_errorcorrect.mat` | <https://data.matr.io/1/api/v1/file/5c86c0b5fa2ede00015ddf66/download> | 3,025,320,241 | `9d928ab978f0e3c70b31cb833a749fedd35094d01af76475d69b40aa3497f5ba` |
| `2017-06-30_batchdata_updated_struct_errorcorrect.mat` | <https://data.matr.io/1/api/v1/file/5c86bf13fa2ede00015ddd82/download> | 2,007,331,155 | `63ab200d09ecb237fee5ef3a5c5db76e3212e3206a0bd92f769e1427fed338b8` |
| `2018-04-12_batchdata_updated_struct_errorcorrect.mat` | <https://data.matr.io/1/api/v1/file/5c86bd64fa2ede00015ddbb2/download> | 3,236,690,412 | `62c30e413b63e6144720e016deed3661fac8468641794a5807b123fe84717998` |

## Format and measurements

**Verified from the file headers (2026-11-15):** each file is a MATLAB 7.3 MAT-file (HDF5
signature at byte 512), created by MATLAB on Dec 12 2018 (batch 1, MACI64), Feb 20 2018
(batch 2, PCWIN64) and Jun 18 2018 (batch 3, PCWIN64).

**From the paper and the authors' processing code (not yet checked against the files):**
per-cycle summaries such as discharge and charge capacity, internal resistance, temperature and
charge time, plus per-sample voltage, current, temperature and charge traces and each cell's
charging policy. M2 examines the HDF5 structure before any parser is written.

## Attribution (CC BY 4.0)

Any use of data derived from these files in VOLTERRA AI must credit: Severson et al., Nature
Energy 4, 383–391 (2019), doi:10.1038/s41560-019-0356-8; data from <https://data.matr.io/1>
(Toyota Research Institute), licensed under CC BY 4.0
(<https://creativecommons.org/licenses/by/4.0/>), and state that the data was processed (for
example into per-cycle summaries). The same attribution is recorded in the registry and in
`MANIFEST.json`.

## Notes for M2 (parsing; not done in M1)

- The paper and the authors' processing notebooks (`BuildPkl_Batch1-3.ipynb`) describe cells
  that are excluded or combined across batches. Check the exact list against those sources in
  M2; import all cells and flag exclusions rather than dropping them (decision D10).
