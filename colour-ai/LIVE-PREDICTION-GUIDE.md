# Live number, Big/Small and colour predictions

Open `View-Live-Predictions.cmd`. If an old log viewer is already open, close it and open this file once to use the new display. The new viewer reads recorded forecasts directly and follows worker restarts automatically.
Each forecast shows Big/Small, primary Red/Green, Violet probability and an exact-number line with its top three digits. These are separately trained targets: their top choices can differ. Percentages are estimates, not demonstrated win rates.

The main panel explicitly labels the Big/Small pick, estimated confidence, and both Big and Small probabilities. Expired forecasts are marked ROUND CLOSED instead of being presented as current predictions. The log with sequence examples, scores and learning messages is available in `View-Detailed-Prediction-Log.cmd`.

## Example: does seeing many 6s mean 6 comes next?

No. The frequency method counts how common 6 has been recently. The sequence methods separately count what followed 6, or 6 then 6, on earlier occasions. A hypothetical sequence might have been followed by 3 more often than by another 6; that can favour 3 in that method even when 6 is frequent overall. Big/Small methods similarly learn what followed past size sequences and streaks. Each new result scores the methods before updating their counts and influence. Neural networks separately update their trained weights from the observed answer.

Training now compares a 40-method candidate with the original 32-method learner. The candidate adds three- and four-digit histories, joint size/colour sequences, consecutive run pairs (such as five Big then four Small), digit repeats and alternation lengths. Rare long patterns fall back to shorter matching sequences. In the latest chronological selection, the original 32-method configuration did better, so the live learner and its saved memory were retained. More methods do not automatically improve accuracy.

`NEXT CURRENT MODEL` is the reference network. `NEXT LEARNING MODEL` updates as results arrive. Both are logged before the target result and scored separately. The recent-100 majority rule is also recorded prospectively as a simple comparison.

`NEXT ADAPTIVE MODEL` is an additional experimental learner with 32 methods: Big/Small suffixes up to 12 rounds, Red/Green suffixes up to eight, digit transitions, streak lengths, recent frequencies and clock/counter groups. It combines their probability distributions and adjusts their weights only after seeing each actual answer. Its number, size and colour probabilities all come from one digit distribution. Their most likely individual choices can still differ because a size or colour includes several digits.

Its sequence counts, learned weights and last processed period persist inside the same live checkpoint. `SIMILAR PAST SEQUENCE` shows descriptive counts for a matching history with at least 20 earlier occurrences. These counts are not guaranteed next-round probabilities. `ADAPTIVE SCORES` reports separately logged future performance and an approximate 95% Big/Small accuracy interval; it does not establish an edge by itself. The adaptive learner does not automatically replace the neural reference.

The added method was selected using an earlier chronological segment, then tested with predictions made before each answer was learned. It did not beat chance on Big/Small in that historical test. The software now supports more explicit pattern learning; improved real-world accuracy remains unproven.

## Memory and learning

1. The collector saves actual rounds to `wingo_investigation/collected_data/wingo_30s_history.csv`.
2. The predictor matches actual results to previously recorded forecasts by period ID.
3. For each new usable result, the learning networks receive the preceding history and that result as the training answer. Features include past digits, frequencies, streak lengths, transitions and period-counter time features. Histories stop at missing rounds.
4. Each update mixes the new example with up to 31 earlier examples from a 2,048-example replay memory to help retain earlier learning.
5. Weights, replay memory, random-generator state, learning count and last learned period are saved. Restarting resumes the checkpoint without training the same rounds twice. The saved round history and prediction scores are separate durable records.
6. The next forecast is made for a still-unseen round. After 1,000 scored rounds, a comparison can promote a learning network to reference if it beats the reference, majority baseline and chance without worsening probability loss. Learning does not guarantee improvement.

Training compares 60- and 100-round contexts and two network sizes using chronological selection data. A later segment calibrates probabilities; the final segment measures performance. All available usable examples then fit the selected networks. Previously explored historical data is not conclusive evidence; future logged results matter.

For five Big followed by four Small, the model receives the past sequence and learns from what actually followed similar inputs. It does not assume the next outcome must be Big. A streak may occur by chance.

## Start, view and stop

- `Start-Live-Collector.cmd`: starts a background collector and requests Windows to prevent automatic idle sleep. Duplicate writers are blocked. Network errors and failed saves are retried.
- `View-Live-Collector.cmd`: views its output.
- `Stop-Live-Collector.cmd`: requests a final save and releases sleep prevention. Usually stops within one poll; an API backoff can delay this up to five minutes.
- `Start-Live-Predictions.cmd`: starts/resumes learning in the background.
- `View-Live-Predictions.cmd`: shows predictions and learning progress.
- `Check-Prediction-Score.cmd`: shows scores for the current model run.
- `Stop-Live-Predictions.cmd`: stops prediction processes; saved memory and scores remain.
- `Train-BigSmall-Colour.cmd`: full new training, including the number target. Stop the learning worker first. Previous checkpoints and run-specific scores remain; full retraining starts a new comparison run.
- `Train-1000-Patterns.cmd`: independent 1,000-input model comparison with exactly 5,000 eligible historical test rounds. Leaves live learning running. The final model and per-round probabilities are saved separately; this does not automatically replace the live model.

## The 1,000-input / 5,000-round experiment

The input catalog contains 400 lag inputs, 400 rolling summaries, 100 period-ID/time inputs, 72 sequence inputs and 28 streak, transition and distance inputs. These are correlated candidate features, not 1,000 proven predictive patterns. All historical inputs end before the target outcome; histories restart after missing rounds.

The newest 5,000 eligible historical examples are reserved for final testing. The preceding 1,500 examples select model configurations, probability calibration and mixture weights. Remaining earlier examples train the models. Two neural architectures, two boosted-tree settings, an extra-trees model, a linear model and the historical-frequency baseline compete for each of number, size and full colour. Red/Green is derived from the full-colour probabilities.

The selected model is saved before final test scores are computed. Its weights stay fixed throughout testing. Earlier observed test outcomes may appear in a later test round's input history; the current or future answer may not. The historical data was previously explored in this project, so this is an exploratory backtest, not a fresh live trial.

`results/latest_thousand_test.json` points to the saved model, report and all 5,000 per-round predictions. `src/verify_thousand_test.py` independently checks the saved probabilities and scores, reproduces 40 predictions from the saved model and compares a recent-100 baseline.

## What the seed investigation can establish

The existing public history API exposes results and period metadata. The audit in `results/api_rng_metadata_audit.json` records its field names and checks whether other collected fields add information. It does not access server internals. The experiment also tests two small rule families: a linear recurrence on previous digits modulo 10, and a linear function of the period counter modulo 10. A matching rule would still not identify a server seed. Failure only rejects those simple observable rules, not every possible generator.

No generator implementation, internal state or genuine seed has been identified. Statistical pattern fitting is not seed recovery. Proper random-number generators may be designed to resist prediction; this project's data does not establish which generator the server uses. Background reference: [NIST definition of prediction resistance](https://csrc.nist.gov/glossary/term/prediction_resistance).

## Sleep limitation

Keep the laptop plugged in, its lid open, and internet connected. The display may turn off. This machine reports network-disconnected standby. Actual Sleep, shutdown, power loss or a sleep-triggering lid close suspends collection; a local Python script cannot keep polling in those states. No permanent sleep or lid settings are changed. Collection while the laptop is truly asleep requires a separate always-on computer/server; one has not been deployed.

Windows behavior: https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate
