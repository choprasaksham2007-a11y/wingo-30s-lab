"""
WinGo 30-Second Historical & Live Data Collector (Platsaas API)
==============================================================
Collects, displays, validates, and permanently stores WinGo 30S lottery results
from the Platsaas API with complete 5-digit premium preservation.

Storage Directory:
  collected_data/
    - wingo_30s_history.csv       : Full historical dataset (chronological, oldest to newest)
    - wingo_30s_history.sqlite    : High-integrity SQLite database (unique key: issueNumber + typeID)
    - raw_api_responses.jsonl     : Original API responses for auditable research
    - collector_state.json        : Resume state and backfill progress tracking
    - collector.log               : Complete timestamped logs
    - collection_summary.json     : Running statistics, distribution, and continuity summary

Usage:
  # Run built-in self-tests with sample API response:
  python platsaas_collector.py --test

  # Historical backfill (e.g. from 2026-10-12 to today):
  python platsaas_collector.py --mode backfill --start-date 2026-10-12 --end-date 2026-11-11

  # Test backfill (small 1-day sample):
  python platsaas_collector.py --mode backfill --start-date 2026-11-10 --end-date 2026-11-10 --max-pages 2

  # Continuous live monitoring (poll every 30s):
  python platsaas_collector.py --mode live --poll-interval 30

  # Audit and data-quality inspection:
  python platsaas_collector.py --mode audit
"""

import argparse
import csv
import json
import logging
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import requests

# Windows file locking support
try:
    import msvcrt
except ImportError:
    msvcrt = None

# ==============================================================================
# Configuration & Constants
# ==============================================================================

API_URL = "https://lotteryresultapi.platsaas.com/api/GetWinResult"
TYPE_ID = 30  # WinGo 30 Seconds

UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "collected_data"

# Canonical CSV Columns (Strict String/Integrity Preserved)
CSV_COLUMNS = [
    "issueNumber",
    "premium",
    "number",
    "colour",
    "typeID",
    "startTime",
    "endTime",
    "state",
    "intervalM",
    "expireSeconds",
    "fetched_at_utc",
    "fetched_at_ist",
    "source_api",
    "premium_last_digit",
    "premium_matches_number",
    # Derived Compatibility Columns:
    "color",
    "size",
    "primary_color",
    "has_violet",
    "parity",
    "issue_date",
    "game_code",
    "daily_round_num",
    "gap_from_prev",
    "is_consecutive",
]

# ==============================================================================
# Logging Setup
# ==============================================================================

def setup_logger(output_dir: Path) -> logging.Logger:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_file = output_dir / "collector.log"
    logger = logging.getLogger("platsaas_collector")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger

# ==============================================================================
# Concurrency Lock (Prevent Multiple Simultaneous Writers)
# ==============================================================================

class ProcessLock:
    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self.handle = None

    def acquire(self) -> bool:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.handle = open(self.lock_file, "a+b")
            if self.lock_file.stat().st_size == 0:
                self.handle.write(b"0")
                self.handle.flush()
            self.handle.seek(0)
            if msvcrt:
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except (OSError, IOError):
            if self.handle:
                try:
                    self.handle.close()
                except Exception:
                    pass
                self.handle = None
            return False

    def release(self):
        if self.handle:
            try:
                self.handle.seek(0)
                if msvcrt:
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                self.handle.close()
            except Exception:
                pass
            self.handle = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(
                f"Another collector process holds the lock on '{self.lock_file}'. "
                "Only one collector may write to the database/CSV at a time."
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

# ==============================================================================
# Data Validation & Normalization
# ==============================================================================

def parse_issue_metadata(issue_number: str) -> dict:
    """Extract date, game code, and daily round number from 17-digit issueNumber."""
    issue_str = str(issue_number).strip()
    if len(issue_str) == 17 and issue_str.isdigit():
        raw_date = issue_str[:8]
        formatted_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        game_code = issue_str[8:13]
        daily_round_num = int(issue_str[13:])
        return {
            "issue_date": formatted_date,
            "game_code": game_code,
            "daily_round_num": daily_round_num,
        }
    return {"issue_date": "", "game_code": "", "daily_round_num": -1}


def derive_outcome_fields(number_str: str, color_str: str) -> dict:
    """Calculate Big/Small, primary colour, violet flag, and parity."""
    num_str = str(number_str).strip()
    if num_str.isdigit() and 0 <= int(num_str) <= 9:
        num_int = int(num_str)
        size = "Big" if num_int >= 5 else "Small"
        parity = "even" if num_int % 2 == 0 else "odd"
    else:
        size = ""
        parity = ""

    col_str = str(color_str).lower().strip()
    if "red" in col_str:
        primary_color = "red"
    elif "green" in col_str:
        primary_color = "green"
    else:
        primary_color = col_str

    has_violet = 1 if "violet" in col_str else 0
    return {
        "size": size,
        "primary_color": primary_color,
        "has_violet": has_violet,
        "parity": parity,
    }


def validate_premium(premium_str: str, number_str: str) -> Tuple[str, int]:
    """
    Validates the 5-digit premium value against the winning number.
    Returns: (premium_last_digit, premium_matches_number)
      premium_matches_number:
         1: match (int(premium) % 10 == int(number))
         0: mismatch
        -1: invalid / non-5-digit / pending
    """
    prem_clean = str(premium_str).strip()
    num_clean = str(number_str).strip()

    if len(prem_clean) == 5 and prem_clean.isdigit():
        last_digit = prem_clean[-1]
        if num_clean.isdigit():
            match = 1 if int(prem_clean) % 10 == int(num_clean) else 0
            return last_digit, match
        return last_digit, 0
    return "", -1


def normalize_record(raw: dict, fetched_utc: str = "", fetched_ist: str = "") -> dict:
    """Normalize raw API response dictionary into canonical schema with full validation."""
    if not fetched_utc:
        now_utc = datetime.now(UTC)
        fetched_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        fetched_ist = now_utc.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST")

    issue_id = str(raw.get("issueNumber", "")).strip()
    prem = str(raw.get("premium", "")).strip()
    num = str(raw.get("number", "")).strip()
    col = str(raw.get("colour") or raw.get("color") or "").strip()
    type_id = int(raw.get("typeID") or raw.get("TypeId") or TYPE_ID)
    state = int(raw.get("state", 1 if (prem and num) else 0))
    start_time = str(raw.get("startTime", "")).strip()
    end_time = str(raw.get("endTime", "")).strip()
    interval_m = float(raw.get("intervalM", 0.5))
    expire_sec = int(raw.get("expireSeconds", 0))

    last_digit, matches_rule = validate_premium(prem, num)
    meta = parse_issue_metadata(issue_id)
    derived = derive_outcome_fields(num, col)

    return {
        "issueNumber": issue_id,
        "premium": prem,
        "number": num,
        "colour": col,
        "color": col,
        "typeID": type_id,
        "startTime": start_time,
        "endTime": end_time,
        "state": state,
        "intervalM": interval_m,
        "expireSeconds": expire_sec,
        "fetched_at_utc": fetched_utc,
        "fetched_at_ist": fetched_ist,
        "source_api": API_URL,
        "premium_last_digit": last_digit,
        "premium_matches_number": matches_rule,
        "size": derived["size"],
        "primary_color": derived["primary_color"],
        "has_violet": derived["has_violet"],
        "parity": derived["parity"],
        "issue_date": meta["issue_date"],
        "game_code": meta["game_code"],
        "daily_round_num": meta["daily_round_num"],
        "gap_from_prev": "",
        "is_consecutive": 1,
    }

# ==============================================================================
# Storage Manager (SQLite + CSV + JSONL + State + Summary)
# ==============================================================================

class StorageManager:
    def __init__(self, output_dir: Path, logger: logging.Logger):
        self.output_dir = output_dir
        self.logger = logger
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.output_dir / "wingo_30s_history.sqlite"
        self.csv_path = self.output_dir / "wingo_30s_history.csv"
        self.jsonl_path = self.output_dir / "raw_api_responses.jsonl"
        self.state_path = self.output_dir / "collector_state.json"
        self.summary_path = self.output_dir / "collection_summary.json"
        self.stop_path = self.output_dir / "collector.stop"

        self._init_sqlite()
        self._ensure_legacy_ingested()

    def _ensure_legacy_ingested(self):
        """Ensures all pre-existing historical records from earlier collectors are preserved in SQLite."""
        backup_csv = self.output_dir / "wingo_30s_history_backup_pre_platsaas.csv"
        csv_to_check = backup_csv if backup_csv.exists() else self.csv_path
        if csv_to_check.exists() and csv_to_check.stat().st_size > 0:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT count(*) FROM rounds")
                existing_cnt = cursor.fetchone()[0]

            if existing_cnt < 1000:  # Fresh or minimal DB, import full legacy archive
                self.logger.info(f"Preserving existing historical records from '{csv_to_check.name}' into SQLite...")
                now_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
                imported = []
                with open(csv_to_check, "r", encoding="utf-8", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        pid = str(row.get("issueNumber", "")).strip()
                        if not pid or not pid.isdigit():
                            continue
                        norm = normalize_record(row, fetched_utc=now_utc, fetched_ist=now_ist)
                        imported.append(norm)

                if imported:
                    self.save_records_batch(imported, is_import=True)
                    self.logger.info(f"Successfully preserved {len(imported)} legacy rounds in SQLite database.")

    def _init_sqlite(self):
        """Create database tables with primary keys and indexes."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rounds (
                    issueNumber TEXT NOT NULL,
                    typeID INTEGER NOT NULL,
                    premium TEXT NOT NULL,
                    number TEXT NOT NULL,
                    colour TEXT NOT NULL,
                    startTime TEXT,
                    endTime TEXT,
                    state INTEGER NOT NULL,
                    intervalM REAL,
                    expireSeconds INTEGER,
                    fetched_at_utc TEXT,
                    fetched_at_ist TEXT,
                    source_api TEXT,
                    premium_last_digit TEXT,
                    premium_matches_number INTEGER,
                    color TEXT,
                    size TEXT,
                    primary_color TEXT,
                    has_violet INTEGER,
                    parity TEXT,
                    issue_date TEXT,
                    game_code TEXT,
                    daily_round_num INTEGER,
                    gap_from_prev TEXT,
                    is_consecutive INTEGER,
                    PRIMARY KEY (issueNumber, typeID)
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_issue_date ON rounds(issue_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_start_time ON rounds(startTime);")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_rounds (
                    issueNumber TEXT NOT NULL,
                    typeID INTEGER NOT NULL,
                    raw_json TEXT NOT NULL,
                    fetched_at_utc TEXT,
                    PRIMARY KEY (issueNumber, typeID)
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    action TEXT NOT NULL,
                    issueNumber TEXT NOT NULL,
                    detail TEXT
                );
            """)
            conn.commit()

    def load_existing_memory(self) -> Dict[str, dict]:
        """
        Loads all completed rounds from SQLite into memory for fast deduplication.
        If SQLite is empty but existing CSV exists, imports CSV into SQLite first.
        """
        records = {}
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rounds WHERE state = 1 ORDER BY issueNumber ASC")
            rows = cursor.fetchall()
            for r in rows:
                records[r["issueNumber"]] = dict(r)

        if not records and self.csv_path.exists() and self.csv_path.stat().st_size > 0:
            self.logger.info(f"Importing legacy records from existing CSV: {self.csv_path}")
            records = self._import_legacy_csv()

        return records

    def _import_legacy_csv(self) -> Dict[str, dict]:
        """Ingests legacy CSV records into the new SQLite database without loss."""
        imported = {}
        now_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

        with open(self.csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = str(row.get("issueNumber", "")).strip()
                if not pid or not pid.isdigit():
                    continue
                norm = normalize_record(row, fetched_utc=now_utc, fetched_ist=now_ist)
                imported[pid] = norm

        if imported:
            self.save_records_batch(list(imported.values()), is_import=True)
            self.logger.info(f"Successfully migrated {len(imported)} existing rows into SQLite.")
        return imported

    def save_records_batch(self, batch: List[dict], is_import: bool = False) -> Tuple[int, int]:
        """
        Saves a batch of records into SQLite, handles updates of previously pending or 1-digit records,
        and appends raw audit log. Returns (new_count, updated_count).
        """
        if not batch:
            return 0, 0

        new_count = 0
        updated_count = 0
        now_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for rec in batch:
                pid = rec["issueNumber"]
                tid = rec["typeID"]
                state = rec["state"]

                if state == 0:
                    cursor.execute("""
                        INSERT OR REPLACE INTO pending_rounds (issueNumber, typeID, raw_json, fetched_at_utc)
                        VALUES (?, ?, ?, ?)
                    """, (pid, tid, json.dumps(rec), now_utc))
                    continue

                # Check if already present
                cursor.execute("SELECT premium, state FROM rounds WHERE issueNumber = ? AND typeID = ?", (pid, tid))
                existing = cursor.fetchone()

                if existing is None:
                    # Insert new completed record
                    cursor.execute("""
                        INSERT INTO rounds (
                            issueNumber, typeID, premium, number, colour, startTime, endTime,
                            state, intervalM, expireSeconds, fetched_at_utc, fetched_at_ist,
                            source_api, premium_last_digit, premium_matches_number, color, size,
                            primary_color, has_violet, parity, issue_date, game_code,
                            daily_round_num, gap_from_prev, is_consecutive
                        ) VALUES (
                            :issueNumber, :typeID, :premium, :number, :colour, :startTime, :endTime,
                            :state, :intervalM, :expireSeconds, :fetched_at_utc, :fetched_at_ist,
                            :source_api, :premium_last_digit, :premium_matches_number, :color, :size,
                            :primary_color, :has_violet, :parity, :issue_date, :game_code,
                            :daily_round_num, :gap_from_prev, :is_consecutive
                        )
                    """, rec)
                    new_count += 1
                else:
                    old_prem, old_state = existing
                    # If older record only had single digit premium or was pending, upgrade it!
                    if (len(str(old_prem)) < 5 and len(str(rec["premium"])) == 5) or old_state == 0:
                        cursor.execute("""
                            UPDATE rounds SET
                                premium = :premium, number = :number, colour = :colour,
                                startTime = :startTime, endTime = :endTime, state = :state,
                                intervalM = :intervalM, expireSeconds = :expireSeconds,
                                fetched_at_utc = :fetched_at_utc, fetched_at_ist = :fetched_at_ist,
                                source_api = :source_api, premium_last_digit = :premium_last_digit,
                                premium_matches_number = :premium_matches_number, color = :color,
                                size = :size, primary_color = :primary_color, has_violet = :has_violet,
                                parity = :parity, issue_date = :issue_date, game_code = :game_code,
                                daily_round_num = :daily_round_num
                            WHERE issueNumber = :issueNumber AND typeID = :typeID
                        """, rec)
                        cursor.execute("""
                            INSERT INTO audit_log (timestamp_utc, action, issueNumber, detail)
                            VALUES (?, 'UPGRADE_5DIGIT_PREMIUM', ?, ?)
                        """, (now_utc, pid, f"Upgraded premium from '{old_prem}' to '{rec['premium']}'"))
                        updated_count += 1

                # If pending existed, remove from pending
                cursor.execute("DELETE FROM pending_rounds WHERE issueNumber = ? AND typeID = ?", (pid, tid))

            conn.commit()

        return new_count, updated_count

    def append_raw_jsonl(self, raw_items: List[dict]):
        """Append raw API objects to JSONL audit file."""
        if not raw_items:
            return
        now_iso = datetime.now(UTC).isoformat()
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            for item in raw_items:
                f.write(json.dumps({"logged_at_utc": now_iso, "record": item}, ensure_ascii=False) + "\n")

    def export_full_csv(self) -> int:
        """
        Reads all completed rounds from SQLite, computes gap/continuity metadata,
        and atomically writes wingo_30s_history.csv sorted chronologically.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rounds WHERE state = 1 ORDER BY issueNumber ASC")
            rows = [dict(r) for r in cursor.fetchall()]

        if not rows:
            return 0

        # Compute gaps and continuity across entire sequence
        prev_pid = ""
        for i, row in enumerate(rows):
            curr_pid = row["issueNumber"]
            if not prev_pid:
                row["gap_from_prev"] = "0"
                row["is_consecutive"] = 1
            else:
                if len(prev_pid) == 17 and len(curr_pid) == 17 and prev_pid[:13] == curr_pid[:13]:
                    diff = int(curr_pid[13:]) - int(prev_pid[13:])
                    gap = max(0, diff - 1)
                    row["gap_from_prev"] = str(gap)
                    row["is_consecutive"] = 1 if diff == 1 else 0
                else:
                    prev_serial = int(prev_pid[13:]) if len(prev_pid) == 17 else -1
                    curr_serial = int(curr_pid[13:]) if len(curr_pid) == 17 else -1
                    if prev_serial == 2880 and curr_serial == 1:
                        row["gap_from_prev"] = "0"
                        row["is_consecutive"] = 1
                    else:
                        row["gap_from_prev"] = "day_change"
                        row["is_consecutive"] = 0
            prev_pid = curr_pid

        # Atomic write to CSV
        tmp_csv = self.csv_path.with_suffix(".tmp")
        with open(tmp_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for r in rows:
                writer.writerow({col: r.get(col, "") for col in CSV_COLUMNS})
            f.flush()
            os.fsync(f.fileno())

        tmp_csv.replace(self.csv_path)
        return len(rows)

    def load_state(self) -> dict:
        if self.state_path.exists():
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "earliest_date_available": "2026-10-12",
            "completed_dates": [],
            "in_progress": None,
            "last_updated_utc": "",
        }

    def save_state(self, state: dict):
        state["last_updated_utc"] = datetime.now(UTC).isoformat()
        tmp_state = self.state_path.with_suffix(".tmp")
        with open(tmp_state, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.flush()
        tmp_state.replace(self.state_path)

    def generate_and_save_summary(self) -> dict:
        """Computes comprehensive collection statistics and writes collection_summary.json."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rounds WHERE state = 1 ORDER BY issueNumber ASC")
            rows = cursor.fetchall()

        total = len(rows)
        if total == 0:
            summary = {
                "total_completed_records": 0,
                "status": "No completed records in database.",
                "updated_at_utc": datetime.now(UTC).isoformat(),
            }
            with open(self.summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
            return summary

        first_pid = rows[0]["issueNumber"]
        last_pid = rows[-1]["issueNumber"]
        first_date = rows[0]["issue_date"]
        last_date = rows[-1]["issue_date"]

        # Premium validation counts
        prem_5digit = sum(1 for r in rows if len(str(r["premium"])) == 5 and str(r["premium"]).isdigit())
        matches = sum(1 for r in rows if r["premium_matches_number"] == 1)
        mismatches = sum(1 for r in rows if r["premium_matches_number"] == 0)
        invalid_prems = sum(1 for r in rows if r["premium_matches_number"] == -1)

        # Digit frequencies
        num_counts = Counter(str(r["number"]) for r in rows)
        size_counts = Counter(str(r["size"]) for r in rows)
        color_counts = Counter(str(r["colour"]) for r in rows)

        # Continuity & gaps
        consecutive_pairs = sum(1 for r in rows[1:] if r["is_consecutive"] == 1)
        breaks = max(0, (total - 1) - consecutive_pairs)

        summary = {
            "total_completed_records": total,
            "oldest_period_id": first_pid,
            "newest_period_id": last_pid,
            "oldest_date": first_date,
            "newest_date": last_date,
            "premium_metrics": {
                "five_digit_premiums": prem_5digit,
                "legacy_or_short_premiums": total - prem_5digit,
                "validation_matches (int(prem)%10 == num)": matches,
                "validation_mismatches": mismatches,
                "invalid_or_unvalidated": invalid_prems,
                "validation_accuracy_pct": round(matches / prem_5digit * 100, 2) if prem_5digit > 0 else 0.0,
            },
            "distributions": {
                "numbers": {str(i): num_counts.get(str(i), 0) for i in range(10)},
                "size": dict(size_counts),
                "colour": dict(color_counts),
            },
            "continuity": {
                "consecutive_steps": consecutive_pairs,
                "breaks_or_gaps": breaks,
            },
            "files": {
                "csv": str(self.csv_path),
                "sqlite": str(self.db_path),
                "jsonl": str(self.jsonl_path),
                "state": str(self.state_path),
            },
            "updated_at_utc": datetime.now(UTC).isoformat(),
            "updated_at_ist": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
        }

        with open(self.summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        return summary

# ==============================================================================
# API Client (HTTP POST with Retry & Exponential Backoff)
# ==============================================================================

class PlatsaasAPIClient:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "WinGoResearchCollector/1.0",
        })

    def fetch_page(
        self, target_date: str, page_index: int = 1, page_size: int = 100, max_retries: int = 5
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Sends POST request to Platsaas API with exponential backoff on errors.
        Returns: (success, error_msg, response_dict)
        """
        payload = {
            "PageSize": page_size,
            "PageIndex": page_index,
            "TypeId": TYPE_ID,
            "Time": target_date,
        }

        delay = 2.0
        for attempt in range(1, max_retries + 1):
            try:
                resp = self.session.post(API_URL, json=payload, timeout=20)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        return True, "", data
                    except ValueError:
                        return False, "Failed to parse JSON response", None
                elif resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 30))
                    self.logger.warning(f"Rate limited (HTTP 429). Backing off for {retry_after}s...")
                    time.sleep(retry_after)
                else:
                    self.logger.warning(
                        f"HTTP {resp.status_code} on {target_date} p.{page_index} (attempt {attempt}/{max_retries})"
                    )
            except requests.exceptions.RequestException as e:
                self.logger.warning(
                    f"Network error on {target_date} p.{page_index}: {e} (attempt {attempt}/{max_retries})"
                )

            if attempt < max_retries:
                time.sleep(delay)
                delay = min(delay * 2.0, 60.0)

        return False, f"Failed after {max_retries} attempts", None

# ==============================================================================
# Terminal Display Functions
# ==============================================================================

def print_terminal_table(records: List[dict], max_display: int = 15):
    """Prints a clean, formatted status table of the most recent rounds."""
    if not records:
        print("\nNo records to display.")
        return

    display_subset = records[-max_display:]
    print("\n" + "=" * 80)
    print(f"WINGO 30S OUTCOME MONITOR (Showing latest {len(display_subset)} records)")
    print("-" * 80)
    print(f"{'Issue Number':<20} {'Premium':<10} {'Number':<8} {'Colour':<14} {'Status':<16}")
    print("-" * 80)

    for r in display_subset:
        pid = str(r.get("issueNumber", ""))
        prem = str(r.get("premium", ""))
        num = str(r.get("number", ""))
        col = str(r.get("colour") or r.get("color", ""))
        state = r.get("state", 1)

        if state == 0:
            status_str = "Pending"
        else:
            match = r.get("premium_matches_number")
            if match == 1:
                status_str = "Complete (Valid)"
            elif match == 0:
                status_str = "Complete (MISMATCH)"
            else:
                status_str = "Complete"

        print(f"{pid:<20} {prem:<10} {num:<8} {col:<14} {status_str:<16}")

    print("=" * 80)


def print_session_stats(summary: dict, session_added: int = 0):
    """Displays running statistics and storage paths."""
    print("\n" + "-" * 40 + " COLLECTION STATS " + "-" * 40)
    print(f"Total Unique Completed Records: {summary.get('total_completed_records', 0)}")
    print(f"Period ID Coverage            : {summary.get('oldest_period_id', 'N/A')}  -->  {summary.get('newest_period_id', 'N/A')}")
    print(f"Date Range                    : {summary.get('oldest_date', 'N/A')}  -->  {summary.get('newest_date', 'N/A')}")
    print(f"Records Added in Session      : {session_added}")

    pm = summary.get("premium_metrics", {})
    print(f"5-Digit Premium Records       : {pm.get('five_digit_premiums', 0)}")
    print(f"Validation Matches (prem%10)  : {pm.get('validation_matches (int(prem)%10 == num)', 0)}")
    print(f"Validation Mismatches         : {pm.get('validation_mismatches', 0)}")

    dist = summary.get("distributions", {})
    nums = dist.get("numbers", {})
    freq_str = "  ".join(f"{k}:{v}" for k, v in sorted(nums.items(), key=lambda x: int(x[0])))
    print(f"Digit Frequencies (0-9)       : {freq_str}")

    files = summary.get("files", {})
    print(f"CSV Save Location             : {files.get('csv', '')}")
    print(f"SQLite Save Location          : {files.get('sqlite', '')}")
    print("-" * 98 + "\n")

# ==============================================================================
# Historical Backfill Engine
# ==============================================================================

def run_historical_backfill(
    storage: StorageManager,
    client: PlatsaasAPIClient,
    start_date_str: str,
    end_date_str: str,
    page_size: int = 100,
    max_pages_per_date: Optional[int] = None,
    delay_between_pages: float = 0.3,
):
    """Executes resilient historical backfilling with resume capability."""
    logger = storage.logger
    state = storage.load_state()

    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date()

    if start_dt > end_dt:
        logger.error(f"Start date {start_date_str} is after end date {end_date_str}!")
        return

    logger.info(f"Starting Historical Backfill from {start_date_str} to {end_date_str} (PageSize={page_size})")

    current_dt = start_dt
    session_added = 0
    recent_records = []

    try:
        while current_dt <= end_dt:
            if storage.stop_path.exists():
                logger.info("Stop requested via collector.stop. Halting backfill cleanly.")
                break

            date_str = current_dt.strftime("%Y-%m-%d")

            # Check if this date was already fully completed
            if date_str in state.get("completed_dates", []):
                logger.info(f"Date {date_str} already completed. Skipping.")
                current_dt += timedelta(days=1)
                continue

            # Determine starting pageIndex (if resuming an in-progress date)
            start_page = 1
            if state.get("in_progress") and state["in_progress"].get("date") == date_str:
                start_page = state["in_progress"].get("next_page", 1)
                logger.info(f"Resuming {date_str} from page {start_page}...")

            # Fetch page 1 (or start_page) to determine totalPage
            ok, err, data = client.fetch_page(date_str, page_index=start_page, page_size=page_size)
            if not ok or not data:
                logger.warning(f"No records or error for {date_str} (page {start_page}): {err}")
                current_dt += timedelta(days=1)
                continue

            total_pages = int(data.get("totalPage") or 1)
            total_count = int(data.get("totalCount") or 0)
            items = data.get("data") or []

            if not items:
                logger.info(f"Date {date_str} has 0 records available. Marking complete.")
                state.setdefault("completed_dates", []).append(date_str)
                storage.save_state(state)
                current_dt += timedelta(days=1)
                continue

            logger.info(f"Date {date_str}: {total_count} total rounds reported across {total_pages} pages.")

            # Process start_page
            norm_records = [normalize_record(it) for it in items if isinstance(it, dict)]
            new_cnt, up_cnt = storage.save_records_batch(norm_records)
            storage.append_raw_jsonl(items)
            session_added += new_cnt
            recent_records.extend(norm_records)

            page = start_page + 1
            limit_pages = total_pages
            if max_pages_per_date:
                limit_pages = min(total_pages, start_page + max_pages_per_date - 1)

            while page <= limit_pages:
                if storage.stop_path.exists():
                    logger.info("Stop requested via collector.stop. Saving checkpoint and exiting.")
                    state["in_progress"] = {"date": date_str, "next_page": page}
                    storage.save_state(state)
                    storage.export_full_csv()
                    return

                time.sleep(delay_between_pages)
                p_ok, p_err, p_data = client.fetch_page(date_str, page_index=page, page_size=page_size)
                if not p_ok or not p_data:
                    logger.warning(f"Error fetching {date_str} page {page}: {p_err}. Retrying...")
                    time.sleep(2.0)
                    continue

                p_items = p_data.get("data") or []
                if not p_items:
                    break

                p_norm = [normalize_record(it) for it in p_items if isinstance(it, dict)]
                n_cnt, u_cnt = storage.save_records_batch(p_norm)
                storage.append_raw_jsonl(p_items)
                session_added += n_cnt
                recent_records.extend(p_norm)

                logger.info(f"  [{date_str}] Page {page}/{total_pages} processed (+{n_cnt} new, {u_cnt} upgraded)")

                # Periodic checkpoint state
                state["in_progress"] = {"date": date_str, "next_page": page + 1}
                storage.save_state(state)
                page += 1

            # Completed entire date
            if limit_pages >= total_pages:
                if date_str not in state.setdefault("completed_dates", []):
                    state["completed_dates"].append(date_str)
                state["in_progress"] = None
                storage.save_state(state)
                logger.info(f"Date {date_str} backfill complete!")

            # Export CSV and update summary after each date
            storage.export_full_csv()
            summary = storage.generate_and_save_summary()

            print_terminal_table(recent_records[-15:])
            print_session_stats(summary, session_added=session_added)

            current_dt += timedelta(days=1)

    except KeyboardInterrupt:
        logger.info("\nBackfill interrupted by user (Ctrl+C). Saving all records...")
    finally:
        storage.export_full_csv()
        summary = storage.generate_and_save_summary()
        logger.info(f"Backfill ended. Total completed rounds in database: {summary.get('total_completed_records', 0)}")

# ==============================================================================
# Live Continuous Collector Engine
# ==============================================================================

def run_live_collector(storage: StorageManager, client: PlatsaasAPIClient, poll_interval: int = 30):
    """Continuously polls the Platsaas API for newly published results."""
    logger = storage.logger
    logger.info(f"=== Starting WinGo 30S Live Continuous Collector (Poll Interval: {poll_interval}s) ===")
    logger.info(f"Press Ctrl+C or touch '{storage.stop_path}' to stop cleanly.")

    session_added = 0
    cycle = 0

    try:
        while True:
            if storage.stop_path.exists():
                logger.info("Stop file detected. Exiting live collector cleanly.")
                break

            cycle += 1
            now_dt = datetime.now(IST)
            today_str = now_dt.strftime("%Y-%m-%d")

            # Fetch first page (latest 20 records)
            ok, err, data = client.fetch_page(today_str, page_index=1, page_size=20)
            if not ok or not data:
                logger.warning(f"[Cycle {cycle} @ {now_dt.strftime('%H:%M:%S')}] Poll failed ({err}). Retrying in {poll_interval}s...")
                time.sleep(poll_interval)
                continue

            items = data.get("data") or []
            if items:
                norm_records = [normalize_record(it) for it in items if isinstance(it, dict)]
                new_cnt, up_cnt = storage.save_records_batch(norm_records)
                storage.append_raw_jsonl(items)

                if new_cnt > 0 or up_cnt > 0:
                    session_added += new_cnt
                    storage.export_full_csv()
                    summary = storage.generate_and_save_summary()

                    # Sort oldest to newest for display
                    display_recs = sorted(norm_records, key=lambda x: str(x.get("issueNumber", "")))
                    print_terminal_table(display_recs)
                    print_session_stats(summary, session_added=session_added)
                elif cycle % 10 == 0:
                    logger.info(f"[Cycle {cycle} @ {now_dt.strftime('%H:%M:%S')}] Waiting for next 30s draw...")

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        logger.info("\nLive collector stopped by user (Ctrl+C).")
    finally:
        storage.export_full_csv()
        storage.generate_and_save_summary()
        logger.info("Live collector terminated cleanly. All data flushed to disk.")

# ==============================================================================
# Comprehensive Data Quality & Research Audit
# ==============================================================================

def run_dataset_audit(storage: StorageManager):
    """Runs a 10-point data quality and research readiness audit."""
    print("\n" + "=" * 80)
    print("WINGO 30S DATA QUALITY & RESEARCH READINESS AUDIT")
    print("=" * 80)

    summary = storage.generate_and_save_summary()
    total = summary.get("total_completed_records", 0)
    print(f"Total Unique Completed Records : {total}")
    if total == 0:
        print("Dataset is empty. Run backfill or live collector first.")
        return

    with sqlite3.connect(storage.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rounds WHERE state = 1 ORDER BY issueNumber ASC")
        rows = cursor.fetchall()

    # 1. Duplicates check
    pids = [r["issueNumber"] for r in rows]
    pid_counts = Counter(pids)
    duplicates = [pid for pid, cnt in pid_counts.items() if cnt > 1]
    print(f"1. Duplicate Period IDs         : {'PASS (0 duplicates)' if not duplicates else f'FAIL ({len(duplicates)} duplicates)'}")

    # 2. Chronological Ordering
    is_sorted = all(pids[i] <= pids[i+1] for i in range(len(pids)-1))
    print(f"2. Chronological Order Check    : {'PASS (Strictly sorted)' if is_sorted else 'FAIL (Unsorted records found)'}")

    # 3. Premium String Format (5-digit preservation)
    prem_lengths = Counter(len(str(r["premium"])) for r in rows)
    prem_5d = prem_lengths.get(5, 0)
    print(f"3. 5-Digit Premium Preservation : {prem_5d}/{total} ({prem_5d/total*100:.2f}%)")

    # 4. Winning Number Integrity (0-9)
    invalid_nums = [r["number"] for r in rows if str(r["number"]) not in {str(i) for i in range(10)}]
    print(f"4. Winning Number Validity (0-9): {'PASS (100% valid)' if not invalid_nums else f'FAIL ({len(invalid_nums)} invalid)'}")

    # 5. Conversion Rule Verification: int(premium) % 10 == int(number)
    matches = summary.get("premium_metrics", {}).get("validation_matches (int(prem)%10 == num)", 0)
    mismatches = summary.get("premium_metrics", {}).get("validation_mismatches", 0)
    print(f"5. Premium Rule (prem%10 == num): {matches} Matches, {mismatches} Mismatches")

    # 6. Timeline Continuity & Missing Periods
    consec = summary.get("continuity", {}).get("consecutive_steps", 0)
    breaks = summary.get("continuity", {}).get("breaks_or_gaps", 0)
    print(f"6. Sequence Continuity          : {consec} Consecutive Transitions, {breaks} Gaps/Breaks")

    # 7. Distribution Uniformity (Chi-Square)
    num_counts = summary.get("distributions", {}).get("numbers", {})
    expected = total / 10.0
    chi2 = sum(((num_counts.get(str(i), 0) - expected) ** 2) / expected for i in range(10))
    print(f"7. Digit Chi-Square Uniformity  : Chi2 = {chi2:.4f} (df=9, baseline ~16.92 at p=0.05)")

    print("=" * 80 + "\n")

# ==============================================================================
# Built-in Test Suite
# ==============================================================================

def run_tests():
    """Validates normalization, 5-digit premium preservation, and conversion rules."""
    print("\n=== Running WinGo Platsaas Collector Self-Tests ===")

    sample_api_response = {
        "totalPage": 23,
        "totalCount": 2249,
        "data": [
            {
                "issueNumber": "20261110100051588",
                "premium": "72924",
                "number": "4",
                "colour": "red",
                "typeID": 30,
                "startTime": "2026-11-10T18:43:30",
                "endTime": "2026-11-10T18:44:00",
                "state": 1,
                "intervalM": 0.5,
                "expireSeconds": 0
            }
        ]
    }

    raw_item = sample_api_response["data"][0]
    norm = normalize_record(raw_item)

    # Test 1: Full 5-digit premium preservation
    assert norm["premium"] == "72924", f"Expected '72924', got '{norm['premium']}'"
    print("Test 1: 5-Digit Premium Preserved as String -> PASSED")

    # Test 2: Full 17-digit issueNumber preserved as string
    assert norm["issueNumber"] == "20261110100051588", f"Expected '20261110100051588', got '{norm['issueNumber']}'"
    print("Test 2: IssueNumber Preserved as String -> PASSED")

    # Test 3: Conversion rule int(premium) % 10 == int(number)
    assert norm["premium_matches_number"] == 1, f"Expected match 1, got {norm['premium_matches_number']}"
    assert norm["premium_last_digit"] == "4", f"Expected '4', got '{norm['premium_last_digit']}'"
    print("Test 3: Conversion Rule (72924 % 10 == 4) -> PASSED")

    # Test 4: Mismatch detection
    mismatch_item = raw_item.copy()
    mismatch_item["premium"] = "72925"  # ends in 5, number is 4
    m_norm = normalize_record(mismatch_item)
    assert m_norm["premium_matches_number"] == 0, "Mismatch should be flagged as 0"
    print("Test 4: Premium Mismatch Flagging -> PASSED")

    # Test 5: Leading zero preservation
    zero_item = raw_item.copy()
    zero_item["premium"] = "00123"
    zero_item["number"] = "3"
    z_norm = normalize_record(zero_item)
    assert z_norm["premium"] == "00123", f"Expected '00123', got '{z_norm['premium']}'"
    assert z_norm["premium_matches_number"] == 1
    print("Test 5: Leading Zero Preservation ('00123') -> PASSED")

    # Test 6: Pending state detection
    pending_item = raw_item.copy()
    pending_item["state"] = 0
    pending_item["premium"] = ""
    pending_item["number"] = ""
    p_norm = normalize_record(pending_item)
    assert p_norm["state"] == 0
    assert p_norm["premium_matches_number"] == -1
    print("Test 6: Pending Round Handling -> PASSED")

    print("\nALL 6 TESTS PASSED SUCCESSFULLY!\n")

# ==============================================================================
# Main Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="WinGo 30S Platsaas Historical & Live Data Collector")
    parser.add_argument("--mode", choices=["backfill", "live", "audit", "test"], default="audit", help="Collector operational mode")
    parser.add_argument("--start-date", type=str, default="2026-10-12", help="Backfill starting date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default="2026-11-11", help="Backfill ending date (YYYY-MM-DD)")
    parser.add_argument("--page-size", type=int, default=100, help="API page size (10 to 1000, default: 100)")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit number of pages per date (for quick testing)")
    parser.add_argument("--poll-interval", type=int, default=30, help="Live polling interval in seconds (default: 30)")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR), help="Output directory path")
    parser.add_argument("--test", action="store_true", help="Run self-tests and exit")

    args = parser.parse_args()

    if args.test or args.mode == "test":
        run_tests()
        return

    output_dir = Path(args.output_dir)
    logger = setup_logger(output_dir)
    lock_file = output_dir / "collector.lock"

    # Acquire process lock
    try:
        with ProcessLock(lock_file):
            # Clean up stop file if left over from a previous session
            stop_file = output_dir / "collector.stop"
            if stop_file.exists():
                stop_file.unlink(missing_ok=True)

            storage = StorageManager(output_dir, logger)
            client = PlatsaasAPIClient(logger)

            if args.mode == "backfill":
                run_historical_backfill(
                    storage=storage,
                    client=client,
                    start_date_str=args.start_date,
                    end_date_str=args.end_date,
                    page_size=args.page_size,
                    max_pages_per_date=args.max_pages,
                )
            elif args.mode == "live":
                run_live_collector(
                    storage=storage,
                    client=client,
                    poll_interval=args.poll_interval,
                )
            elif args.mode == "audit":
                run_dataset_audit(storage)

    except RuntimeError as e:
        logger.error(f"[LOCK ERROR] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
