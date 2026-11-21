"""Persistent, past-only mixture of frequency, sequence, streak and clock experts.

Experts share one digit distribution, so size and overlapping colours agree with it.
Mixture weights learn from predictions BEFORE their outcomes enter the counts.
"""
from collections import defaultdict

import numpy as np

from neural_predictor import period_index


def categories(p):
    p = np.asarray(p)
    return {'digit': p,
            'size': np.stack((p[..., :5].sum(-1), p[..., 5:].sum(-1)), axis=-1),
            'primary': np.stack((p[..., ::2].sum(-1), p[..., 1::2].sum(-1)), axis=-1),
            'colour': np.stack((p[..., [2, 4, 6, 8]].sum(-1), p[..., [1, 3, 7, 9]].sum(-1),
                                p[..., 0], p[..., 5]), axis=-1)}


def outcome_loss(p, digit):
    grouped = categories(p)
    # Fixed objective prioritises Big/Small while retaining colour and exact number.
    return (-.5 * np.log(np.clip(grouped['size'][..., int(digit >= 5)], 1e-12, 1)) / np.log(2)
            -.3 * np.log(np.clip(grouped['primary'][..., digit % 2], 1e-12, 1)) / np.log(2)
            -.2 * np.log(np.clip(p[..., digit], 1e-12, 1)) / np.log(10))


def new_counts():
    return np.zeros(10)


class AdaptivePatterns:
    version = 'adaptive-patterns-v1'

    def __init__(self, strength=64., rate=.02):
        self.strength, self.rate = strength, rate
        self.names = (['uniform', 'all_history', 'recent_20', 'recent_100', 'recent_500']
                      + [f'size_suffix_{k}' for k in range(1, 13)]
                      + [f'colour_suffix_{k}' for k in range(1, 9)]
                      + ['digit_suffix_1', 'digit_suffix_2', 'size_streak', 'colour_streak',
                         'clock_hour', 'counter_mod10', 'half_minute'])
        self.counts = defaultdict(new_counts)
        self.totals = np.zeros(10)
        self.losses = np.zeros(len(self.names))
        self.history = []
        self.learned_through = ''
        self.last_index = None
        self.observations = 0
        self.updates = 0

    def weights(self):
        values = -self.rate * (self.losses - self.losses.min())
        weights = np.exp(values - values.max())
        # A small weight floor lets an expert recover if the generating process changes.
        return .98 * weights / weights.sum() + .02 / len(weights)

    def contexts(self, pid, history):
        big = tuple(int(x >= 5) for x in history)
        colour = tuple(x % 2 for x in history)
        result = []
        for prefix, values, maximum in (('size_suffix', big, 12), ('colour_suffix', colour, 8),
                                       ('digit_suffix', tuple(history), 2)):
            for k in range(1, maximum + 1):
                result.append((f'{prefix}_{k}', values[-k:]) if len(values) >= k else None)
        for prefix, values in (('size_streak', big), ('colour_streak', colour)):
            if not values:
                result.append(None)
                continue
            run = 1
            while run < len(values) and values[-run-1] == values[-1]:
                run += 1
            result.append((prefix, (values[-1], min(run, 20))))
        counter = int(pid[-4:])
        # Period counter follows UTC; adding IST offset changes hour phase only.
        result.extend([('clock_hour', ((counter * 30 + 19800) // 3600) % 24),
                       ('counter_mod10', counter % 10), ('half_minute', counter % 2)])
        return result

    def expert_probabilities(self, pid):
        index = period_index(pid)
        if self.last_index is not None and index <= self.last_index:
            raise ValueError('Prediction must follow the last learned period')
        history = self.history if self.last_index is not None and index == self.last_index + 1 else []
        prior = (self.totals + 10) / (self.totals.sum() + 100)
        result = [np.ones(10) / 10, prior]
        for length in (20, 100, 500):
            counts = np.bincount(history[-length:], minlength=10)
            result.append((counts + self.strength * prior) / (counts.sum() + self.strength))
        for key in self.contexts(pid, history):
            counts = self.counts.get(key) if key is not None else None
            result.append(prior if counts is None else (counts + self.strength * prior) / (counts.sum() + self.strength))
        return np.asarray(result)

    def predict(self, pid):
        return self.weights() @ self.expert_probabilities(pid)

    def observe(self, pid, digit):
        index = period_index(pid)
        if not isinstance(digit, (int, np.integer)) or not 0 <= digit <= 9:
            raise ValueError('Digit must be an integer from 0 to 9')
        if self.last_index is not None and index <= self.last_index:
            return False
        if self.last_index is not None and index != self.last_index + 1:
            self.history = []
        experts = self.expert_probabilities(pid)
        if len(self.history) >= 20:
            self.losses = .999 * self.losses + outcome_loss(experts, digit)
            self.updates += 1
        for key in self.contexts(pid, self.history):
            if key is not None:
                self.counts[key][digit] += 1
        self.totals[digit] += 1
        self.history.append(int(digit))
        self.history = self.history[-500:]
        self.learned_through, self.last_index = str(pid), index
        self.observations += 1
        return True

    def ingest(self, frame):
        updates = 0
        for row in frame.loc[frame.period_id > self.learned_through].itertuples(index=False):
            updates += self.observe(str(row.period_id), int(row.number))
        return updates

    def leaders(self, count=3):
        weights = self.weights()
        return [(self.names[i], float(weights[i])) for i in np.argsort(-weights, kind='stable')[:count]]

    def sequence_evidence(self, minimum=20):
        """Descriptive support for the longest sufficiently observed recent size suffix."""
        big = tuple(int(x >= 5) for x in self.history)
        for length in range(min(12, len(big)), 0, -1):
            counts = self.counts.get((f'size_suffix_{length}', big[-length:]))
            if counts is not None and counts.sum() >= minimum:
                return {'sequence': ' '.join('B' if x else 'S' for x in big[-length:]),
                        'observed': int(counts.sum()), 'followed_by_big': int(counts[5:].sum())}
        return None


class HierarchicalPatterns(AdaptivePatterns):
    """Long patterns back off to shorter matching histories when evidence is sparse."""
    version = 'hierarchical-patterns-v2'

    def __init__(self, strength=64., rate=.02):
        super().__init__(strength, rate)
        self.names += ['digit_suffix_3', 'digit_suffix_4', 'joint_suffix_1', 'joint_suffix_2',
                       'joint_suffix_3', 'size_run_pair', 'digit_streak', 'size_alternation']
        self.losses = np.zeros(len(self.names))

    def contexts(self, pid, history):
        result = super().contexts(pid, history)
        for k in (3, 4):
            result.append((f'digit_suffix_{k}', tuple(history[-k:])) if len(history) >= k else None)
        joint = tuple(2 * int(x >= 5) + x % 2 for x in history)
        for k in (1, 2, 3):
            result.append((f'joint_suffix_{k}', joint[-k:]) if len(joint) >= k else None)
        big = tuple(int(x >= 5) for x in history)
        run = 0
        while run < len(big) and big[-run-1] == big[-1]:
            run += 1
        previous = 0
        while run + previous < len(big) and big[-run-previous-1] != big[-1]:
            previous += 1
        result.append(('size_run_pair', (big[-1], min(run, 20), min(previous, 20))) if previous else None)
        repeats = 0
        while repeats < len(history) and history[-repeats-1] == history[-1]:
            repeats += 1
        result.append(('digit_streak', (history[-1], min(repeats, 20))) if history else None)
        alternating = 1 if big else 0
        while alternating < len(big) and big[-alternating-1] != big[-alternating]:
            alternating += 1
        result.append(('size_alternation', (big[-1], min(alternating, 20))) if big else None)
        return result

    def expert_probabilities(self, pid):
        result = super().expert_probabilities(pid)
        index = period_index(pid)
        history = self.history if self.last_index is not None and index == self.last_index + 1 else []
        context = self.contexts(pid, history)
        positions = {name: i for i, name in enumerate(self.names)}
        # Ordered shorter-to-longer within every family; absent data falls back exactly.
        for prefix, maximum in (('size_suffix', 12), ('colour_suffix', 8), ('digit_suffix', 4), ('joint_suffix', 3)):
            for length in range(2, maximum + 1):
                pos = positions[f'{prefix}_{length}']
                parent = result[positions[f'{prefix}_{length-1}']]
                key = context[pos - 5]
                counts = self.counts.get(key) if key is not None else None
                result[pos] = parent if counts is None else (counts + self.strength * parent) / (counts.sum() + self.strength)
        return result
