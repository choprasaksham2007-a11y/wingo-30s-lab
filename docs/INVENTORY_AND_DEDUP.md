# Inventory and duplication decisions

The inventory covers **1,213 files** across the original VS Code research project, the Antigravity brain directory and scratch research scripts, the nested colour-extraction project, saved WinGo captures, and matching research downloads. It excludes dependency/cache/VCS directories and three unrelated scratch projects. This is a file/content-hash inventory, not a claim that every screenshot was manually inspected or every historical script executed.

- [Full inventory](evidence/file_inventory.csv): source alias, relative name, size, SHA-256, type, classification and disposition.
- [Duplicate groups](evidence/duplicate_groups.json): 21 byte-identical groups and the normalized-AST comparison results.
- [Summary and exclusions](evidence/inventory_summary.json).
- [Published artifact transformations](evidence/publication_manifest.csv).
- [Saved model inventory](../models/manifest.csv).

## Decisions

Three downloaded ChatGPT ZIPs are identical; one was extracted and all copies remain untouched. The Downloads and Antigravity v19 workbooks are identical; the release carries one copy. Several earlier raw/ML version pairs are identical despite different filenames. Those are historical versions, not additional observations. Empty logs and repeated metadata files are also grouped by hash.

CSV/schema/period inspection and the timestamp pivot reconciliation demonstrate overlapping snapshots. Datasets were never concatenated blindly. The richer VS Code collector file and canonical v19 are separate representations of overlapping recorded history, not two independent studies. Older gappy collector backups remain local.

Normalized AST comparison removes formatting/location differences for Python scripts. An equal AST indicates a narrow structural duplicate. Different ASTs do **not** prove different methods. In particular, the twenty-vector and 110-dimension scripts repeat several calculations and the same lag-five random-forest design. They are related implementations, not independent replications merely because their text differs.

## Model and extraction distinctions

Twelve `.joblib` files in the VS Code project are saved model artifacts. Three `.pkl` files in the extraction project contain serialized observation lists, as established by their generating scripts' `pickle.dump(all_obs, ...)` calls. They are catalogued as data, not counted as three extra trained models. No serialized file was opened through pickle/joblib.

## Publication boundary

The public repository contains selected code, sanitized metrics, historical prediction rows, the small sample, newly written documentation and audit checks. Full factual datasets are release assets. Model weights, private account/request captures, internal handoffs, third-party frontend bundles and screenshots are excluded from the public package. Their original files remain in place; retained hashes support provenance without exposing their content.

This release does not claim a complete license audit of every excluded local file. Source origins and licenses were reviewed for the selected public artifacts. No third-party GitHub implementation was supplied with an independently auditable deployment link, so none was copied or relicensed as project code.
