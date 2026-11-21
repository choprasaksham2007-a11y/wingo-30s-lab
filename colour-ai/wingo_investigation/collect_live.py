import csv
import json
import shutil
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests
from collector_runtime import collector_session

API_URL = "https://lotteryresultapi.platsaas.com/api/GetWinResult"

# SAVING DIRECTLY IN VS CODE WORKSPACE: Look for the 'collected_data' folder on your left sidebar!
# Data is saved in a folder called collected_data, next to this script (same place as before)
OUTPUT_DIR = Path(__file__).resolve().parent / "collected_data"

POLL_INTERVAL_SECONDS = 15
BACKOFF_SECONDS = 300          # if the site says 'too many requests', wait this long
HISTORY_DISPLAY_ROWS = 15
STOP_FILE = OUTPUT_DIR / 'collector.stop'

# Indian Standard Time (IST) is UTC + 5 hours 30 minutes
IST_OFFSET = timezone(timedelta(hours=5, minutes=30))

VALID_NUMBERS = {str(i) for i in range(10)}
REQUIRED_FIELDS = ("issueNumber", "number", "color", "premium", "sum")

CSV_COLUMNS = [
    "issueNumber",
    "issue_date",
    "game_code",
    "daily_round_num",
    "number",
    "size",
    "color",
    "primary_color",
    "has_violet",
    "parity",
    "premium",
    "sum",
    "gap_from_prev",
    "is_consecutive",
    "api_serviceTime",
    "fetched_at_ist",
    "source_mode",
]


def parse_issue_metadata(issue_number: str) -> dict:
    if len(issue_number) == 17 and issue_number.isdigit():
        raw_date = issue_number[:8]
        formatted_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        game_code = issue_number[8:13]
        daily_round_num = int(issue_number[13:])
        return {
            "issue_date": formatted_date,
            "game_code": game_code,
            "daily_round_num": daily_round_num,
        }
    return {"issue_date": "", "game_code": "", "daily_round_num": -1}


def derive_outcome_fields(number_str: str, color_str: str) -> dict:
    num_int = int(number_str)
    size = "Big" if num_int >= 5 else "Small"
    parity = "even" if num_int % 2 == 0 else "odd"
    color_lower = color_str.lower()
    primary_color = "red" if "red" in color_lower else ("green" if "green" in color_lower else color_lower)
    has_violet = 1 if "violet" in color_lower else 0
    return {
        "size": size,
        "primary_color": primary_color,
        "has_violet": has_violet,
        "parity": parity,
    }


def compute_gap(prev_issue: str, curr_issue: str) -> tuple:
    if not prev_issue:
        return "", 1
    if prev_issue.isdigit() and curr_issue.isdigit():
        if prev_issue[:13] == curr_issue[:13]:
            diff = int(curr_issue[13:]) - int(prev_issue[13:])
            gap = max(0, diff - 1)
            return str(gap), (1 if diff == 1 else 0)
        else:
            prev_serial = int(prev_issue[13:])
            curr_serial = int(curr_issue[13:])
            if prev_serial == 2880 and curr_serial == 1:
                return "0", 1
            return "day_change", 0
    return "", 0


def enrich_and_sort_records(raw_records_by_id: dict) -> list:
    sorted_ids = sorted(raw_records_by_id.keys())
    enriched_list = []
    prev_id = ""

    for issue_id in sorted_ids:
        rec = raw_records_by_id[issue_id]
        issue_meta = parse_issue_metadata(issue_id)
        outcome_meta = derive_outcome_fields(rec["number"], rec["color"])
        gap_str, is_consec = compute_gap(prev_id, issue_id)

        full_row = {
            "issueNumber": issue_id,
            "issue_date": issue_meta["issue_date"],
            "game_code": issue_meta["game_code"],
            "daily_round_num": issue_meta["daily_round_num"],
            "number": rec["number"],
            "size": outcome_meta["size"],
            "color": rec["color"],
            "primary_color": outcome_meta["primary_color"],
            "has_violet": outcome_meta["has_violet"],
            "parity": outcome_meta["parity"],
            "premium": rec["premium"],
            "sum": rec["sum"],
            "gap_from_prev": gap_str,
            "is_consecutive": is_consec,
            "api_serviceTime": rec.get("api_serviceTime", ""),
            "fetched_at_ist": rec.get("fetched_at_ist", ""),
            "source_mode": rec.get("source_mode", "fresh_start"),
        }
        enriched_list.append(full_row)
        prev_id = issue_id

    return enriched_list


def write_full_enriched_csv(csv_path: Path, enriched_rows: list):
    temp_path = csv_path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(enriched_rows)
        f.flush()
    temp_path.replace(csv_path)


def update_antigravity_handoff(handoff_path: Path, csv_path: Path, enriched_rows: list):
    total = len(enriched_rows)
    num_counts = Counter(r["number"] for r in enriched_rows)
    size_counts = Counter(r["size"] for r in enriched_rows)
    primary_color_counts = Counter(r["primary_color"] for r in enriched_rows)
    violet_count = sum(int(r["has_violet"]) for r in enriched_rows)
    consec_transitions = sum(1 for r in enriched_rows[1:] if int(r["is_consecutive"]) == 1)
    gap_breaks = max(0, (total - 1) - consec_transitions)

    handoff_payload = {
        "project": "WinGo_30S Fresh Live Data Collection",
        "updated_at_ist": datetime.now(IST_OFFSET).isoformat(),
        "dataset_csv_path": str(csv_path),
        "total_unique_rounds": total,
        "earliest_issueNumber": enriched_rows[0]["issueNumber"] if enriched_rows else None,
        "latest_issueNumber": enriched_rows[-1]["issueNumber"] if enriched_rows else None,
        "continuity": {
            "consecutive_step_pairs": consec_transitions,
            "sequence_breaks_or_gaps": gap_breaks,
        },
        "distributions": {
            "numbers_0_to_9": {str(i): num_counts.get(str(i), 0) for i in range(10)},
            "size": dict(size_counts),
            "primary_color": dict(primary_color_counts),
            "violet_occurrences": violet_count,
        },
        "columns": CSV_COLUMNS,
        "latest_20_rounds": enriched_rows[-20:],
    }

    with handoff_path.open("w", encoding="utf-8") as f:
        json.dump(handoff_payload, f, indent=2)


def print_history_and_stats(enriched_rows: list, last_n: int = HISTORY_DISPLAY_ROWS):
    total = len(enriched_rows)
    if total == 0:
        print("No records collected yet. Waiting for first round...", flush=True)
        return

    recent = enriched_rows[-last_n:]
    print("\n" + "=" * 80, flush=True)
    print(f"FRESH HISTORY VIEW (Times in IST | Showing last {len(recent)} of {total} total rounds)", flush=True)
    print("-" * 80, flush=True)
    print(f"{'IssueNumber':<19} | {'DailyRnd':>8} | {'Num':>3} | {'Size':<5} | {'Color':<12} | {'Gap':>4} | {'Time (IST)'}", flush=True)
    print("-" * 80, flush=True)
    for r in recent:
        obs_time = r["fetched_at_ist"]
        obs_short = obs_time[11:19] if len(obs_time) >= 19 else obs_time
        gap_disp = "0" if r["gap_from_prev"] in ("", "0") else f"+{r['gap_from_prev']}"
        print(
            f"{r['issueNumber']:<19} | {str(r['daily_round_num']):>8} | {r['number']:>3} | "
            f"{r['size']:<5} | {r['color']:<12} | {gap_disp:>4} | {obs_short}",
            flush=True,
        )
    print("-" * 80, flush=True)

    big_cnt = sum(1 for r in enriched_rows if r["size"] == "Big")
    small_cnt = total - big_cnt
    red_cnt = sum(1 for r in enriched_rows if r["primary_color"] == "red")
    green_cnt = sum(1 for r in enriched_rows if r["primary_color"] == "green")
    violet_cnt = sum(int(r["has_violet"]) for r in enriched_rows)
    num_counts = Counter(r["number"] for r in enriched_rows)
    freq_str = "  ".join(f"{i}:{num_counts.get(str(i), 0)}" for i in range(10))

    print(
        f"STATS (n={total}) -> Big: {big_cnt} ({big_cnt/total*100:.1f}%) | "
        f"Small: {small_cnt} ({small_cnt/total*100:.1f}%) | "
        f"Red: {red_cnt} | Green: {green_cnt} | Violet: {violet_cnt}",
        flush=True,
    )
    print(f"NUMBER COUNTS  -> {freq_str}", flush=True)
    print("=" * 80 + "\n", flush=True)


def fetch_api_window() -> tuple:
    try:
        response = requests.get(
            API_URL,
            params={"pageNo": 1, "pageSize": 100},
            headers={"Accept": "application/json"},
            timeout=10,
        )
    except requests.exceptions.RequestException as exc:
        return False, f"Network error: {exc}", "", []

    if response.status_code != 200:
        return False, f"HTTP {response.status_code}", "", []

    try:
        payload = response.json()
    except ValueError:
        return False, "Non-JSON response", "", []

    if not isinstance(payload, dict):
        return False, "Invalid API response object", "", []
    if payload.get("code") != 0:
        return False, f"API error: {payload.get('msg')}", "", []

    data = payload.get("data")
    records = data.get("list") if isinstance(data, dict) else None
    if not isinstance(records, list) or not records:
        return False, "Empty data.list", "", []

    return True, "", str(payload.get("serviceTime", "")), records


def sync_records(known_records: dict, source_mode: str) -> tuple:
    ok, err, service_time, items = fetch_api_window()
    if not ok:
        return False, err, [], None

    fetched_at_ist = datetime.now(IST_OFFSET).isoformat()
    sorted_items = sorted(
        [x for x in items if isinstance(x, dict)],
        key=lambda x: str(x.get("issueNumber", "")),
    )

    newly_added = []
    latest_id = None

    for item in sorted_items:
        missing = [k for k in REQUIRED_FIELDS if k not in item or item[k] is None]
        if missing:
            continue

        issue_id = str(item["issueNumber"]).strip()
        num_str = str(item["number"]).strip()
        col_str = str(item["color"]).strip()
        prem_str = str(item["premium"]).strip()
        sum_str = str(item["sum"]).strip()

        if not issue_id.isdigit() or num_str not in VALID_NUMBERS or not col_str:
            continue

        latest_id = issue_id
        if issue_id not in known_records:
            known_records[issue_id] = {
                "issueNumber": issue_id,
                "number": num_str,
                "color": col_str,
                "premium": prem_str,
                "sum": sum_str,
                "api_serviceTime": service_time,
                "fetched_at_ist": fetched_at_ist,
                "source_mode": source_mode,
            }
            newly_added.append(issue_id)

    return True, "", newly_added, latest_id


def load_existing_records(csv_path: Path) -> dict:
    """Read the CSV saved earlier, so a restart never throws old rounds away."""
    known = {}
    if not csv_path.exists():
        return known
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            known[row["issueNumber"]] = {
                "issueNumber": row["issueNumber"],
                "number": row["number"],
                "color": row["color"],
                "premium": row.get("premium", ""),
                "sum": row.get("sum", ""),
                "api_serviceTime": row.get("api_serviceTime", ""),
                "fetched_at_ist": row.get("fetched_at_ist", ""),
                "source_mode": row.get("source_mode", "loaded_from_csv"),
            }
    return known


def save_all(history_csv: Path, handoff_json: Path, enriched_rows: list) -> bool:
    """Save, but never crash if the file is locked (for example open in Excel)."""
    try:
        write_full_enriched_csv(history_csv, enriched_rows)
        update_antigravity_handoff(handoff_json, history_csv, enriched_rows)
        return True
    except OSError as exc:
        print(f"[WARNING] Could not save ({exc}). Close the file if it is open. Will retry on the next poll.", flush=True)
        return False


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None or sys.stderr is None:   # started by Task Scheduler with pythonw (no console)
        sys.stdout = sys.stderr = open(OUTPUT_DIR / "collector.log", "a", encoding="utf-8", buffering=1)
    history_csv = OUTPUT_DIR / "wingo_30s_history.csv"
    handoff_json = OUTPUT_DIR / "antigravity_handoff.json"

    print("=== WinGo 30S Live Collector Started ===", flush=True)
    known_records = load_existing_records(history_csv)   # CHANGED: keep old data after a restart
    if known_records:
        backup = OUTPUT_DIR / f"backup_{datetime.now(IST_OFFSET).strftime('%Y%m%d')}.csv"
        if not backup.exists():                          # one backup per day
            shutil.copy2(history_csv, backup)
        print(f"Loaded {len(known_records)} existing rounds from the CSV.", flush=True)

    ok, err, new_ids, _ = sync_records(known_records, source_mode="start_sync")
    enriched_rows = enrich_and_sort_records(known_records)
    dirty = not save_all(history_csv, handoff_json, enriched_rows)

    if ok:
        print(f"Start sync complete: found {len(new_ids)} new rounds.", flush=True)
    else:
        print(f"Start sync failed ({err}). Will keep trying.", flush=True)

    print_history_and_stats(enriched_rows)

    print(f"--- Continuous Live Monitoring (Polling every {POLL_INTERVAL_SECONDS}s) ---", flush=True)
    print(f"Files saving inside: {OUTPUT_DIR}\n", flush=True)

    cycle = 0
    try:
        while True:
            time.sleep(POLL_INTERVAL_SECONDS)
            if STOP_FILE.exists():
                break
            cycle += 1
            try:                                          # CHANGED: one bad poll must never stop the collector
                now_str = datetime.now(IST_OFFSET).strftime("%H:%M:%S IST")
                if dirty:
                    dirty = not save_all(history_csv, handoff_json, enrich_and_sort_records(known_records))
                ok, err, new_ids, latest_id = sync_records(known_records, source_mode="live_continuous")

                if not ok:
                    print(f"[Poll #{cycle} @ {now_str}] Retry needed ({err})", flush=True)
                    if "429" in err or "403" in err:      # the site asks us to slow down
                        print(f"Backing off for {BACKOFF_SECONDS} seconds.", flush=True)
                        time.sleep(BACKOFF_SECONDS)
                    continue

                if new_ids:
                    dirty = True
                    enriched_rows = enrich_and_sort_records(known_records)
                    dirty = not save_all(history_csv, handoff_json, enriched_rows)

                    for nid in new_ids:
                        r = next(row for row in enriched_rows if row["issueNumber"] == nid)
                        print(
                            f"[NEW ROUND @ {now_str}] Issue={r['issueNumber']} (DailyRnd#{r['daily_round_num']}) | "
                            f"Num={r['number']} ({r['size']}) | Color={r['color']} | "
                            f"Gap={r['gap_from_prev'] or '0'} | Total={len(enriched_rows)}",
                            flush=True,
                        )
                    if len(enriched_rows) % 10 == 0:
                        print_history_and_stats(enriched_rows)
                elif cycle % 20 == 0:                     # CHANGED: print the waiting line less often
                    print(
                        f"[Poll #{cycle} @ {now_str}] Waiting for round to finish "
                        f"(latest={latest_id}, total={len(enriched_rows)})",
                        flush=True,
                    )
            except Exception:
                print("[ERROR] Unexpected problem, the collector keeps running:", flush=True)
                traceback.print_exc()
    except KeyboardInterrupt:
        pass
    saved = save_all(history_csv, handoff_json, enrich_and_sort_records(known_records))
    print(f"\n[STOPPED] {len(known_records)} rounds in memory; final save {'succeeded' if saved else 'FAILED'}.", flush=True)


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with collector_session(OUTPUT_DIR / 'collector.lock'):
            STOP_FILE.unlink(missing_ok=True)
            while not STOP_FILE.exists():
                try:
                    main()
                    break
                except Exception:
                    traceback.print_exc()
                    print('Collector restarting in 15 seconds after an unexpected exit.', flush=True)
                    time.sleep(15)
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        print(exc, flush=True)
        sys.exit(2)
