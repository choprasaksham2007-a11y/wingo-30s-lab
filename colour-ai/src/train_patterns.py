"""Select an adaptive ensemble chronologically, then test it by predict-before-update."""
import copy
import hashlib
import json
from datetime import datetime

import joblib
import numpy as np
from scipy.stats import binomtest
from sklearn.metrics import log_loss
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from adaptive_patterns import AdaptivePatterns, HierarchicalPatterns, categories, outcome_loss
from advanced_model import advanced_features, build_advanced_rows, temper
from category_predictor import make_model, labels, atomic_save, learner_lock
from neural_predictor import ROOT, UTC, load_training_data


def metrics(probabilities, numbers):
    output = {}
    for name, p in probabilities.items():
        truth = (numbers % 2 if name == 'primary' else labels(numbers)[name])
        hit = p.argmax(axis=1) == truth
        interval = binomtest(int(hit.sum()), len(hit)).proportion_ci(method='wilson')
        output[name] = {'accuracy': float(hit.mean()), 'log_loss': float(log_loss(truth, p, labels=range(p.shape[1]))),
                        'accuracy_95_range': [float(interval.low), float(interval.high)]}
    return output


def train():
    frame = load_training_data()
    histories, numbers, ids = build_advanced_rows(frame, max_history=500)
    n = len(ids)
    if n < 2000:
        raise ValueError('Need 2,000 usable rounds')
    a, b = int(n * .6), int(n * .8)
    selection_ids, test_ids = set(ids[a:b]), set(ids[b:])
    candidates = [kind(strength, rate) for kind in (AdaptivePatterns, HierarchicalPatterns)
                  for strength in (16., 64.) for rate in (.02, .1)]
    selection_losses = [[] for _ in candidates]
    print(f'Train {a}; chronological selection {b-a}; predict-before-update test {n-b}', flush=True)
    # Stop ALL candidates before test. No selection is allowed to inspect test outcomes.
    for row in frame.loc[frame.period_id < ids[b]].itertuples(index=False):
        for i, model in enumerate(candidates):
            if row.period_id in selection_ids:
                selection_losses[i].append(float(outcome_loss(model.predict(row.period_id), row.number)))
            model.observe(row.period_id, int(row.number))
    selected = int(np.argmin([np.mean(x) for x in selection_losses]))
    model = candidates[selected]
    print(f'Selected {model.version}: strength={model.strength}, rate={model.rate}, {len(model.names)} experts', flush=True)
    before_test = copy.deepcopy(model)
    predictions = []
    for row in frame.loc[frame.period_id >= ids[b]].itertuples(index=False):
        if row.period_id in test_ids:
            predictions.append(model.predict(row.period_id))
        model.observe(row.period_id, int(row.number))
    probabilities = np.asarray(predictions)
    truth = numbers[b:]
    result = metrics(categories(probabilities), truth)
    recent = np.array([(np.bincount(h[-100:], minlength=10) + 1) / (len(h[-100:]) + 10) for h in histories[b:]])
    # A fixed neural comparator is fitted only on the earlier training block.
    # Temperature is chosen on selection; no final-test tuning or refitting.
    X = np.asarray([advanced_features(h, pid, 60) for h, pid in zip(histories, ids)])
    scaler = StandardScaler().fit(X[:a])
    xs = scaler.transform(X)
    reference = {}
    for name, classes in (('size', 2), ('colour', 4), ('digit', 10)):
        network = make_model((128, 64, 32))
        y = labels(numbers)[name]
        best_loss, saved, best_epoch = float('inf'), None, 0
        for epoch in range(1, 41):
            network.partial_fit(xs[:a], y[:a], classes=np.arange(classes))
            loss = log_loss(y[a:b], network.predict_proba(xs[a:b]), labels=range(classes))
            if loss < best_loss - .0001:
                best_loss, saved, best_epoch = loss, copy.deepcopy(network), epoch
            if epoch - best_epoch >= 8:
                break
        val_p = saved.predict_proba(xs[a:b])
        temperature = min((1, 2, 4, 8, 16, 32), key=lambda t: log_loss(y[a:b], temper(val_p, t), labels=range(classes)))
        reference[name] = temper(saved.predict_proba(xs[b:]), temperature)
        print(f'Neural comparator {name}: selected epoch {best_epoch}', flush=True)
    reference['primary'] = reference['colour'][:, :2] + reference['colour'][:, 2:]
    majority = int(np.bincount((numbers[:a] >= 5).astype(int)).argmax())
    hit = categories(probabilities)['size'].argmax(1) == (truth >= 5)
    majority_hit = majority == (truth >= 5)
    wins, losses = int((hit & ~majority_hit).sum()), int((~hit & majority_hit).sum())
    paired = float(binomtest(wins, wins+losses, .5, alternative='greater').pvalue) if wins+losses else 1.
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    model_id = f'patterns_{stamp}'
    report = {'model_id': model_id, 'training_rows': a, 'selection_rows': b-a, 'test_rows': n-b,
              'usable_rows': n, 'test_start': str(ids[b]), 'test_end': str(ids[-1]),
              'data_sha256': hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest(),
              'configuration': {'version': model.version, 'strength': model.strength, 'rate': model.rate, 'experts': len(model.names)},
              'selection_candidates': [{'version': m.version, 'strength': m.strength, 'rate': m.rate} for m in candidates],
              'selection_losses': [float(np.mean(x)) for x in selection_losses],
              'adaptive': result, 'neural_comparator': metrics(reference, truth),
              'recent_100': metrics(categories(recent), truth),
              'big_small_majority_accuracy': float(majority_hit.mean()), 'big_small_p_vs_majority': paired,
              'test_quarters_big_small': [float(x.mean()) for x in np.array_split(hit, 4)],
              'note': 'Historical data has been explored repeatedly. This is exploratory evidence. Adaptive and recent-history predictors update on earlier observed test rounds, never the current target. No guaranteed advantage or automatic promotion based on this report.'}
    path = ROOT / 'models' / f'{model_id}.joblib'
    report_path = ROOT / 'results' / f'{model_id}.json'
    atomic_save({'model': model, 'model_id': model_id, 'report': str(report_path), 'trained_rows': len(frame)}, path)
    # Preserve the pre-test state and exact probabilities so the reported test is reproducible.
    atomic_save({'model': before_test, 'ids': ids[b:], 'numbers': truth, 'probabilities': probabilities},
                ROOT / 'models' / f'{model_id}_test_audit.joblib')
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    pointer = ROOT / 'models/latest_patterns.json'
    temp = pointer.with_suffix('.tmp')
    temp.write_text(json.dumps({'checkpoint': str(path), 'report': str(report_path)}, indent=2), encoding='utf-8')
    temp.replace(pointer)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    with learner_lock(ROOT / 'results/pattern_training.lock'), threadpool_limits(limits=2):
        train()
