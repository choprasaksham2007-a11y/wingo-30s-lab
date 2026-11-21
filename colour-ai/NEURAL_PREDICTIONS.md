# Colour AI neural predictions

**Current workflow:** the live launchers now run dedicated Big/Small and colour networks with an adaptive challenger. See [BIG_SMALL_COLOUR.md](BIG_SMALL_COLOUR.md). The digit-model instructions below describe the preserved earlier experiments.

The network predicts one digit (0–9) for the next WinGo 30-second round. It reads the existing live collector CSV; keep your collector running. It does not place bets or make additional API requests.

## Everyday use

1. A trained model is already saved and a background prediction worker was started. Double-click `View-Live-Predictions.cmd` to follow its predictions as they arrive. Closing this viewer leaves the background worker running.
2. Double-click `Check-Prediction-Score.cmd` to see the scored predictions, baseline, and uncertainty interval.
3. Double-click `Stop-Live-Predictions.cmd` to stop the background worker. To start a visible prediction session afterward, double-click `Start-Live-Predictions.cmd`. Leave that window open; press Ctrl+C to stop it.
4. To run the expanded search later, double-click `Train-Advanced-Model.cmd`. The current worker can keep running while training. A candidate replaces the selected model only if it passes the comparison described below. Existing models and predictions are preserved.

The hidden prediction worker's process and log paths are recorded in `results/neural_worker.json`. The stop launcher checks the process identity before stopping it. Stop that worker before starting the visible launcher.

The updated prediction worker checks for a newly selected model on every collector update and switches automatically. It does not automatically restart after reboot. One database row per target period prevents duplicate or revised predictions even if you accidentally run two watchers. Live scores are reported separately for each model; the score launcher also shows the combined total.

## Advanced training

- Searches 12 configurations: eight neural networks varying depth, regularization, history length and random seed; two logistic models; gradient boosting; and extra trees.
- Tests individual models, equal-weight ensembles of the top two/three/five candidates, and a diverse neural/linear/tree ensemble.
- Uses 20 or up to 60 uninterrupted previous digits, multiple recent-frequency windows, bounded time since a digit occurred, streaks, historical transitions and known clock/round-ID features. Missing older history is explicitly masked, never filled with invented results.
- Runs three expanding chronological folds: train 0–40% / validate 40–50%, train 0–50% / validate 50–60%, train 0–60% / validate 60–70%. Neural early stopping uses an inner chronological split entirely within each fold's training data.
- Chooses the candidate/ensemble by aggregate rolling-validation exact-number accuracy, breaking ties with probability log loss. Network training is capped at 80 epochs per search; stopping epochs for final fits are fixed from the rolling folds.
- Fits the chosen strategy on the oldest 70%, calibrates its probabilities on 70–80%, then evaluates once on 80–100%. Neither selection nor calibration uses the final test outcomes in this run.
- Retrains the original network on the same 70% prefix for a fair comparison. The old deployed bundle is not tested on historical outcomes that it was trained on.
- Activates the advanced model only if its final-test exact-number accuracy is higher and its log loss is no worse than that matched-prefix original model. This comparison is an engineering gate, not proof of a statistical advantage over chance. A failing candidate is saved for inspection without replacing the active model.
- Refits selected components on all available data for future predictions. Calibration transferred from the earlier fit still needs checking on live predictions.

The original `Train-Neural-Model.cmd` remains available for the simpler two-network search and unconditionally selects its resulting model. Use the advanced launcher for the expanded search and comparison gate.

### Completed advanced run: 7 November 2026

The search used 10,035 usable examples. The selected candidate was a `(64, 32)` neural network with 321 features from the last 20 rounds, trained for eight epochs; the larger 60-round networks and tested ensembles did not win rolling validation. The final production network was refitted on all 10,035 examples, through period `20261107100051380`.

On the same 2,007-round final test, the advanced candidate scored **229 correct (11.41%)**, versus **189 (9.42%)** for the original architecture retrained on the same earlier prefix. The simple majority baseline scored **203 (10.11%)**. Advanced log loss was 2.30236, compared with 2.30301 for the original and 2.30259 for uniform probabilities. The advanced candidate passed the stated replacement gate and was selected for live predictions.

Its 95% accuracy interval was 10.09%–12.88%. The paired comparison against the majority baseline had p=0.102, so this run did not establish a statistically reliable advantage over that baseline. This historical test has overlap with previously investigated data; prospective results remain essential. The holdout score is not a promised future win rate.

## Original training

- Combines processed workbook records with live collector records; collector values take precedence on overlap.
- Uses 20 previous consecutive digits, digit frequencies in the last 5/10/20 rounds, and the known target round's time-of-day encoding: 232 input features, ten output classes.
- Resets history at every data gap. Nothing is filled in or guessed for missing rounds.
- Uses the oldest 60% for training, the next 20% for architecture selection, stopping epoch and probability temperature, and the newest 20% for testing this run.
- Compares networks with hidden layers `(64, 32)` and `(128, 64)`. Stops when validation loss no longer improves, with at most 60 training epochs per candidate.
- Reports exact-digit accuracy, 95% interval, log loss, and comparisons with uniform guessing and the training-set majority digit.
- Refits the selected architecture on all available history for production. Holdout results describe the evaluation network, not future performance of this refitted network. Temperature is transferred from validation; live calibration must be measured prospectively.

The same historical data has been investigated previously. Repeatedly retraining until a historical result looks good is not independent evidence of prediction ability. The live record is the stronger check.

## Live records and safeguards

Predictions and their complete ten-digit probability vectors are stored in `results/live_predictions.sqlite3`, together with model identity, training cutoff, source period, target period, and creation/deadline timestamps. Existing predictions cannot be replaced by this program. Only their subsequently observed outcome and scoring time are filled in.

The program waits for 20 consecutive recent collector results, rejects stale data, and checks that a prediction is recorded at least two seconds before the target round's expected end. This uses the project's existing convention: the period's date is UTC, with 2,880 thirty-second rounds per day. Keep the computer clock correct. The date and period displayed identify which round a prediction belongs to; an old prediction is not a prediction for the current round.

The database records hit rate and a majority-digit baseline. A winning round by itself does not establish an advantage. The first training run achieved 9.10% on 2,001 held-out rounds versus a 10.04% majority baseline: no demonstrated advantage. Model-estimated probabilities are not proven win probabilities.

Each live update first prints `RESULT` with the completed period, predicted digit, actual digit and HIT/MISS, followed by its cumulative score. It then prints `NEXT PREDICTION (awaiting result)` for the upcoming result. That new prediction is not yet part of the completed-round accuracy. The `pending` count on the score line is taken before the new prediction is added; a pending prediction simply has no observed result yet. On startup, the viewer log also shows up to three recent completed results.

## Command-line equivalents

Run from this project folder in PowerShell:

```powershell
.venv\Scripts\python.exe src\neural_predictor.py train
.venv\Scripts\python.exe src\train_advanced.py
.venv\Scripts\python.exe -u src\neural_predictor.py watch
.venv\Scripts\python.exe src\neural_predictor.py predict
.venv\Scripts\python.exe src\neural_predictor.py status
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`predict` attempts one prospective prediction. `watch --seconds 120` runs a bounded two-minute session. `models/latest_neural.json` identifies the active model and evaluation report. Historical training runs are preserved as timestamped model and JSON files.
