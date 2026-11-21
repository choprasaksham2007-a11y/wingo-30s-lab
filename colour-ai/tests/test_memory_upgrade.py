import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'wingo_investigation'))
from collector_runtime import collector_session
from test_category_predictor import cat, frame, state, Model
from advanced_model import advanced_features, build_advanced_rows


class MemoryUpgradeTests(unittest.TestCase):
    def test_hundred_history_and_number_survive_restart(self):
        s, data = state(), frame(103)
        s['lookback'] = 100
        width = len(advanced_features(np.arange(100) % 10, data.period_id.iloc[-1], 100))
        s['buffer_X'] = np.zeros((40, width))
        s['champions']['digit'] = {'model': Model(np.arange(1, 11) / 55), 'temperature': 1}
        s['challengers']['digit'] = {'model': Model(np.arange(1, 11) / 55), 'temperature': 1}
        s['baseline_digit'] = 0
        s['learned_through'] = data.period_id.iloc[-2]
        self.assertEqual(cat.online_update(s, data), 1)
        x, target = s['challengers']['digit']['model'].updates[-1]
        self.assertEqual(x.shape[1], width)
        self.assertEqual(target[-1], data.number.iloc[-1])
        self.assertEqual(len(s['champions']['digit']['model'].updates), 0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'memory.joblib'
            cat.atomic_save(s, path)
            restored = cat.joblib.load(path)
            self.assertEqual(cat.online_update(restored, data), 0)
            forecast, reason = cat.forecast(restored, data, cat.round_end(data.period_id.iloc[-1]))
            self.assertIsNone(reason)
            self.assertEqual(forecast['challengers_digit'].argmax(), 9)
            output = io.StringIO()
            with redirect_stdout(output):
                cat.print_forecasts(forecast, data)
            self.assertIn('RECENT 100 OBSERVED', output.getvalue())
            self.assertIn('NEXT LEARNING MODEL NUMBER | 9', output.getvalue())

    def test_hundred_features_use_past_only_and_reset_at_gap(self):
        data = frame(130)
        histories, _, ids = build_advanced_rows(data, 100)
        self.assertEqual(len(histories[-1]), 100)
        original = advanced_features(histories[80], ids[80], 100)
        data.loc[100:, 'number'] = 9
        changed, _, _ = build_advanced_rows(data, 100)
        np.testing.assert_array_equal(original, advanced_features(changed[80], ids[80], 100))
        data = data.drop(index=105)
        histories, _, ids = build_advanced_rows(data, 100)
        pos = list(ids).index('20261107100050127')
        self.assertEqual(len(histories[pos]), 20)

    def test_digit_forecasts_are_immutable_and_score_only_matching_future_result(self):
        s, data = state(), frame()
        s['baseline_digit'] = 0
        now = cat.round_end(data.period_id.iloc[-1]) + timedelta(seconds=1)
        prediction, _ = cat.forecast(s, data, now)
        prediction['champions_digit'] = np.eye(10)[3] * .9 + .01
        prediction['challengers_digit'] = np.eye(10)[2] * .9 + .01
        with tempfile.TemporaryDirectory() as tmp:
            db = cat.open_db(Path(tmp) / 'db.sqlite3')
            try:
                with patch.object(cat, 'datetime', wraps=datetime) as clock:
                    clock.now.return_value = now
                    self.assertTrue(cat.record(db, s, prediction))
                    prediction['champions_digit'] = np.ones(10) / 10
                    self.assertFalse(cat.record(db, s, prediction))
                self.assertEqual(np.argmax(json.loads(db.execute('SELECT main_probs FROM digit_predictions').fetchone()[0])), 3)
                cat.reconcile(db, frame(24))
                output = io.StringIO()
                with redirect_stdout(output):
                    cat.print_status(db, s)
                self.assertIn('NUMBER SCORES | current 1/1 (100.0%) | learning 0/1 (0.0%)', output.getvalue())
            finally:
                db.close()

    def test_collector_lock_and_power_release_on_failure(self):
        calls = []
        def power(flags):
            calls.append(flags)
            return 1
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'collector.lock'
            with self.assertRaises(ValueError):
                with collector_session(path, power):
                    with self.assertRaises(RuntimeError):
                        with collector_session(path, power):
                            self.fail('Duplicate collector must not start')
                    raise ValueError('test crash')
            self.assertEqual(calls, [0x80000001, 0x80000000])
            with collector_session(path, power):
                pass


if __name__ == '__main__':
    unittest.main()
