import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("audit", ROOT / "scripts/run_audit_suite.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class IntegrityTests(unittest.TestCase):
    def test_sample_is_complete_and_contiguous(self):
        result, rows = audit.validate_data(ROOT / "data/sample_1000_rounds.csv")
        self.assertTrue(result["valid"])
        self.assertEqual(len(rows), 1000)

    def test_corrupt_mapping_and_duplicate_are_rejected(self):
        rows = audit.records(ROOT / "data/sample_1000_rounds.csv")[:2]
        rows[1]["Period ID"] = rows[0]["Period ID"]
        rows[1]["premium"] = "10000" if rows[1]["number"] != "0" else "10001"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
            result, _ = audit.validate_data(path)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"]["duplicate_periods"], 1)
        self.assertEqual(result["errors"]["premium_digit_mismatch"], 1)

    def test_daily_period_rollover_requires_next_calendar_day(self):
        self.assertEqual(audit.period_position("20261012100050001") - audit.period_position("20261011100052880"), 1)
        self.assertEqual(audit.period_position("20261013100050001") - audit.period_position("20261011100052880"), 2881)

    def test_published_evidence_hashes(self):
        self.assertTrue(audit.verify_publication_manifest()["valid"])

    def test_training_replay_requires_explicit_opt_in(self):
        with self.assertRaises(SystemExit) as caught:
            audit.main(["--replay", "section4"])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
