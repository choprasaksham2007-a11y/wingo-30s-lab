import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from adaptive_patterns import AdaptivePatterns, categories
from test_category_predictor import cat, frame, state


def pid(i):
    return f'2026110810005{i:04d}'


class AdaptiveTests(unittest.TestCase):
    def test_overlapping_categories_are_exact_sums(self):
        for d in range(10):
            grouped = categories(np.eye(10)[d])
            self.assertEqual(grouped['size'].argmax(), int(d >= 5))
            self.assertEqual(grouped['primary'].argmax(), d % 2)
            self.assertEqual(grouped['colour'].argmax(), int(cat.labels([d])['colour'][0]))
            self.assertEqual(grouped['colour'][2:].sum(), int(d in (0, 5)))

    def test_predict_does_not_mutate_memory_and_future_is_not_visible(self):
        model = AdaptivePatterns()
        for i in range(1, 60):
            model.observe(pid(i), i % 10)
        original = copy.deepcopy(model)
        before = model.predict(pid(60))
        np.testing.assert_array_equal(before, model.predict(pid(60)))
        np.testing.assert_array_equal(model.losses, original.losses)
        self.assertEqual(model.observations, 59)
        model.observe(pid(60), 9)
        original.observe(pid(60), 0)
        self.assertFalse(np.array_equal(model.predict(pid(61)), original.predict(pid(61))))
        with self.assertRaises(ValueError):
            model.predict(pid(60))

    def test_gap_does_not_create_false_sequence_contexts(self):
        model = AdaptivePatterns()
        for i in range(1, 31):
            model.observe(pid(i), 8)
        previous = model.counts[('size_suffix_1', (1,))].copy()
        model.observe(pid(35), 2)
        np.testing.assert_array_equal(previous, model.counts[('size_suffix_1', (1,))])
        self.assertEqual(model.history, [2])
        model.observe(pid(36), 9)
        self.assertEqual(model.counts[('size_suffix_1', (0,))][9], 1)

    def test_pattern_memory_learns_real_synthetic_dependency(self):
        model = AdaptivePatterns(strength=16, rate=.1)
        hits = []
        # A deliberately deterministic sequence verifies learning ability, not real-world accuracy.
        for i in range(1, 1501):
            digit = 8 if (i - 1) % 9 < 5 else 1
            if i > 1100:
                hits.append(categories(model.predict(pid(i)))['size'].argmax() == (digit >= 5))
            model.observe(pid(i), digit)
        self.assertGreater(np.mean(hits), .9)
        self.assertGreater(np.ptp(model.weights()), .01)

    def test_restart_preserves_memory_and_skips_old_rounds(self):
        model = AdaptivePatterns()
        data = frame(75)
        self.assertEqual(model.ingest(data), 75)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.joblib'
            joblib.dump(model, path)
            restored = joblib.load(path)
            self.assertEqual(restored.ingest(data), 0)
            target = cat.next_period(data.period_id.iloc[-1])
            np.testing.assert_array_equal(restored.predict(target), model.predict(target))
            self.assertEqual(restored.observations, 75)

    def test_live_model_is_logged_immutably_and_rejects_wrong_cutoff(self):
        s, data = state(), frame(30)
        model = AdaptivePatterns()
        model.ingest(data)
        s['adaptive'] = {'model': model, 'model_id': 'test-pattern'}
        now = cat.round_end(data.period_id.iloc[-1]) + timedelta(seconds=1)
        prediction, _ = cat.forecast(s, data, now)
        self.assertIn('adaptive_digit', prediction)
        with tempfile.TemporaryDirectory() as tmp:
            db = cat.open_db(Path(tmp) / 'scores.sqlite3')
            try:
                with patch.object(cat, 'datetime', wraps=datetime) as clock:
                    clock.now.return_value = now
                    self.assertTrue(cat.record(db, s, prediction))
                    self.assertFalse(cat.record(db, s, prediction))
                self.assertEqual(db.execute('SELECT COUNT(*) FROM adaptive_predictions').fetchone()[0], 1)
                stored = json.loads(db.execute('SELECT digit_probs FROM adaptive_predictions').fetchone()[0])
                np.testing.assert_array_equal(stored, prediction['adaptive_digit'])
                model.observe(cat.next_period(data.period_id.iloc[-1]), 2)
                prediction, _ = cat.forecast(s, data, now)
                self.assertNotIn('adaptive_digit', prediction)
            finally:
                db.close()


if __name__ == '__main__':
    unittest.main()
