# Reproduction and preservation methods

## What was performed for this release

Publication preparation inventoried and hashed local research files, identified identical content and normalized Python AST duplicates, extracted one evidence ZIP safely, verified its supplied manifest, reconciled snapshots, read saved metrics, and checked schemas and result mappings. No game API requests, new statistical experiments, seed searches, model fitting or model deserialization were performed.

The standard-library entry point validates data and summarizes saved results. This distinguishes **checking an existing artifact** from **repeating the experiment that created it**.

## Quick check

Use Python 3.11 or newer in the repository root:

```console
python scripts/run_audit_suite.py
python -m unittest discover -s tests -v
```

The sample command checks period syntax, chronological progression including calendar transitions, uniqueness, 30-second timestamp spacing, premium completeness, modulo-ten mapping and number/colour/size consistency. It also verifies the published source/evidence manifest and writes an ignored `outputs/publication_checks.json` file. A failed integrity check returns a nonzero exit code.

## Full-data check

Download the raw and ML CSV release assets into `data/`. Verify their hashes against `data/SHA256SUMS.txt`, then run:

```console
python scripts/run_audit_suite.py --data data/colour_raw_data_v19.csv --ml data/colour_ml_ready_v19.csv
```

This checks all target fields, the exact ordered target-ID sequence, all five number/colour/size lags, and the single-block marker. Missing/extra rows and labels inconsistent with the raw archive fail the check. It does not train on those fields.

The raw period format is treated as `YYYYMMDD` + game code `10005` + daily counter `0001..2880`. This is a dataset-specific validation rule, not a claim that every WinGo deployment shares that scheme. Recorded timestamps are parsed as naive worksheet times; this release does not infer timezone or convert dates from the period ID.

## Optional replay of archived calculations

The publication retains six Antigravity scripts. Their computations and known defects are preserved; only hardcoded paths and execution guards were changed. Their `pass`/`verified` fields must be read with [the claim ledger](CLAIM_LEDGER.md). Replay can reproduce flawed calculations and is **not validation of their scientific interpretation**.

Install optional dependencies in your own virtual environment:

```console
python -m pip install -r requirements-legacy.txt
python scripts/run_audit_suite.py --data data/colour_raw_data_v19.csv --replay ent
```

Available names: `ent`, `section2`, `section3`, `section4`, `section5_6`, `twenty`. Replay requires the exact canonical raw-file checksum, because the archived methods assume a long corpus. Outputs go to `outputs/legacy_replay/`, separate from preserved evidence. Numerical outputs may differ across library versions; the original execution environment is not fully pinned in the source archive.

`section4` and `twenty` include model fitting. They are blocked unless the caller explicitly adds `--allow-training`. **Neither was executed while preparing this release.** The other replay choices also constitute new executions and are never run by default. A valid replay command is an option for a future researcher, not a claim that its output was regenerated here.

Historical collection tools in `scripts/collection_reference/` are outside the audit workflow. They retain the original collection logic and require `WINGO_ENABLE_NETWORK=1` to run as scripts. No default command calls them. Their presence documents provenance, not a claim that the APIs remain available or permission to access restricted services.

## Saved model evidence

The original 12 VS Code model binaries are kept locally and hashed in `models/manifest.csv`. Their saved metrics, the 1,000-feature protocol/catalogue, 5,000 prediction rows and historical source snapshot are published separately. No `.joblib` or `.pkl` file is loaded by the reproduction entry point.

The earlier ChatGPT ZIP includes a narrative evaluation and collection tools, not the training code or fitted artifacts for its 17,762-round test. Those results are therefore traceable to a report but not fully executable from this release. The archived Antigravity scripts include some fitting code but no claim is made that saved weights exist for those particular fits.

## Evidence manifest and maintenance

`docs/evidence/publication_manifest.csv` records source alias, original hash, public destination, public hash and transformation for reused scripts/results. `file_inventory.csv` catalogs the broader local corpus without absolute user-directory paths. `data/SHA256SUMS.txt` covers downloadable data and the sample. Newly written prose, the wrapper and its tests are publication additions, not historical artifacts.

If a source artifact is intentionally edited, record the change and update the public checksum. Do not edit historical metrics to make them match a new method. Keep original local sources untouched and publish revised conclusions with explicit evidence status.
