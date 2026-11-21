import copy
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from adaptive_patterns import HierarchicalPatterns
from test_category_predictor import cat, frame, state
from view_live import render
from neural_predictor import period_index


class UpgradeTests(unittest.TestCase):
    def test_rare_long_digit_pattern_backs_off_to_shorter_pattern(self):
        m = HierarchicalPatterns()
        m.history = [8, 6, 6, 6]
        m.learned_through = '20261108100050020'
        m.last_index = period_index(m.learned_through)
        m.counts[('digit_suffix_1', (6,))] = np.eye(10)[2] * 100
        p = m.expert_probabilities('20261108100050021')
        positions = {name: i for i, name in enumerate(m.names)}
        for length in (2, 3, 4):
            np.testing.assert_array_equal(p[positions[f'digit_suffix_{length}']], p[positions['digit_suffix_1']])
        self.assertEqual(p[positions['digit_suffix_4']].argmax(), 2)
        self.assertEqual(p.shape, (40, 10))
        np.testing.assert_allclose(p.sum(axis=1), 1)

    def test_five_big_four_small_is_an_explicit_run_pair(self):
        m = HierarchicalPatterns()
        contexts = m.contexts('20261108100050021', [8] * 5 + [2] * 4)
        self.assertIn(('size_run_pair', (0, 4, 5)), contexts)
        self.assertIn(('digit_streak', (2, 4)), contexts)
        self.assertIn(('joint_suffix_3', (0, 0, 0)), contexts)

    def test_new_model_prediction_is_read_only_and_skips_repeated_learning(self):
        m = HierarchicalPatterns()
        data = frame(60)
        self.assertEqual(m.ingest(data), 60)
        before = copy.deepcopy(m)
        p = m.predict(cat.next_period(data.period_id.iloc[-1]))
        self.assertEqual(m.ingest(data), 0)
        np.testing.assert_array_equal(m.losses, before.losses)
        np.testing.assert_array_equal(p, before.predict(cat.next_period(data.period_id.iloc[-1])))

    def test_viewer_displays_both_probabilities_and_marks_expired_predictions(self):
        s, data = state(), frame()
        now = cat.round_end(data.period_id.iloc[-1]) + timedelta(seconds=1)
        p, _ = cat.forecast(s, data, now)
        with tempfile.TemporaryDirectory() as directory:
            db = cat.open_db(Path(directory) / 'scores.sqlite3')
            try:
                with patch.object(cat, 'datetime', wraps=datetime) as clock:
                    clock.now.return_value = now
                    cat.record(db, s, p)
                output = render(db, now)
                self.assertIn('BIG / SMALL PICK: BIG', output)
                self.assertIn('ESTIMATED CONFIDENCE: 60.00%', output)
                self.assertIn('Big: 60.00%     Small: 40.00%', output)
                self.assertIn('ROUND CLOSED', render(db, now + timedelta(minutes=1)))
                self.assertNotIn('LIVE |', render(db, now + timedelta(minutes=1)))
                cat.reconcile(db, frame(24))
                self.assertIn('RESULT: 3 (SMALL)', render(db, now + timedelta(minutes=1)))
                later = now + timedelta(seconds=30)
                next_prediction, _ = cat.forecast(s, frame(24), later)
                with patch.object(cat, 'datetime', wraps=datetime) as clock:
                    clock.now.return_value = later
                    cat.record(db, s, next_prediction)
                refreshed = render(db, later)
                self.assertIn('Period: 20261107100050025', refreshed)
                self.assertIn('LIVE |', refreshed)
            finally:
                db.close()


if __name__ == '__main__':
    unittest.main()
