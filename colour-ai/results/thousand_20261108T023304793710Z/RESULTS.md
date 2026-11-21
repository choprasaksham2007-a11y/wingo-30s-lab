# 1,000-input model: 5,000-round test

Training and verification completed on 8 November 2026. The experiment did not establish an improvement in prediction accuracy or recover a game seed. The existing live predictor was not replaced.

## Data and method

- Training: 4,096 eligible historical rounds.
- Model selection and calibration: the next 1,500 rounds.
- Final test: the next 5,000 eligible rounds, from period 20261026100051341 through 20261108100050305.
- Inputs: 400 lag features, 400 rolling summaries, 100 time/period-ID features, 72 sequence features and 28 streak/transition/distance features.
- Compared per target: two neural networks, two boosted-tree models, extra trees, a linear model and a historical-frequency baseline. Model mixtures were chosen on selection data only.

The selected weights were frozen before final testing. Earlier observed results may appear in later test inputs, but no current or future answer is an input. Missing rounds break histories; only targets with at least 20 preceding consecutive observations are eligible. The 5,000 test examples are not necessarily 5,000 consecutive periods.

These records were examined in previous project work. This is an exploratory chronological backtest, not a new live trial. The 1,000 inputs are correlated candidates, not 1,000 proven rules.

## Actual test accuracy

- Big/Small: **2,413 / 5,000 = 48.26%**. Approximate 95% accuracy interval: 46.88%–49.65%. The training-majority baseline scored 49.20%.
- Red/Green: **2,476 / 5,000 = 49.52%**. Baseline: 49.58%.
- Exact digit: **438 / 5,000 = 8.76%**. Baseline: 10.66%.
- Full colour, distinguishing Red, Green, Red+Violet and Green+Violet: **1,951 / 5,000 = 39.02%**. Baseline: 38.92%.

The pre-existing recent-100 rule scored **2,584 / 5,000 = 51.68% Big/Small** on the same test periods. That is better than the larger model in this backtest; it is not proof of a reliable future advantage.

The larger model's Big/Small results in five successive 1,000-round blocks were 47.4%, 52.0%, 47.6%, 45.9% and 48.4%. Adding model complexity did not produce consistent gains.

## Seed investigation

One ordinary read of the public history API found no explicitly labelled seed, internal generator state or commitment fields. In all 7,740 collected records checked during the metadata audit, `premium` equalled the outcome digit and `sum` was zero.

Two limited observable rule families were checked, with parameters chosen from training data: a linear function of the previous digit modulo 10, and a linear function of the daily period counter modulo 10. Their final-test exact-digit accuracies were 9.84% and 9.90%. Neither reproduced all training outputs. These tests do not identify the generator or rule out every possible generator.

**No genuine seed was recovered.** The project has neither the server's generator implementation nor its internal state. Fitting a pattern to past digits is not equivalent to recovering a seed. Secure generators can be designed for [prediction resistance](https://csrc.nist.gov/glossary/term/prediction_resistance); this audit does not establish which generator this game uses.

## Saved evidence

- `report.json`: split boundaries, selected models, weights and test metrics.
- `feature_catalog.json`: every input name.
- `protocol.json`: the evaluation plan saved before model fitting and test scoring.
- `source_snapshot.csv`: the exact input history used for reproducibility.
- `test_predictions_5000.csv`: all 5,000 predictions, actual digits and probabilities.
- `verification.json`: independent count, score and probability checks, plus recent-100 baseline results.
- Saved model: `models/thousand_20261108T023304793710Z.joblib` in the project root.

All 53 project tests passed. Independent verification checked every saved test row and reproduced 40 evenly spaced forecasts from the saved model.
