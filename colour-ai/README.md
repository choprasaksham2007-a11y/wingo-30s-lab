# Colour AI workspace

Download [the complete workspace ZIP](https://github.com/choprasaksham2007-a11y/wingo-30s-lab/releases/download/v1.1.0/colour-ai-workspace.zip) to get the application, model checkpoints, workbooks, collected rounds, databases and saved predictions together. Open the extracted `colour-ai` folder in VS Code. GitHub also lets you browse the source, tests and Windows launchers in this directory.

## Open the saved prediction viewer

Run these commands in PowerShell from the extracted folder. The original workspace used Python 3.14. Its dependency versions are in [requirements.txt](requirements.txt).

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src\view_live.py --once
```

The viewer reads the saved prediction database. Its timestamps show when those forecasts were recorded. The workspace includes 12 model files, so there is no initial training step to inspect the archive. Use the hashes in [the workspace manifest](WORKSPACE_FILES.csv) to verify the files before opening any serialized model.

## Record new rounds and predictions

For a fresh session, use two PowerShell terminals in this folder, with the dependencies above installed. In the first, run:

```powershell
.\.venv\Scripts\python.exe wingo_investigation\platsaas_collector.py --mode live --poll-interval 30
```

In the second, run:

```powershell
.\.venv\Scripts\python.exe src\category_predictor.py watch
```

The collector writes completed rounds to `wingo_investigation/collected_data/wingo_30s_history.csv`. The predictor uses the local history file. Open `View-Live-Predictions.cmd` for the viewer. Each new forecast requires current rounds and a running computer. Live data availability depends on the upstream provider. Starting the learner may update the extracted checkpoints, so keep the downloaded ZIP as your reference copy.

## What the download contains

On November 22, 2026 the working project contained **173 inventoried files** after excluding the virtual environment, caches and Git metadata. All 173 paths matched the manifest. Of those, **96** appear in both Git and the release ZIP, **65** are distributed through the ZIP alone, and **12** are marked local only. All 161 distributed files matched their original-file hashes in the working project and their published hashes in the ZIP. The ZIP itself matched the SHA-256 digest recorded by GitHub. [Inspect the file-by-file manifest](WORKSPACE_FILES.csv)

The ZIP preserves the project's directory layout, source, tests, launchers, training reports, saved models, raw workbook, processed data, historical exports, prediction scores and finalized collector database. [WORKSPACE_FILES.csv](WORKSPACE_FILES.csv) identifies the location, distribution status, and checksum for each inventoried project file. Its entries include the specific files kept local.

The virtual environment and Python caches can be rebuilt. Process locks, worker IDs, two raw HTTP capture files and a pending raw-response row were left out. Machine-specific paths were made relative. Three model copies had an embedded workstation directory replaced with an equal-length relative path prefix. The remaining bytes of those models and all bytes of the other nine models were preserved. No model was retrained.

The [original research release](https://github.com/choprasaksham2007-a11y/wingo-30s-lab/releases/tag/v1.0.0) has the canonical v19 data and the whitepaper. The VS Code model evaluations used the historical snapshots identified in their protocols.
