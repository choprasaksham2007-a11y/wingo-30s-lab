import sys
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import neural_predictor as nn


class IdentityScaler:
    def transform(self, value):
        return value


class FixedNetwork:
    def predict_proba(self, value):
        return np.array([[0.05] * 9 + [0.55]])


def frame(count=25):
    ids = ["2026110710005" + f"{i:04d}" for i in range(1, count+1)]
    return pd.DataFrame({"period_id": ids, "number": np.arange(count) % 10,
                         "index": [nn.period_index(pid) for pid in ids]})


def bundle():
    return {"model": FixedNetwork(), "scaler": IdentityScaler(), "temperature": 1,
            "trained_through": "20261106100052880", "lags": 20, "model_id": "test", "baseline_digit": 1}


class TemporalSafetyTests(unittest.TestCase):
    def test_midnight_rollover_is_consecutive(self):
        old, new = "20261231100052880", "20270101100050001"
        self.assertEqual(nn.next_period(old), new)
        self.assertEqual(nn.period_index(new) - nn.period_index(old), 1)
        self.assertEqual(nn.round_end(new) - nn.round_end(old), timedelta(seconds=30))

    def test_invalid_mode_or_counter_rejected(self):
        for pid in ("20261107100010001", "20261107100050000", "20261107100052881"):
            with self.assertRaises(ValueError):
                nn.period_index(pid)

    def test_target_outcome_is_not_a_feature(self):
        original = frame()
        changed = original.copy()
        changed.loc[20, "number"] = 7
        x1, y1, ids = nn.training_rows(original)
        x2, y2, _ = nn.training_rows(changed)
        np.testing.assert_array_equal(x1[0], x2[0])
        self.assertNotEqual(y1[0], y2[0])
        self.assertEqual(ids[0], original.period_id.iloc[20])

    def test_training_never_crosses_gaps(self):
        data = frame(42).drop(index=20).reset_index(drop=True)
        _, _, ids = nn.training_rows(data)
        self.assertEqual(list(ids), [data.period_id.iloc[-1]])

    def test_live_refuses_gap(self):
        data = frame().drop(index=15).reset_index(drop=True)
        now = nn.round_end(data.period_id.iloc[-1]) + timedelta(seconds=3)
        forecast, reason = nn.live_forecast(bundle(), data, now)
        self.assertIsNone(forecast)
        self.assertIn("consecutive", reason)

    def test_live_refuses_stale_data(self):
        data = frame()
        now = nn.round_end(nn.next_period(data.period_id.iloc[-1]))
        forecast, reason = nn.live_forecast(bundle(), data, now)
        self.assertIsNone(forecast)
        self.assertIn("too old", reason)

    def test_live_refuses_model_trained_on_future(self):
        data, model = frame(), bundle()
        model["trained_through"] = "20261108100050001"
        forecast, reason = nn.live_forecast(model, data, nn.round_end(data.period_id.iloc[-1]))
        self.assertIsNone(forecast)
        self.assertIn("retrospective", reason)

    def test_probabilities_and_correct_target(self):
        data = frame()
        forecast, reason = nn.live_forecast(bundle(), data, nn.round_end(data.period_id.iloc[-1]))
        self.assertIsNone(reason)
        self.assertEqual(forecast["target"], "20261107100050026")
        self.assertEqual(forecast["digit"], 9)
        self.assertAlmostEqual(float(forecast["probabilities"].sum()), 1)

    def test_prediction_is_immutable_and_scored_afterward(self):
        data, model = frame(), bundle()
        now = nn.round_end(data.period_id.iloc[-1]) + timedelta(seconds=3)
        forecast, _ = nn.live_forecast(model, data, now)
        with tempfile.TemporaryDirectory() as directory:
            connection = nn.open_database(Path(directory) / "test.sqlite3")
            try:
                with patch.object(nn, "datetime", wraps=datetime) as clock:
                    clock.now.return_value = now
                    self.assertTrue(nn.record_forecast(connection, model, forecast))
                    forecast["digit"] = 1
                    self.assertFalse(nn.record_forecast(connection, model, forecast))
                self.assertEqual(nn.reconcile(connection, data), [])
                self.assertEqual(connection.execute("SELECT digit, actual FROM predictions").fetchone(), (9, None))
                completed = nn.reconcile(connection, frame(26))
                self.assertEqual(completed, [("20261107100050026", 9, 5, "test")])
                self.assertEqual(connection.execute("SELECT digit, actual FROM predictions").fetchone(), (9, 5))
                self.assertEqual(nn.reconcile(connection, frame(26)), [])
            finally:
                connection.close()

    def test_late_inference_cannot_be_recorded(self):
        data = frame()
        forecast, _ = nn.live_forecast(bundle(), data, nn.round_end(data.period_id.iloc[-1]))
        with tempfile.TemporaryDirectory() as directory:
            connection = nn.open_database(Path(directory) / "test.sqlite3")
            try:
                with patch.object(nn, "datetime", wraps=datetime) as clock:
                    clock.now.return_value = forecast["deadline"]
                    self.assertFalse(nn.record_forecast(connection, bundle(), forecast))
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM predictions").fetchone()[0], 0)
            finally:
                connection.close()

    def test_result_message_identifies_completed_round_and_outcome(self):
        output = io.StringIO()
        with redirect_stdout(output):
            nn.print_result("20261107100051396", 1, 1)
            nn.print_result("20261107100051397", 6, 5)
        self.assertIn("completed period 20261107100051396 | predicted 1 | actual 1 | HIT", output.getvalue())
        self.assertIn("completed period 20261107100051397 | predicted 6 | actual 5 | MISS", output.getvalue())


if __name__ == "__main__":
    unittest.main()
