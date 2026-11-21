"""Use the frozen 1,000-input model live; adapt mixture weights on NEW outcomes only."""
import json
from pathlib import Path

import joblib
import numpy as np

from adaptive_patterns import categories
from neural_predictor import ROOT
from thousand_features import LOOKBACK, pattern_features


def load_model(pointer=ROOT / 'results/latest_thousand_test.json'):
    if not pointer.exists():
        return None
    metadata = json.loads(pointer.read_text(encoding='utf-8'))
    saved = joblib.load(metadata['model'])
    report = json.loads(Path(metadata['report']).read_text(encoding='utf-8'))
    return {'bundle': saved['bundle'], 'model_id': saved['protocol']['run_id'],
            'selection_last': saved['protocol']['selection_last'],
            'test_size_accuracy': report['evaluation']['size']['accuracy']}


def initialize(model, source):
    # Weight adaptation starts now, not by quietly reusing the reported 5,000-row test.
    return {'model_id': model['model_id'], 'started_through': source, 'learned_through': source,
            'updates': 0, 'losses': {name: np.zeros(len(members)+2)
                                    for name, members in model['bundle'].members.items()}}


def weights(model, memory, target):
    prior = np.append(.9 * np.asarray(model['bundle'].weights[target]), [.05, .05])
    losses = memory['losses'][target]
    log_weights = np.log(np.clip(prior, 1e-9, 1)) - .05 * (losses-losses.min())
    weights = np.exp(log_weights - log_weights.max())
    return .99 * weights/weights.sum() + .01/len(weights)


def expert_probabilities(model, history, target):
    x = pattern_features(history, target).reshape(1, -1)
    output = {name: np.array([p[0] for p in members])
              for name, members in model['bundle'].member_probabilities(x).items()}
    # Two explicit alternatives help a poor fitted component lose influence.
    recent = np.asarray(history[-100:], dtype=int)
    recent_digit = (np.bincount(recent, minlength=10)+1)/(len(recent)+10)
    recent_groups, chance_groups = categories(recent_digit), categories(np.ones(10)/10)
    return {name: np.vstack([p, recent_groups[name], chance_groups[name]]) for name, p in output.items()}


def predict(model, memory, history, target):
    if target <= max(model['selection_last'], memory['learned_through']):
        raise ValueError('The 1,000-input model cannot predict a round already learned')
    experts = expert_probabilities(model, history, target)
    fixed, learning = {}, {}
    for name, p in experts.items():
        fixed[name] = np.asarray(model['bundle'].weights[name]) @ p[:-2]
        learning[name] = weights(model, memory, name) @ p
        for values in (fixed[name], learning[name]):
            if not np.isfinite(values).all() or (values < 0).any() or not np.isclose(values.sum(), 1):
                raise ValueError('Invalid 1,000-input probabilities')
    return {'fixed': fixed, 'learning': learning, 'model_id': model['model_id'],
            'learned_through': memory['learned_through'], 'updates': memory['updates'],
            'test_size_accuracy': model['test_size_accuracy']}


def learn(model, memory, frame):
    updates = 0
    for _, group in frame.groupby(frame['index'].diff().ne(1).cumsum()):
        numbers, ids = group.number.to_numpy(), group.period_id.to_numpy()
        for i in range(20, len(group)):
            if ids[i] <= memory['learned_through']:
                continue
            p = expert_probabilities(model, numbers[max(0, i-LOOKBACK):i], ids[i])
            number = int(numbers[i])
            targets = {'digit': number, 'size': int(number >= 5),
                       'colour': 2 if number == 0 else 3 if number == 5 else number % 2}
            for name, probabilities in p.items():
                memory['losses'][name] = .995 * memory['losses'][name] - np.log(np.clip(probabilities[:, targets[name]], 1e-12, 1))
            memory['learned_through'] = str(ids[i])
            memory['updates'] += 1
            updates += 1
    if len(frame):
        memory['learned_through'] = max(memory['learned_through'], str(frame.period_id.iloc[-1]))
    return updates
