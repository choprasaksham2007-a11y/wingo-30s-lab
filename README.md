# WinGo 30S Lab

![WinGo 30S Lab. Across five 1,000-round blocks, the model's Big/Small accuracy ranged from 45.9% to 52.0%. The recent-100 rule ranged from 51.2% to 52.7%.](docs/figures/wingo-lab-cover.png)

**[Run the scorecard in Colab ↗](https://colab.research.google.com/github/choprasaksham2007-a11y/wingo-30s-lab/blob/main/examples/score-the-forecasts.ipynb)** · **[Download the VS Code project](https://github.com/choprasaksham2007-a11y/wingo-30s-lab/releases/download/v1.1.0/colour-ai-workspace.zip)** · **[Get the data](https://github.com/choprasaksham2007-a11y/wingo-30s-lab/releases/tag/v1.0.0)** · **[Read the paper](docs/WHITEPAPER.md)**

The model got **52%** of Big/Small calls right in its second block of 1,000 rounds. In the fourth, it got **45.9%**. Across all 5,000, a simple rule based on the previous 100 rounds beat the trained model by **171 correct calls**. This archive puts the forecasts, the underlying data and the scoring code in your hands.

### Try it in two cells

Open the notebook and run both cells to score the saved digit, size and colour forecasts. Then set `start, stop = 1000, 2000` and rerun the second cell to see how much the headline accuracy changes when you choose a different window. The notebook runs with standard Python and verifies the prediction file's checksum. [Preview the scorecard and its output on GitHub](examples/score-the-forecasts.ipynb)

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

The recent-100 Big/Small rule got **2,584/5,000 (51.68%)** right. These rounds had already been explored. Establishing a lasting advantage would require recording predictions on fresh rounds before the outcomes arrive. [Saved predictions](docs/evidence/vscode/thousand_test_predictions_5000.csv) · [Results and limitations](docs/RESULTS_AND_LIMITATIONS.md)

<details>
<summary><strong>Read one round of the dataset</strong></summary>

![The first eight recorded digits were 0, 6, 6, 0, 0, 5, 4 and 7. Each card shows its recorded size and colour.](docs/figures/opening-rounds.svg)

At the worksheet time **00:00:00**, the first published premium was **71180**. Its last digit, **0**, makes the result **Small** and **Red + Violet**. All **88,916** completed records follow that last-digit rule. A forecast must be recorded before the target round’s premium becomes available. [Inspect the first 1,000 rows](data/sample_1000_rounds.csv)

</details>

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

If you use the dataset or notebook, star the repository to save it for your next experiment. If you find a discrepancy, include the period ID, the snapshot you used and the value you expected. [Report a data or scoring issue](https://github.com/choprasaksham2007-a11y/wingo-30s-lab/issues)
