import copy
import io
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import category_predictor as cat
from neural_predictor import period_index, round_end


class Identity:
    def transform(self, X):
        return X


class Model:
    def __init__(self, probabilities):
        self.probabilities = probabilities
        self.updates = []

    def predict_proba(self, X):
        return np.tile(self.probabilities, (len(X), 1))

    def partial_fit(self, X, y):
        self.updates.append((X.copy(), y.copy()))


def frame(n=23):
    ids = ['2026110710005' + f'{i:04d}' for i in range(1, n+1)]
    return pd.DataFrame({'period_id': ids, 'number': np.arange(n) % 10,
                         'index': [period_index(p) for p in ids]})


def state():
    models = {'size': {'model': Model([0.4, 0.6]), 'temperature': 1},
              'colour': {'model': Model([0.2, 0.3, 0.1, 0.4]), 'temperature': 1}}
    return {'run_id': 'test', 'revision': 0, 'window': 1, 'updates': 0, 'decisions': [],
            'learned_through': '20261107100050021', 'trained_through': '20261107100050021',
            'champions': models, 'challengers': copy.deepcopy(models), 'scaler': Identity(),
            'buffer_X': np.zeros((40, 761)), 'buffer_numbers': np.arange(40) % 10,
            'rng': np.random.default_rng(42), 'baseline_size': 0, 'baseline_primary': 0}


class CategoryTests(unittest.TestCase):
    def test_view_shows_both_forecasts_and_observed_streak(self):
        s, data = state(), frame()
        p, _ = cat.forecast(s, data, round_end(data.period_id.iloc[-1]))
        p['champions_size'] = np.array([.7, .3])
        p['challengers_size'] = np.array([.2, .8])
        output = io.StringIO()
        with redirect_stdout(output):
            cat.print_forecasts(p, data)
        rendered = output.getvalue()
        self.assertIn('observed streak: Small x3', rendered)
        self.assertIn('NEXT CURRENT MODEL | 20261107100050024 | Small (70.0%)', rendered)
        self.assertIn('NEXT LEARNING MODEL | 20261107100050024 | Big (80.0%)', rendered)

    def test_target_mapping_and_violet_overlap(self):
        targets = cat.labels(np.arange(10))
        np.testing.assert_array_equal(targets['size'], [0]*5 + [1]*5)
        np.testing.assert_array_equal(targets['colour'], [2, 1, 0, 1, 0, 3, 0, 1, 0, 1])
        np.testing.assert_allclose(cat.primary_probabilities([0.2, 0.3, 0.1, 0.4]), [0.3, 0.7])

    def test_only_new_observed_rounds_update_challenger(self):
        s = state()
        self.assertEqual(cat.online_update(s, frame()), 2)
        self.assertEqual(s['updates'], 2)
        self.assertEqual(cat.online_update(s, frame()), 0)
        self.assertEqual(len(s['challengers']['size']['model'].updates), 2)
        self.assertEqual(len(s['champions']['size']['model'].updates), 0)
        self.assertEqual(s['learned_through'], '20261107100050023')
        self.assertEqual(s['challengers']['colour']['model'].updates[-1][1][-1], 0)

    def test_gap_is_not_learned_as_a_continuous_sequence(self):
        s = state()
        data = frame().drop(index=21).reset_index(drop=True)
        self.assertEqual(cat.online_update(s, data), 0)
        self.assertEqual(s['learned_through'], '20261107100050023')

    def test_target_label_does_not_enter_its_features(self):
        first, second = state(), state()
        a, b = frame(22), frame(22)
        b.loc[21, 'number'] = 9
        cat.online_update(first, a)
        cat.online_update(second, b)
        x1, y1 = first['challengers']['size']['model'].updates[0]
        x2, y2 = second['challengers']['size']['model'].updates[0]
        np.testing.assert_array_equal(x1, x2)
        self.assertNotEqual(y1[-1], y2[-1])

    def test_forecast_uses_only_next_round(self):
        s, data = state(), frame()
        p, reason = cat.forecast(s, data, round_end(data.period_id.iloc[-1]))
        self.assertIsNone(reason)
        self.assertEqual(p['period'], '20261107100050024')
        self.assertEqual(p['champions_size'].argmax(), 1)
        self.assertEqual(cat.primary_probabilities(p['champions_colour']).argmax(), 1)
        p, reason = cat.forecast(s, data, round_end('20261107100050024'))
        self.assertIsNone(p)

    def test_record_is_immutable_and_scored_by_same_period(self):
        s, data = state(), frame()
        now = round_end(data.period_id.iloc[-1]) + timedelta(seconds=1)
        p, _ = cat.forecast(s, data, now)
        with tempfile.TemporaryDirectory() as directory:
            db = cat.open_db(Path(directory) / 'predictions.sqlite3')
            try:
                with patch.object(cat, 'datetime', wraps=datetime) as clock:
                    clock.now.return_value = now
                    self.assertTrue(cat.record(db, s, p))
                    self.assertFalse(cat.record(db, s, p))
                self.assertEqual(cat.reconcile(db, data), [])
                messages = cat.reconcile(db, frame(24))
                self.assertEqual(len(messages), 1)
                self.assertIn('actual 3: Small, Green', messages[0])
                self.assertEqual(cat.reconcile(db, frame(24)), [])
            finally:
                db.close()

    def test_comparison_does_not_promote_equal_or_bad_challenger(self):
        truth = np.arange(100) % 2
        good = np.eye(2)[truth] * 0.8 + 0.1
        bad = good[:, ::-1]
        self.assertFalse(cat.compare_candidate(truth, good, good, np.zeros(100), 0.5, 0.01)['promote'])
        self.assertFalse(cat.compare_candidate(truth, good, bad, np.zeros(100), 0.5, 0.01)['promote'])
        self.assertTrue(cat.compare_candidate(truth, bad, good, np.zeros(100), 0.5, 0.01)['promote'])

    def test_cannot_promote_before_required_future_rounds(self):
        with tempfile.TemporaryDirectory() as directory:
            db = cat.open_db(Path(directory) / 'predictions.sqlite3')
            try:
                s = state()
                self.assertIsNone(cat.evaluate_window(s, db))
                self.assertEqual(s['window'], 1)
                self.assertEqual(s['revision'], 0)
            finally:
                db.close()

    def test_promotion_uses_one_completed_window_only(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            db = cat.open_db(Path(directory) / 'predictions.sqlite3')
            try:
                s = state()
                for i in range(20):
                    number = 1 if i % 2 else 8
                    size, colour = int(number >= 5), number % 2
                    good_s = np.eye(2)[size] * .8 + .1
                    bad_s = good_s[::-1]
                    good_c = np.eye(4)[colour] * .8 + .05
                    bad_c = np.eye(4)[1-colour] * .8 + .05
                    db.execute('INSERT INTO category_predictions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                               (f'{i:03d}', 'source', 'created', 'deadline', 'test', 0, i, 1, 'learned',
                                *[json.dumps(p.tolist()) for p in (bad_s, bad_c, good_s, good_c)], 0, 0, number, 'scored'))
                db.commit()
                result = cat.evaluate_window(s, db, required=20)
                self.assertTrue(result['decisions']['size']['promote'])
                self.assertTrue(result['decisions']['colour']['promote'])
                self.assertEqual(s['revision'], 2)
                self.assertEqual(s['window'], 2)
                self.assertIsNone(cat.evaluate_window(s, db, required=20))
            finally:
                db.close()

    def test_checkpoint_restart_does_not_relearn_rows(self):
        s = state()
        cat.online_update(s, frame())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'checkpoint.joblib'
            cat.atomic_save(s, path)
            restored = cat.joblib.load(path)
            self.assertEqual(cat.online_update(restored, frame()), 0)
            self.assertEqual(restored['updates'], 2)

    def test_single_writer_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'writer.lock'
            with cat.learner_lock(path):
                with self.assertRaises(RuntimeError):
                    with cat.learner_lock(path):
                        self.fail('Second writer must not start')
            with cat.learner_lock(path):
                pass


if __name__ == '__main__':
    unittest.main()
