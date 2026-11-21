# Big/Small, colour, and live learning

The live workflow now uses dedicated Big/Small and colour neural networks. It reads the existing collector and does not place bets. Earlier digit models and their prediction records are preserved separately.

## View and control

- Double-click `View-Live-Predictions.cmd` to follow the running background learner. Close and reopen an older viewer after switching to this workflow.
- `RECENT ACTUALS` shows the last twelve observed Big/Small results, oldest to newest, and the observed current streak. `NEXT CURRENT MODEL` is the fixed champion. `NEXT LEARNING MODEL` shows the adaptively trained challenger's forecast for the same upcoming period. Both predictions were already saved before they were displayed.
- `Check-Prediction-Score.cmd` shows Big/Small, Red/Green, and full-colour accuracy separately, plus challenger and simple-baseline scores.
- `Stop-Live-Predictions.cmd` stops the background worker and preserves its learning checkpoint.
- `Start-Live-Predictions.cmd` starts a visible session using that checkpoint. Ctrl+C stops it. A lock prevents two workers from updating the same learner.
- `Train-BigSmall-Colour.cmd` starts a new training run from historical plus collector data. Stop the learner before using this manual full-retraining command. Normal live learning needs no manual retraining.

## Exact target definitions

Small means digits 0–4; Big means 5–9. The four full-colour classes are Red (2,4,6,8), Green (1,3,7,9), Red+Violet (0), and Green+Violet (5). Red/Green probabilities include the corresponding Violet combination. Violet probability is the sum of the two Violet classes. It is not a third exclusive alternative to Red/Green.

Size and colour are separately trained target networks. Their displayed marginal predictions are not a claim that every most-likely label will happen together. All targets and evaluation outcomes are derived from the same observed digit.

With equally likely digits, the chance baselines are 50% for Big/Small, 50% for Red/Green, and 20% for the occurrence of Violet. Always saying “no Violet” would score 80%, which would not show skill. Full-colour accuracy is distinct: Red-only and Green-only each have a 40% chance. The program never presents Violet/non-Violet accuracy as evidence of beating the 50% Big/Small baseline.

## Real training and continuous learning

The initial training run used 10,079 usable examples with up to 60 consecutive prior digits per example. It compared two neural architectures per target, selected architecture and stopping epoch on a later validation interval, calibrated probabilities on a separate interval, then tested on the newest 2,016 examples. The selected models each have hidden layers of 128, 64 and 32 units. They were refitted on all examples before live use.

Initial historical test: Big/Small 49.16%; Red/Green 49.90%; full colour 38.79%. These are not evidence of a reliable forecasting advantage, and previously explored history is not a new independent experiment.

The live system maintains a fixed current model (the champion) and an adaptive challenger for each target:

1. Log both models' complete probabilities before the target result is observed. Entries cannot be revised.
2. Once the collector supplies that exact period, score both predictions against the same actual digit.
3. Update only challenger weights with the newly observed example and up to 31 replay examples from a buffer of the last 2,048 training examples. Earlier features for that example never include its own outcome. The scaler remains fixed; online learning uses a low learning rate.
4. Save the updated weights, optimizer, random-generator state, replay buffer, and learned-through period atomically. Restarting does not relearn already processed rounds.
5. After 1,000 paired, genuinely future scored rounds, compare challenger with champion, the fixed training-majority baseline, and 50% chance. A target is promoted only if all three directional tests pass the window's threshold and probability log loss is no worse. Colour promotion also requires no worse full-colour log loss, including Violet.
6. Start the next non-overlapping comparison window. Thresholds become stricter across repeated windows. No mid-window promotion is made after a lucky streak.

This is continuous learning and measured model replacement, not a guarantee that performance improves. Probability calibration from initial training can drift as the challenger learns; live scores and loss comparisons are essential. The significance checks are statistical screens, not proof of a secure generator's predictability or a guarantee of future results.

Streak length, recent category counts and ordered prior digits are already in the model inputs. A streak ending sometimes does not establish that it ends more often than chance predicts. The program does not force a reversal after several Small or Big results. Training replay samples are randomly selected, but forecasts themselves use the highest model probabilities; the same saved weights and input history yield the same predictions.

## Files

`models/latest_categories.json` identifies the persistent learning checkpoint and initial evaluation. The checkpoint contains both target networks and challenger weights. `results/category_predictions.sqlite3` holds category predictions, full probabilities for both systems, learning counters, model revision, deadlines, and actual outcomes. Earlier digit predictions remain in `results/live_predictions.sqlite3`.

The computer and collector must remain running. The watcher does not automatically restart after reboot. Missing rounds are not fabricated; learning and prediction require at least 20 preceding consecutive observed rounds. The display labels outcomes as estimated probabilities and never promises 90% accuracy.
