# Dataset files

`sample_1000_rounds.csv` contains the first 1,000 chronological canonical v19 rows, with seven columns. It is a format/reproduction sample, not a random sample.

Full release assets:

- `colour_raw_data_v19.csv`: 88,916 rounds, nine fields.
- `colour_ml_ready_v19.csv`: 88,911 examples, 23 fields; five preceding rounds.
- `Colour_Prediction_Dataset_v19.xlsx`: seven-sheet workbook containing both tables and supporting documentation.
- `WinGo_same_time_every_day_legacy.csv`: old 2,880-row pivot containing 88,865 observations, useful for snapshot reconciliation.

Verify the files against [SHA256SUMS.txt](SHA256SUMS.txt). Full downloads are ignored by Git when placed in this directory. Historical experiment inputs under `docs/evidence/vscode/` belong to their saved evaluation cohort and are not additional v19 rows.

Keep period IDs as strings. Spreadsheet software may round 17-digit numeric identifiers. Do not treat `target_premium`, `target_colour` or `target_size` as predictors of the same unresolved target digit. See [data provenance](../docs/DATA_PROVENANCE.md) for field definitions and timestamp limitations.
