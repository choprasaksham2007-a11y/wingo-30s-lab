# Repository Guidelines

## Evidence and architecture

This repository is a publication archive. `scripts/run_audit_suite.py` is the offline entry point; it validates a raw table, optionally validates the ML table, checks the publication manifest and reads saved evaluations. `docs/evidence/` contains historical artifacts, not fresh experiment outputs. `scripts/legacy/` retains earlier calculations with known defects and explicit execution guards. The collection reference scripts are separate from the audit workflow.

Maintain the distinction between VERIFIED local consistency checks, REPORTED historical findings, HYPOTHESIS and UNKNOWN. Do not turn source `pass` fields into scientific certification. Consult `docs/CLAIM_LEDGER.md` when editing interpretations. The default workflow must remain free of model loading, fitting and network calls.

## Validation commands

Run `python scripts/run_audit_suite.py` for the included sample. Run `python -m unittest discover -s tests -v` for integrity, rollover, evidence-hash and training-gate checks. Full-data validation requires downloaded release files and the command documented in `docs/METHODS.md`. The normal checks need Python 3.11+ and no external packages.

Do not run legacy replay or collectors merely to validate documentation changes. Replay is a new experiment; `section4` and `twenty` also fit models. An explicit request is needed for new research during maintenance.

## Preservation and edits

Keep original research files and model weights untouched. Never deserialize untrusted serialized artifacts to inventory them. Changes to included historical source/results need an explanation and an updated destination hash in `docs/evidence/publication_manifest.csv`. Preserve original source hashes.

Full datasets are release assets, while Git contains the 1,000-row sample and selected historical evidence. Do not add raw captures, private local paths, credentials or model binaries. Preserve period IDs as strings and identify the experimental cohort before comparing scores. The initial repository has no inherited commit convention or formatter configuration; do not imply that either exists.
