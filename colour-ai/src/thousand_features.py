"""Exactly 1,000 documented past-only inputs. These are candidates, not proven rules."""
from datetime import timedelta

import numpy as np

from neural_predictor import round_end

VERSION = 'thousand-features-v1'
LOOKBACK = 500


def pattern_features(history, target_pid, with_names=False):
    h = np.asarray(history, dtype=int)[-LOOKBACK:]
    if len(h) < 20 or not np.isin(h, np.arange(10)).all():
        raise ValueError('Need at least 20 valid preceding digits')
    values, names = [], []
    def add(name, value):
        names.append(name)
        values.append(value)
    channels = {'digit': h, 'big': (h >= 5).astype(int), 'green': h % 2,
                'violet': np.isin(h, [0, 5]).astype(int)}
    # 400 lag inputs. Missing history has an explicit -1 sentinel.
    for name, sequence in channels.items():
        for lag in range(1, 101):
            add(f'{name}_lag_{lag}', sequence[-lag] if len(h) >= lag else -1)
    # 400 rolling summaries. Different windows are correlated, not independent evidence.
    for window in range(2, 102):
        for name in ('big', 'green', 'violet'):
            add(f'{name}_frequency_{window}', channels[name][-window:].mean() if len(h) >= window else -1)
        add(f'digit_repeat_frequency_{window}', np.mean(h[-window:][1:] == h[-window:][:-1]) if len(h) >= window else -1)
    # 100 target metadata inputs, all known before the target outcome.
    counter = int(target_pid[-4:])
    for modulus in range(2, 66):
        add(f'counter_modulo_{modulus}', counter % modulus)
    for i, character in enumerate(target_pid):
        add(f'period_digit_{i+1}', int(character))
    timestamp = round_end(target_pid) + timedelta(hours=5, minutes=30)
    angle = 2 * np.pi * (timestamp.hour * 3600 + timestamp.minute * 60 + timestamp.second) / 86400
    meta = {'counter': counter, 'IST_hour': timestamp.hour, 'IST_minute': timestamp.minute,
            'IST_second': timestamp.second, 'IST_weekday': timestamp.weekday(),
            'IST_day': timestamp.day, 'IST_month': timestamp.month, 'IST_ordinal': timestamp.toordinal(),
            'daily_sin': np.sin(angle), 'daily_cos': np.cos(angle),
            'weekly_sin': np.sin(2 * np.pi * timestamp.weekday()/7),
            'weekly_cos': np.cos(2 * np.pi * timestamp.weekday()/7),
            'ID_digit_sum': sum(map(int, target_pid)), 'ID_digit_sum_mod10': sum(map(int, target_pid)) % 10,
            'counter_tens': counter // 10, 'counter_hundreds': counter // 100,
            'counter_thousands': counter // 1000, 'IST_day_of_year': timestamp.timetuple().tm_yday,
            'available_history': len(h)}
    for name, value in meta.items():
        add(name, value)
    # 72 recent sequence codes, including two shifted versions of each sequence.
    for name in ('big', 'green'):
        for offset in (0, 1, 2):
            for length in range(1, 13):
                end = len(h) - offset
                code = -1
                if end >= length:
                    code = int(channels[name][end-length:end] @ (2 ** np.arange(length)))
                add(f'{name}_suffix_{length}_offset_{offset}', code)
    # 28 distances, runs, transitions, and run-pair inputs.
    for digit in range(10):
        positions = np.flatnonzero(h == digit)
        add(f'rounds_since_{digit}', len(h)-1-int(positions[-1]) if len(positions) else LOOKBACK+1)
    for name, sequence in channels.items():
        run = 1
        while run < len(sequence) and sequence[-run-1] == sequence[-1]:
            run += 1
        add(f'{name}_streak', run)
    counts = np.bincount(h[1:][h[:-1] == h[-1]], minlength=10) + 1
    for digit in range(10):
        add(f'past_transition_to_{digit}', counts[digit] / counts.sum())
    big = channels['big']
    run, previous = 1, 0
    while run < len(big) and big[-run-1] == big[-1]:
        run += 1
    while run+previous < len(big) and big[-run-previous-1] != big[-1]:
        previous += 1
    alternation = 1
    while alternation < len(big) and big[-alternation-1] != big[-alternation]:
        alternation += 1
    for name, value in [('run_pair_current_size', big[-1]), ('run_pair_current_length', run),
                        ('run_pair_previous_length', previous), ('size_alternation_length', alternation)]:
        add(name, value)
    result = np.asarray(values, dtype=np.float64)
    if len(result) != 1000 or len(set(names)) != 1000 or not np.isfinite(result).all():
        raise AssertionError('Feature contract violated')
    return (result, names) if with_names else result


class PatternBundle:
    """Saved fixed-weight models; never refits when evaluating final-test inputs."""
    def __init__(self, scaler, members, weights, temperatures, feature_names):
        self.scaler, self.members = scaler, members
        self.weights, self.temperatures = weights, temperatures
        self.feature_names = feature_names

    def predict(self, X):
        probabilities = self.member_probabilities(X)
        return {target: sum(weight * p for weight, p in zip(self.weights[target], members))
                for target, members in probabilities.items()}

    def member_probabilities(self, X):
        from advanced_model import temper
        scaled = self.scaler.transform(X)
        output = {}
        for target, members in self.members.items():
            output[target] = [temper(model.predict_proba(scaled if scaled_input else X), temperature)
                              for (name, model, scaled_input), temperature in zip(members, self.temperatures[target])]
        return output
