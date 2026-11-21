import sys
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import neural_predictor as nn
from advanced_model import advanced_features, build_advanced_rows, aligned_probabilities, AdvancedEnsemble
from train_advanced import select_strategy


class FixedAdvanced:
    def predict_from_history(self, past, target):
        self.seen = past.copy()
        return np.ones(10) / 10


class PartialClasses:
    classes_ = np.array([2, 7])

    def predict_proba(self, x):
        return np.tile([0.25, 0.75], (len(x), 1))


def frame():
    pids = ["2026110710005" + f"{i:04d}" for i in range(1, 101)]
    return pd.DataFrame({"period_id": pids, "number": np.arange(100) % 10,
                         "index": [nn.period_index(p) for p in pids]})


class AdvancedTests(unittest.TestCase):
    def test_scores_are_separated_by_model(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = nn.open_database(Path(directory) / "scores.sqlite3")
            try:
                for pid, model, digit in (("1", "old", 0), ("2", "new", 5)):
                    connection.execute("INSERT INTO predictions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                       (pid, "created", "deadline", "source", model, "trained", digit, "[]", 1, 5, "scored"))
                connection.commit()
                output = io.StringIO()
                with redirect_stdout(output):
                    nn.print_status(connection, "new")
                self.assertIn("1/1 = 100.0%", output.getvalue())
                self.assertNotIn("1/2", output.getvalue())
            finally:
                connection.close()

    def test_invalid_live_probabilities_are_rejected(self):
        class InvalidAdvanced:
            def predict_from_history(self, history, target):
                return np.full(10, float("nan"))
        data = frame()
        bundle = {"advanced_model": InvalidAdvanced(), "feature_version": "advanced-v1", "max_history": 60,
                  "lags": 20, "trained_through": "20261106100052880"}
        with self.assertRaisesRegex(ValueError, "Invalid model probabilities"):
            nn.live_forecast(bundle, data, nn.round_end(data.period_id.iloc[-1]))

    def test_padding_has_mask_and_no_false_zero_digits(self):
        x = advanced_features(np.ones(20, dtype=int), "20261107100050101", 60)
        encoded, mask = x[:600].reshape(60, 10), x[600:660]
        self.assertEqual(encoded.sum(), 20)
        self.assertEqual(encoded[:, 0].sum(), 0)
        self.assertEqual(mask.sum(), 20)
        self.assertTrue(np.isfinite(x).all())

    def test_future_outcomes_do_not_change_earlier_features(self):
        data = frame()
        h1, y1, ids = build_advanced_rows(data)
        data.loc[20:, "number"] = 7
        h2, y2, _ = build_advanced_rows(data)
        np.testing.assert_array_equal(advanced_features(h1[0], ids[0]), advanced_features(h2[0], ids[0]))
        self.assertNotEqual(y1[0], y2[0])

    def test_histories_reset_at_gap_and_cap_at_sixty(self):
        data = frame().drop(index=69).reset_index(drop=True)
        histories, _, ids = build_advanced_rows(data)
        self.assertTrue(all(len(h) <= 60 for h in histories))
        first_after = list(ids).index("20261107100050091")
        self.assertEqual(len(histories[first_after]), 20)
        self.assertNotIn("20261107100050090", ids)

    def test_live_uses_newest_segment_with_at_least_twenty(self):
        data = frame().drop(index=69).reset_index(drop=True)
        predictor = FixedAdvanced()
        bundle = {"advanced_model": predictor, "feature_version": "advanced-v1", "max_history": 60,
                  "lags": 20, "trained_through": "20261106100052880"}
        forecast, reason = nn.live_forecast(bundle, data, nn.round_end(data.period_id.iloc[-1]) + timedelta(seconds=1))
        self.assertIsNone(reason)
        self.assertIsNotNone(forecast)
        self.assertEqual(len(predictor.seen), 30)

    def test_live_rejects_gap_with_insufficient_recent_history(self):
        data = frame().drop(index=89).reset_index(drop=True)
        bundle = {"advanced_model": FixedAdvanced(), "feature_version": "advanced-v1", "max_history": 60,
                  "lags": 20, "trained_through": "20261106100052880"}
        forecast, reason = nn.live_forecast(bundle, data, nn.round_end(data.period_id.iloc[-1]))
        self.assertIsNone(forecast)
        self.assertIn("consecutive", reason)

    def test_class_probability_alignment(self):
        p = aligned_probabilities(PartialClasses(), np.zeros((2, 3)))
        self.assertEqual(p.shape, (2, 10))
        np.testing.assert_allclose(p[:, 2], 0.25)
        np.testing.assert_allclose(p[:, 7], 0.75)
        np.testing.assert_allclose(p.sum(axis=1), 1)

    def test_ensemble_weights_and_probabilities(self):
        member = {"lookback": 20, "scaler": None, "model": PartialClasses()}
        model = AdvancedEnsemble([member], [1], 4)
        p = model.predict_from_history(np.arange(20) % 10, "20261107100050021")
        self.assertAlmostEqual(p.sum(), 1)
        self.assertEqual(p.argmax(), 7)
        with self.assertRaises(ValueError):
            AdvancedEnsemble([member], [0.5])

    def test_strategy_selects_on_provided_validation_only(self):
        good = np.tile(np.eye(10)[3] * 0.9 + 0.01, (10, 1))
        bad = np.tile(np.eye(10)[4] * 0.9 + 0.01, (10, 1))
        selected, _ = select_strategy({"good": good, "bad": bad}, np.full(10, 3))
        self.assertEqual(selected["name"], "good")


if __name__ == "__main__":
    unittest.main()
