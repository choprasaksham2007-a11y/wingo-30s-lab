"""Versioned, serializable model and past-only features for the advanced predictor."""
import numpy as np

MIN_HISTORY = 20
MAX_HISTORY = 60
FEATURE_VERSION = "advanced-v1"


def advanced_features(history, target_pid, lookback=60):
    history = np.asarray(history, dtype=int)[-lookback:]
    if len(history) < min(MIN_HISTORY, lookback) or not np.isin(history, np.arange(10)).all():
        raise ValueError("Insufficient history or invalid digits")
    encoded = np.zeros((lookback, 10))
    encoded[:len(history)] = np.eye(10)[history[::-1]]
    mask = np.arange(lookback) < len(history)
    summaries = []
    for window in ((5, 10, 20, 40, 60, 100) if lookback >= 100 else (5, 10, 20, 40, 60)):
        recent = history[-min(window, lookback):]
        summaries.extend(np.bincount(recent, minlength=10) / len(recent))
        summaries.append(len(recent) / min(window, lookback))
    # Time since each digit, bounded by the actual observed uninterrupted history.
    for digit in range(10):
        positions = np.flatnonzero(history == digit)
        summaries.append((len(history) - positions[-1]) / lookback if len(positions) else 1.0)
        summaries.append(float(bool(len(positions))))
    for values in (history, history >= 5, history % 2, np.isin(history, [0, 5])):
        streak = 1
        while streak < len(values) and values[-streak-1] == values[-1]:
            streak += 1
        summaries.append(streak / lookback)
    transitions = np.bincount(history[1:][history[:-1] == history[-1]], minlength=10) + 1
    summaries.extend(transitions / transitions.sum())
    counter = int(target_pid[-4:])
    angle = 2 * np.pi * (counter - 1) / 2880
    summaries.extend([np.sin(angle), np.cos(angle)])
    summaries.extend(np.eye(10)[counter % 10])
    return np.concatenate([encoded.ravel(), mask.astype(float), summaries])


def build_advanced_rows(frame, max_history=MAX_HISTORY):
    histories, labels, ids = [], [], []
    for _, group in frame.groupby(frame["index"].diff().ne(1).cumsum()):
        numbers = group.number.to_numpy()
        pids = group.period_id.to_numpy()
        for i in range(MIN_HISTORY, len(group)):
            histories.append(numbers[max(0, i-max_history):i].copy())
            labels.append(numbers[i])
            ids.append(pids[i])
    return histories, np.asarray(labels), np.asarray(ids)


def aligned_probabilities(model, X):
    probabilities = np.zeros((len(X), 10))
    probabilities[:, np.asarray(model.classes_, dtype=int)] = model.predict_proba(X)
    return probabilities


def temper(probabilities, temperature):
    values = np.log(np.clip(probabilities, 1e-12, 1)) / temperature
    values = np.exp(values - values.max(axis=1, keepdims=True))
    return values / values.sum(axis=1, keepdims=True)


class AdvancedEnsemble:
    def __init__(self, members, weights, temperature=1.0):
        self.members = members
        self.weights = np.asarray(weights, dtype=float)
        if len(self.weights) != len(members) or (self.weights < 0).any() or not np.isclose(self.weights.sum(), 1):
            raise ValueError("Ensemble weights must match members and sum to one")
        self.temperature = temperature

    def predict_from_history(self, history, target_pid):
        probabilities = np.zeros((1, 10))
        for weight, member in zip(self.weights, self.members):
            x = advanced_features(history, target_pid, member["lookback"]).reshape(1, -1)
            if member["scaler"] is not None:
                x = member["scaler"].transform(x)
            probabilities += weight * aligned_probabilities(member["model"], x)
        return temper(probabilities, self.temperature)[0]
