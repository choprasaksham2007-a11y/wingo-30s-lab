# Inside the Antigravity archive

The project’s first raw export contained **1,260 rounds**. Version 18 contained **10,992**. Version 19 added **77,924 periods** and changed the digit for **14** periods present in both v18 and v19. Each changed result has its own row in the comparison. [Dataset history](dataset-history.csv) · [See the 14 changes](v18-v19-digit-changes.csv)

An earlier comparison between the **88,865-observation ChatGPT matrix** and the same final v19 archive found **zero** digit changes on their overlap. Both results hold because the earlier inputs are different. [ChatGPT snapshot reconciliation](../docs/DATA_PROVENANCE.md)

## Read the evidence

| Material | What you can inspect |
| --- | --- |
| [Audit reports](reports/) | 20 historical documents about chronology, missing rounds, colour classification and workbook structure. Claims of “verification” in these documents reflect the statements of the original sessions. The publication’s [claim ledger](../docs/CLAIM_LEDGER.md) gives the later assessment. |
| [Observation files](observations/) | 37 additional files including corrections, spot checks, saved statistical results and digit-recognition evidence. |
| [Method listings](methods/) | 299 archived Python listings for digit recognition, dataset preparation and offline analysis. The text extension identifies historical source listings. Some require original input files or an earlier directory layout. |
| [Extraction evidence](extraction/) | 2,922 distinct observation states from three historical extraction passes, with ordered references back to each pass. The 20 digit-template arrays are stored in a numeric NPZ that can be read with NumPy’s `allow_pickle=False`. |
| [Normalized tables](tables/) | 163 distinct CSV or worksheet tables from 65 source files. Repeated rows point to an existing release CSV or a single stored historical row. |
| [Source index](file-index.csv) | One decision for each of the 3,108 source files inspected, with byte count and source SHA-256. The [coverage report](coverage.json) breaks down the decisions. |

## An example of the historical checks

The digit-classification reports record how the extraction process distinguished a **6** from an **8**. That matters because the two digits have the same Big/Small and primary colour labels. Those labels cannot resolve a disagreement between them. The research kept image shape observations alongside the chosen digit, allowing a later reviewer to examine why a row was accepted or changed. [Historical classifier report](reports/brain-game_rules_and_classifier_audit_report_v11.md) · [Recorded 6/8 checks](observations/scratch/changelog_batch2_6_vs_8.json)

## Read a historical table

From the repository root, use Python 3.11 or later. List the table IDs with:

```console
python antigravity/read_tables.py --list
```

To export a table, supply its ID, a new output filename, and the directories containing the [v1.0.0 data](https://github.com/choprasaksham2007-a11y/wingo-30s-lab/releases/tag/v1.0.0) and [extracted v1.1.0 workspace](https://github.com/choprasaksham2007-a11y/wingo-30s-lab/releases/tag/v1.1.0). For example, with the release CSVs in `downloads/data` and the extracted project in `downloads/colour-ai`:

```console
python antigravity/read_tables.py --table 0 --output first-raw-table.csv --datasets downloads/data --workspace downloads/colour-ai
python antigravity/read_tables.py --verify-all --datasets downloads/data --workspace downloads/colour-ai
```

The reader verifies the ordered values before writing a CSV. Values are strings, empty trailing cells are omitted, and worksheet styling, comments and visual layout are outside this representation. Source workbook hashes remain available in the index. A file marked `already in public release` points directly to the existing artifact.

## Scope and duplicate checks

The inventory covers the main project brain, six related audit folders, the colour-extraction project and top-level research scratch files. Unrelated sibling projects are outside its scope. The scan read every inventoried file, parsed public tables, and decoded source images for format inspection. Private conversations, screenshots, request captures, transient files and operational investigation scripts remain local. Session entries in the public index use opaque identifiers.

The comparison uses source hashes, normalized document text, JSON content, Python syntax trees and ordered table values. Two reports can discuss the same method while documenting different measured values or different source snapshots. Such reports retain their separate attribution. The earlier assessment of generator security and backend attribution remains available in [the whitepaper](../docs/WHITEPAPER.md) and [infrastructure notes](../docs/INFRASTRUCTURE.md).
