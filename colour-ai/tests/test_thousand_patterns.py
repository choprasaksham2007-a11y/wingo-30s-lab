import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from thousand_features import pattern_features, PatternBundle
from train_thousand import partitions, fit_mixture, recurrence_audit
from advanced_model import build_advanced_rows
from test_category_predictor import frame


class IdentityScaler:
    def transform(self, x):
        return x


class FixedModel:
    def __init__(self, p):
        self.p = p
    def predict_proba(self, x):
        return np.tile(self.p, (len(x), 1))


class ThousandTests(unittest.TestCase):
    def test_exact_feature_catalog_and_missing_history(self):
        x, names = pattern_features(np.arange(20) % 10, '20261108100050021', True)
        self.assertEqual(len(x), 1000)
        self.assertEqual(len(set(names)), 1000)
        self.assertTrue(np.isfinite(x).all())
        self.assertEqual(x[names.index('digit_lag_21')], -1)
        self.assertEqual(x[names.index('digit_lag_1')], 9)
        self.assertEqual(x[names.index('big_frequency_21')], -1)

    def test_no_target_or_later_outcome_in_features(self):
        data = frame(150)
        histories, _, ids = build_advanced_rows(data, 500)
        before = pattern_features(histories[80], ids[80])
        data.loc[100:, 'number'] = 8
        histories, _, ids = build_advanced_rows(data, 500)
        np.testing.assert_array_equal(before, pattern_features(histories[80], ids[80]))

    def test_gap_resets_history_for_all_thousand_inputs(self):
        data = frame(150).drop(index=100)
        histories, _, ids = build_advanced_rows(data, 500)
        index = list(ids).index('20261107100050122')
        self.assertEqual(len(histories[index]), 20)
        x, names = pattern_features(histories[index], ids[index], True)
        self.assertEqual(x[names.index('available_history')], 20)

    def test_final_test_is_exactly_five_thousand_and_disjoint(self):
        a, b = partitions(10600)
        self.assertEqual(10600-b, 5000)
        self.assertEqual(b-a, 1500)
        with self.assertRaises(ValueError):
            partitions(8000)

    def test_mixture_normalizes_and_frozen_prediction_does_not_train(self):
        y = np.arange(100) % 2
        good = np.eye(2)[y] * .8 + .1
        w = fit_mixture(y, [good, good[:, ::-1]])
        self.assertAlmostEqual(w.sum(), 1)
        self.assertTrue((w >= 0).all())
        self.assertGreater(w[0], .99)
        model = PatternBundle(IdentityScaler(), {'size': [('a', FixedModel([.7, .3]), True)]},
                              {'size': [1.]}, {'size': [1.]}, ['example'])
        np.testing.assert_allclose(model.predict(np.zeros((2,1)))['size'], [[.7,.3],[.7,.3]])

    def test_recurrence_diagnostic_does_not_claim_seed_recovery(self):
        digits = np.arange(100) % 10
        histories = [np.array([(d-1)%10]) for d in digits]
        ids = [f'2026110810005{i:04d}' for i in range(1,101)]
        report = recurrence_audit(histories, ids, digits, 50, 70)
        self.assertEqual(report['diagnostic_rules']['previous_digit_linear_mod10']['test_accuracy'], 1.)
        self.assertFalse(report['seed_recovered'])


if __name__ == '__main__':
    unittest.main()
