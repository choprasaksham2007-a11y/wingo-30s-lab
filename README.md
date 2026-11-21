# WinGo 30S Lab

Can the last 100 rounds tell you whether the next digit will be Big or Small? WinGo 30S produces a digit every 30 seconds. This archive lets you compare the recorded outcomes with forecasts made from earlier rounds. Across 5,000 historical test rounds, the model called Big or Small correctly **2,413 times (48.26%)**. A simple rule based on the previous 100 rounds scored **51.68%** on the same test.

**[Download the complete VS Code project](https://github.com/choprasaksham2007-a11y/wingo-30s-lab/releases/download/v1.1.0/colour-ai-workspace.zip)** · **[Get the Excel workbook](https://github.com/choprasaksham2007-a11y/wingo-30s-lab/releases/download/v1.0.0/Colour_Prediction_Dataset_v19.xlsx)** · **[Read the whitepaper](docs/WHITEPAPER.md)**

![The first eight recorded digits were 0, 6, 6, 0, 0, 5, 4 and 7. Each card shows its recorded size and colour.](docs/figures/opening-rounds.svg)

The first record illustrates how the fields fit together. At the worksheet time **00:00:00**, the published premium was **71180**. Its last digit, **0**, makes the result **Small** and **Red + Violet**. All **88,916** completed records follow the last-digit rule. A forecaster has to make its pick before that round’s premium is available. [Inspect the first 1,000 rounds](data/sample_1000_rounds.csv)

## Open the project

| What you want to do | Where to start |
| --- | --- |
| Run the app in VS Code | [Download the workspace ZIP](https://github.com/choprasaksham2007-a11y/wingo-30s-lab/releases/download/v1.1.0/colour-ai-workspace.zip), extract it and open the `colour-ai` folder. It contains all 12 saved models and the databases used by the viewer. |
| Record new rounds or view a prediction | Follow the [collector and viewer instructions](colour-ai/README.md). The viewer shows the digit, Big/Small, colour and estimated confidence. |
| Explore the complete dataset | [Raw CSV · 88,916 rounds](https://github.com/choprasaksham2007-a11y/wingo-30s-lab/releases/download/v1.0.0/colour_raw_data_v19.csv) or [Excel workbook · 7 sheets](https://github.com/choprasaksham2007-a11y/wingo-30s-lab/releases/download/v1.0.0/Colour_Prediction_Dataset_v19.xlsx). |
| Work with historical features | [ML CSV · 88,911 examples](https://github.com/choprasaksham2007-a11y/wingo-30s-lab/releases/download/v1.0.0/colour_ml_ready_v19.csv). Each target has five preceding rounds. |

## How did the model score?

The saved VS Code experiment used 1,000 candidate features. It trained on 4,096 examples, selected model settings on the next 1,500, then scored the following 5,000 with the settings fixed. The table gives the actual number of correct predictions. Its reference rates assume independent, uniformly distributed digits.

| Prediction | Correct out of 5,000 | Accuracy | Reference rate |
| --- | ---: | ---: | ---: |
| Exact digit (0–9) | 438 | 8.76% | 10% |
| Big or Small | 2,413 | 48.26% | 50% |
| Primary colour (Red or Green) | 2,476 | 49.52% | 50% |
| Full colour set, including Violet | 1,951 | 39.02% | 40% for the most common single class |

The recent-100 Big/Small rule got **2,584** calls right, 171 more than the model. The researchers had already explored this history, so that result still needs a prospective test on fresh rounds. The evaluated models did not establish a reliable forecasting advantage. [Saved predictions](docs/evidence/vscode/thousand_test_predictions_5000.csv) · [Results and limitations](docs/RESULTS_AND_LIMITATIONS.md)

## Where the evidence comes from

- **VS Code** contains the training code, collectors, model checkpoints, live viewer and saved forecasts. [Browse the app](colour-ai/) · [Inspect the model inventory](models/README.md)
- **ChatGPT** contributed an earlier analysis of 88,865 observations. Matching its archived clock-time matrix to the current data identified 51 added rounds and 49 completed premiums. Every overlapping winning digit agreed. [Earlier report](docs/evidence/chatgpt/premium_analysis_2026-11-11.md) · [Snapshot reconciliation](docs/DATA_PROVENANCE.md)
- **Antigravity** contains the earlier workbook revisions, image-based digit checks and statistical audits. The historical “110 dimensions” report included hardcoded verdicts and checks with unsuitable statistical assumptions. The archive preserves those distinctions and links back to the source. [Additional Antigravity material](antigravity/README.md) · [Audit corrections](docs/CLAIM_LEDGER.md)

The recorded API evidence describes how results were distributed. The author's separate investigation attributes generation to a .NET cryptographic RNG. The archive lacks independent confirmation of the deployed generator, and no seed was recovered. [Infrastructure evidence](docs/INFRASTRUCTURE.md)

## Check the archive offline

From the repository root, run the following with Python 3.11 or newer. The command checks the sample’s period sequence, timestamps and digit mappings, then verifies the historical evidence manifest. It uses the Python standard library.

```console
python scripts/run_audit_suite.py
```

[Full-data verification instructions](docs/METHODS.md) · [Dataset checksums](data/SHA256SUMS.txt) · [Workspace file manifest](colour-ai/WORKSPACE_FILES.csv)

Research and curation by **Saksham Chopra**. [Long-form article](articles/medium_substack_post.md) · [LinkedIn draft](articles/linkedin_post.md) · [Citation](CITATION.cff) · [License](LICENSE) · [Data and third-party notices](THIRD_PARTY_NOTICES.md)
