"""Offline publication checks and explicit replay of archived research scripts.

Default: validate supplied records and summarize saved results. Never trains,
loads serialized models, or contacts an API. Legacy replay is opt-in.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
LEGACY = {
    "ent": ("run_ent_metrics.py", False),
    "section2": ("run_110_audit_sec2.py", False),
    "section3": ("run_110_audit_sec3.py", False),
    "section4": ("run_110_audit_sec4.py", True),
    "section5_6": ("run_110_audit_sec5_6.py", False),
    "twenty": ("run_twenty_vector_audit.py", True),
}


def records(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def colour(n):
    if n == 0:
        return "Red+Violet"
    if n == 5:
        return "Green+Violet"
    return "Green" if n % 2 else "Red"


def period_position(pid):
    if not re.fullmatch(r"[0-9]{17}", pid) or pid[8:13] != "10005":
        raise ValueError("Expected a 17-digit WinGo 30S period ID")
    day = datetime.strptime(pid[:8], "%Y%m%d").date()
    index = int(pid[13:])
    if not 1 <= index <= 2880:
        raise ValueError("Daily round index must be 1..2880")
    return day.toordinal() * 2880 + index


def validate_data(path):
    rows = records(path)
    errors = Counter()
    required = {"Period ID", "timestamp", "premium", "number", "colour", "size"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("CSV is empty or lacks required v19 columns")
    seen = set()
    previous_position = previous_time = None
    for row in rows:
        pid = row["Period ID"]
        errors["duplicate_periods"] += pid in seen
        seen.add(pid)
        errors["missing_required_values"] += sum(not row[k] for k in required)
        try:
            position = period_position(pid)
            timestamp = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
            if previous_position is not None:
                gap = position - previous_position
                errors["missing_periods"] += max(0, gap - 1)
                errors["nonincreasing_periods"] += gap <= 0
                errors["timestamp_steps_not_30s"] += (timestamp - previous_time).total_seconds() != 30
            previous_position, previous_time = position, timestamp
        except (ValueError, TypeError):
            errors["invalid_period_or_time"] += 1
        if not re.fullmatch(r"[0-9]", row["number"]):
            errors["invalid_digit"] += 1
            continue
        n = int(row["number"])
        premium = row["premium"]
        if not re.fullmatch(r"[1-9][0-9]{4}", premium):
            errors["incomplete_premium"] += 1
        else:
            errors["premium_digit_mismatch"] += int(premium) % 10 != n
        errors["colour_mismatch"] += row["colour"] != colour(n)
        errors["size_mismatch"] += row["size"] != ("Big" if n >= 5 else "Small")
    summary = {
        "rows": len(rows), "unique_periods": len(seen), "sha256": digest(path),
        "first_period": rows[0]["Period ID"], "last_period": rows[-1]["Period ID"],
        "first_timestamp": rows[0]["timestamp"], "last_timestamp": rows[-1]["timestamp"],
        "errors": dict(sorted(errors.items())), "valid": not any(errors.values()),
        "scope": "Offline integrity checks; not a randomness or generator certification",
    }
    return summary, rows


def validate_ml(path, raw):
    rows = records(path)
    if not rows:
        raise ValueError("ML CSV is empty")
    expected_ids = [r["Period ID"] for r in raw[5:]]
    actual_ids = [r["Target Period ID"] for r in rows]
    errors = int(actual_ids != expected_ids)
    by_id = {r["Period ID"]: i for i, r in enumerate(raw)}
    for r in rows:
        i = by_id.get(r["Target Period ID"], -1)
        if i < 5:
            errors += 1
            continue
        for field in ["timestamp", "premium", "number", "colour", "size"]:
            errors += r["target_" + field] != raw[i][field]
        for lag in range(1, 6):
            for field in ["number", "colour", "size"]:
                errors += r[f"prev_{lag}_{field}"] != raw[i-lag][field]
        errors += r["block_id"] != "1"
    return {"rows": len(rows), "errors": errors, "valid": errors == 0, "sha256": digest(path)}


def verify_publication_manifest():
    entries = records(ROOT / "docs/evidence/publication_manifest.csv")
    mismatches = []
    for row in entries:
        p = (ROOT / row["published_path"]).resolve()
        if not p.is_relative_to(ROOT) or not p.is_file() or digest(p) != row["published_sha256"]:
            mismatches.append(row["published_path"])
    return {"artifacts": len(entries), "mismatches": mismatches, "valid": not mismatches}


def saved_results():
    evidence = ROOT / "docs/evidence"
    report = json.loads((evidence / "vscode/thousand_report.json").read_text())
    return {
        "status": "REPORTED: saved historical evaluation; no model was executed",
        "thousand_feature_protocol": report["protocol"],
        "thousand_feature_evaluation": report["evaluation"],
        "legacy_warning": "Saved pass/verified fields may be constants or use invalid null models. Read docs/CLAIM_LEDGER.md.",
        "antigravity_saved_files": sorted(p.name for p in (evidence / "antigravity").glob("*.json")),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/sample_1000_rounds.csv")
    parser.add_argument("--ml", type=Path, help="Validate full ML CSV against full raw CSV")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/publication_checks.json")
    parser.add_argument("--replay", nargs="+", choices=sorted(LEGACY), help="Explicitly rerun selected legacy analyses")
    parser.add_argument("--allow-training", action="store_true", help="Permit model fitting in section4/twenty replay")
    args = parser.parse_args(argv)
    if args.allow_training and not args.replay:
        parser.error("--allow-training requires --replay")
    if args.replay and any(LEGACY[s][1] for s in args.replay) and not args.allow_training:
        parser.error("section4/twenty train models; add --allow-training only if that is intended")
    try:
        data, rows = validate_data(args.data)
        result = {"data": data, "evidence_integrity": verify_publication_manifest(), "saved_results": saved_results()}
        if args.ml:
            result["ml"] = validate_ml(args.ml, rows)
        valid = data["valid"] and result["evidence_integrity"]["valid"] and result.get("ml", {"valid": True})["valid"]
        if args.replay:
            # Archived methods assume a long, complete corpus; reject accidental sample replay.
            expected = "055b076b0abbd2b74d06ed7c8172608062a8fca19255a988c90f57ab998ffb65"
            if not valid or data["sha256"] != expected:
                parser.error("Legacy replay requires the unchanged full v19 raw CSV and successful integrity checks")
            output_dir = args.output.resolve().parent / "legacy_replay"
            output_dir.mkdir(parents=True, exist_ok=True)
            if output_dir.is_relative_to((ROOT / "docs/evidence").resolve()):
                parser.error("Replay cannot overwrite archived evidence")
            env = dict(os.environ, WINGO_INPUT_CSV=str(args.data.resolve()), WINGO_OUTPUT_DIR=str(output_dir), WINGO_ALLOW_LEGACY="1", WINGO_ALLOW_TRAINING="1" if args.allow_training else "0")
            print("Replaying archived heuristics; their verdict labels are not validated conclusions.")
            for section in args.replay:
                subprocess.run([sys.executable, str(ROOT / "scripts/legacy" / LEGACY[section][0])], env=env, check=True)
            result["replayed"] = args.replay
        output = args.output.resolve()
        if output == args.data.resolve() or (args.ml and output == args.ml.resolve()) or output.is_relative_to((ROOT / "docs/evidence").resolve()):
            parser.error("Output must not overwrite input or archived evidence")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"{'PASS' if valid else 'FAIL'}: {data['rows']:,} rows; {data['unique_periods']:,} unique periods. Offline report: {output}")
        return 0 if valid else 1
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"Audit failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
