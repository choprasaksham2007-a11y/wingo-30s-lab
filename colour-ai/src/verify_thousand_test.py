"""Independently check the saved 5,000-round result artifact and frozen model."""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from advanced_model import build_advanced_rows
from category_predictor import labels
from neural_predictor import ROOT, read_rounds
from thousand_features import LOOKBACK, pattern_features
from train_thousand import evaluate


def main():
    pointer = json.loads((ROOT/'results/latest_thousand_test.json').read_text())
    report_path = Path(pointer['report'])
    report = json.loads(report_path.read_text())
    artifact = pd.read_csv(pointer['predictions'], dtype={'period_id': str})
    snapshot = read_rounds(report_path.parent/'source_snapshot.csv', 'period_id')
    histories, numbers, ids = build_advanced_rows(snapshot, LOOKBACK)
    saved = joblib.load(pointer['model'])
    a = report['protocol']['training_rows']
    b = a + report['protocol']['selection_rows']
    assert len(artifact) == 5000 and len(artifact.period_id.unique()) == 5000
    assert report['protocol'] == saved['protocol']
    assert report['protocol']['selection_last'] < report['protocol']['test_first']
    np.testing.assert_array_equal(artifact.period_id, ids[b:])
    np.testing.assert_array_equal(artifact.actual_digit, numbers[b:])
    for target, classes in (('size',2), ('colour',4), ('digit',10), ('primary',2)):
        p = artifact[[f'{target}_probability_{i}' for i in range(classes)]].to_numpy()
        assert np.isfinite(p).all() and (p >= 0).all()
        np.testing.assert_allclose(p.sum(1), 1)
        truth = numbers[b:] % 2 if target == 'primary' else labels(numbers[b:])[target]
        hits = int(np.sum(p.argmax(1) == truth))
        assert hits == report['evaluation'][target]['correct']
    # Re-run a fixed spread of saved-model forecasts to catch serialization/input mismatch.
    checks = np.linspace(b, len(ids)-1, 40, dtype=int)
    X = np.array([pattern_features(histories[i], ids[i]) for i in checks])
    predictions = saved['bundle'].predict(X)
    for target, p in predictions.items():
        stored = artifact.iloc[checks-b][[f'{target}_probability_{i}' for i in range(p.shape[1])]].to_numpy()
        np.testing.assert_allclose(p, stored, rtol=1e-12, atol=1e-12)
    # A simple recent-history baseline uses only prior observed digits for each row.
    recent = np.array([(np.bincount(h[-100:], minlength=10)+1)/(len(h[-100:])+10) for h in histories[b:]])
    recent_size = np.column_stack((recent[:, :5].sum(1), recent[:, 5:].sum(1)))
    majority = int(np.bincount((numbers[:a]>=5).astype(int)).argmax())
    extra = {'artifact_rows_verified': len(artifact), 'saved_model_forecasts_reproduced': len(checks),
             'probabilities_and_report_hits_verified': True,
             'recent_100_big_small_baseline': evaluate((numbers[b:]>=5).astype(int), recent_size, majority)}
    (report_path.parent/'verification.json').write_text(json.dumps(extra, indent=2), encoding='utf-8')
    print(json.dumps(extra, indent=2))


if __name__ == '__main__':
    with threadpool_limits(limits=2):
        main()
