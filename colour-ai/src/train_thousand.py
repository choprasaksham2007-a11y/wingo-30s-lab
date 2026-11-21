"""Fixed 1,000-input model search with exactly 5,000 chronological final test rounds."""
import copy
import hashlib
import json
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import binomtest
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from advanced_model import build_advanced_rows, temper
from category_predictor import atomic_save, labels, learner_lock
from neural_predictor import ROOT, UTC, load_training_data
from thousand_features import LOOKBACK, VERSION, PatternBundle, pattern_features

TEST_ROWS = 5000
VALIDATION_ROWS = 1500


def partitions(count):
    test_start = count - TEST_ROWS
    validation_start = test_start - VALIDATION_ROWS
    if validation_start < 2000:
        raise ValueError('Need at least 8,500 eligible examples for this protocol')
    return validation_start, test_start


def evaluate(y, p, baseline):
    hit = p.argmax(1) == y
    base_hit = baseline == y
    wins, losses = int(np.sum(hit & ~base_hit)), int(np.sum(~hit & base_hit))
    interval = binomtest(int(hit.sum()), len(hit)).proportion_ci(method='wilson')
    return {'rounds': len(hit), 'correct': int(hit.sum()), 'accuracy': float(hit.mean()),
            'log_loss': float(log_loss(y, p, labels=range(p.shape[1]))),
            'baseline_accuracy': float(base_hit.mean()),
            'paired_p_vs_baseline': float(binomtest(wins, wins+losses, .5, alternative='greater').pvalue) if wins+losses else 1.,
            'accuracy_95_range': [float(interval.low), float(interval.high)],
            'five_1000_round_blocks': [float(part.mean()) for part in np.array_split(hit, 5)],
            'mean_predicted_confidence': float(p.max(1).mean())}


def fit_mixture(y, probabilities):
    correct = np.array([p[np.arange(len(y)), y] for p in probabilities])
    def objective(w):
        return -np.log(np.clip(w @ correct, 1e-12, 1)).mean() + .001 * np.sum(w*w)
    result = minimize(objective, np.ones(len(correct))/len(correct), method='SLSQP',
                      bounds=[(0, 1)]*len(correct), constraints={'type': 'eq', 'fun': lambda w:w.sum()-1},
                      options={'maxiter': 300, 'ftol': 1e-10})
    if not result.success:
        raise RuntimeError(f'Mixture selection failed: {result.message}')
    w = np.maximum(result.x, 0)
    return w / w.sum()


def recurrence_audit(histories, ids, numbers, train_end, test_start):
    previous = np.array([h[-1] for h in histories])
    counter = np.array([int(pid[-4:]) for pid in ids])
    results = {}
    for name, inputs in (('previous_digit_linear_mod10', previous), ('counter_linear_mod10', counter)):
        best = max(((int(np.sum((a*inputs[:train_end]+c)%10 == numbers[:train_end])), a, c)
                    for a in range(10) for c in range(10)))
        hits, a, c = best
        predicted = (a*inputs[test_start:]+c)%10
        results[name] = {'a': a, 'c': c, 'training_accuracy': hits/train_end,
                         'test_accuracy': float(np.mean(predicted == numbers[test_start:])),
                         'fits_all_training_outputs': bool(hits == train_end)}
    return {'diagnostic_rules': results, 'seed_recovered': False,
            'limitation': 'These are two small observable-digit rule families, not generator identification or seed recovery. Failure does not rule out other generators. No server-side algorithm, internal state or seed is available.'}


def main():
    frame = load_training_data()
    histories, numbers, ids = build_advanced_rows(frame, LOOKBACK)
    a, b = partitions(len(ids))
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')
    run_id = f'thousand_{stamp}'
    work = ROOT / 'results' / run_id
    work.mkdir(parents=True, exist_ok=False)
    frame.to_csv(work / 'source_snapshot.csv', index=False)
    protocol = {'run_id': run_id, 'features': 1000, 'feature_version': VERSION,
                'training_rows': a, 'selection_rows': b-a, 'test_rows': len(ids)-b,
                'training_last': str(ids[a-1]), 'selection_first': str(ids[a]), 'selection_last': str(ids[b-1]),
                'test_first': str(ids[b]), 'test_last': str(ids[-1]),
                'source_sha256': hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest(),
                'protocol': 'Train only earlier rows; select architectures, calibration and mixture weights on the following 1,500 rows. Freeze weights for all 5,000 final test rounds. Past observed test outcomes may enter later input histories. No test-driven model selection. Gaps reset histories; at least 20 preceding consecutive observations required.',
                'limitations': 'These historical records were explored in earlier project work. Results are an exploratory chronological backtest, not a fresh prospective trial. Features are correlated candidates, not 1,000 established patterns.'}
    (work / 'protocol.json').write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    print(json.dumps(protocol, indent=2), flush=True)
    _, feature_names = pattern_features(histories[0], ids[0], with_names=True)
    (work / 'feature_catalog.json').write_text(json.dumps(feature_names, indent=2), encoding='utf-8')
    X = np.array([pattern_features(h, pid) for h, pid in zip(histories, ids)])
    scaler = StandardScaler().fit(X[:a])
    xs = scaler.transform(X)
    members, weights, temperatures, selection = {}, {}, {}, {}
    for target, classes in (('size', 2), ('colour', 4), ('digit', 10)):
        y = labels(numbers)[target]
        pool = []
        # Every candidate sees all 1,000 inputs. The baseline also competes honestly.
        for hidden, alpha in (((64, 32), 20.), ((128, 64, 32), 50.)):
            model = MLPClassifier(hidden_layer_sizes=hidden, alpha=alpha, batch_size=128,
                                  learning_rate_init=.0005, random_state=42)
            best_loss, saved, best_epoch = float('inf'), None, 0
            for epoch in range(1, 61):
                model.partial_fit(xs[:a], y[:a], classes=np.arange(classes))
                loss = log_loss(y[a:b], model.predict_proba(xs[a:b]), labels=range(classes))
                if loss < best_loss - .0001:
                    best_loss, saved, best_epoch = loss, copy.deepcopy(model), epoch
                if epoch-best_epoch >= 8:
                    break
            name = f'neural_{hidden}_{alpha}'
            pool.append((name, saved, True))
            print(f'{target} | {name} selected epoch {best_epoch}', flush=True)
        for leaves in (7, 15):
            model = HistGradientBoostingClassifier(max_iter=80, max_leaf_nodes=leaves,
                min_samples_leaf=50, l2_regularization=10., learning_rate=.05, early_stopping=False, random_state=42)
            model.fit(X[:a], y[:a])
            pool.append((f'boosted_trees_{leaves}', model, False))
            print(f'{target} | boosted trees {leaves} fitted', flush=True)
        forest = ExtraTreesClassifier(n_estimators=192, max_depth=10, min_samples_leaf=25,
                                      max_features=.3, n_jobs=2, random_state=42).fit(X[:a], y[:a])
        pool.append(('extra_trees', forest, False))
        linear = LogisticRegression(C=.05, max_iter=1500, tol=.001).fit(xs[:a], y[:a])
        pool.append(('linear', linear, True))
        pool.append(('training_prior', DummyClassifier(strategy='prior').fit(X[:a], y[:a]), False))
        validation, temps, details = [], [], []
        for name, model, scaled_input in pool:
            raw = model.predict_proba(xs[a:b] if scaled_input else X[a:b])
            temperature = min((1, 2, 4, 8, 16, 32), key=lambda t: log_loss(y[a:b], temper(raw,t), labels=range(classes)))
            probabilities = temper(raw, temperature)
            validation.append(probabilities)
            temps.append(temperature)
            details.append({'name': name, 'temperature': temperature,
                            'selection_log_loss': float(log_loss(y[a:b], probabilities, labels=range(classes))),
                            'selection_accuracy': float(np.mean(probabilities.argmax(1) == y[a:b]))})
        w = fit_mixture(y[a:b], validation)
        for detail, weight in zip(details, w):
            detail['weight'] = float(weight)
        members[target], weights[target], temperatures[target], selection[target] = pool, w, temps, details
        print(f'{target} | selected mixture: ' + ', '.join(f'{d["name"]}={d["weight"]:.3f}' for d in details), flush=True)
    bundle = PatternBundle(scaler, members, weights, temperatures, feature_names)
    # Persist the chosen frozen model before reading any final test scores.
    path = ROOT / 'models' / f'{run_id}.joblib'
    atomic_save({'bundle': bundle, 'protocol': protocol, 'selection': selection}, path)
    predictions = bundle.predict(X[b:])
    predictions['primary'] = predictions['colour'][:, :2] + predictions['colour'][:, 2:]
    report = {'protocol': protocol, 'selection': selection, 'evaluation': {}}
    output = pd.DataFrame({'period_id': ids[b:], 'actual_digit': numbers[b:]})
    for name, p in predictions.items():
        truth = numbers % 2 if name == 'primary' else labels(numbers)[name]
        baseline = int(np.bincount(truth[:a]).argmax())
        report['evaluation'][name] = evaluate(truth[b:], p, baseline)
        output[f'{name}_prediction'] = p.argmax(1)
        output[f'{name}_confidence'] = p.max(1)
        for column in range(p.shape[1]):
            output[f'{name}_probability_{column}'] = p[:, column]
    report['rng_diagnostic'] = recurrence_audit(histories, ids, numbers, a, b)
    report['model_path'] = str(path)
    report['live_model_replaced'] = False
    output.to_csv(work / 'test_predictions_5000.csv', index=False)
    (work / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (ROOT / 'results/latest_thousand_test.json').write_text(json.dumps({'report': str(work/'report.json'),
        'predictions': str(work/'test_predictions_5000.csv'), 'model': str(path)}, indent=2), encoding='utf-8')
    print('FINAL 5,000-ROUND TEST: ' + json.dumps(report['evaluation'], indent=2), flush=True)
    print('Saved report: ' + str(work/'report.json'), flush=True)


if __name__ == '__main__':
    with learner_lock(ROOT / 'results/thousand_training.lock'), threadpool_limits(limits=2):
        main()
