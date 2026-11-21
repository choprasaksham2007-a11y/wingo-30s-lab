# Previously trained models

The [v1.1.0 Colour AI workspace download](https://github.com/choprasaksham2007-a11y/wingo-prng-cryptanalysis/releases/download/v1.1.0/colour-ai-workspace.zip) includes all 12 saved model files. The inventory below describes the original v1.0.0 research release. See the [workspace manifest](../colour-ai/WORKSPACE_FILES.csv) for source and distributed hashes.

**No model was retrained, tuned, deserialized or replaced while preparing this publication.** Twelve original VS Code `.joblib` files remain in their existing local locations. The [manifest](manifest.csv) records relative source names, sizes and SHA-256 hashes. Model binaries are excluded from the initial public release; the saved evidence needed to assess their reported outcomes is published separately.

## Saved model families and evidence

| Family / artifact | Saved evidence | Publication interpretation |
|---|---|---|
| `neural_20261107T111335625015Z` | 2,001 test rows; digit 9.095%; baseline 10.045% | Saved evaluation; final production refit is not identical to the evaluated fit |
| `neural_advanced_20261107T113507284773Z` | Saved fold/candidate selection and final evaluation JSON | Preserved without rerunning selection |
| `categories_20261107T115239029718Z_checkpoint` | 2,016 test rows; size 49.16%; exact colour 38.79%; primary colour 49.90% | Live checkpoint may have changed after the saved evaluation |
| `categories_20261108T020744903096Z_checkpoint` | 2,110 test rows; size 49.62%; digit 9.48%; primary colour 51.14% | Saved evaluation, not a fresh score of the current checkpoint |
| Two `patterns_...` production / test-audit pairs | Saved JSON reports, separate audit weights | Versions preserved; no claim of independent datasets |
| `thousand_20261108T023304793710Z` | 4,096 training, 1,500 selection, 5,000 test rows; protocol/catalogue/predictions | Frozen evaluation parameters; explored historical data |
| `frozen_...`, `frozen_strong_...`, `before_patterns_...` | Hashed binaries and broader project inventory | No newly inferred evaluation score assigned to these weights |

See [saved evaluation files](../docs/evidence/vscode/). A report and a checkpoint with related names do not establish that the report measures the current checkpoint bytes. This is particularly important for models that had online updates. No claim is made that an autonomous live learner is currently active.

## The 1,000-feature test

| Target | Correct | Test accuracy | Saved baseline |
|---|---:|---:|---:|
| Big/Small | 2,413/5,000 | 48.26% | 49.20% |
| Primary Red/Green | 2,476/5,000 | 49.52% | 49.58% |
| Exact digit | 438/5,000 | 8.76% | 10.66% |
| Four exact colour sets | 1,951/5,000 | 39.02% | 38.92% |

The feature catalogue contains candidate numerical inputs, not 1,000 validated patterns. The saved protocol resets histories at gaps and requires consecutive preceding observations. Its test periods run from `20261026100051341` to `20261108100050305`; the protocol identifies the exact historical source hash. This cohort differs from the current 88,916-round v19 archive.

The saved recent-100 Big/Small baseline scored 51.68%; it is preserved with its interval and nominal paired comparison. Retrospective exploration prevents treating that alone as a validated future edge. The earlier saved verification also reports reproducing 40 model forecasts; that was a historical verification, **not repeated for this release**.

The three extraction `.pkl` files in the broader inventory are observation lists, not trained models. They also remain untouched and unpublished.
