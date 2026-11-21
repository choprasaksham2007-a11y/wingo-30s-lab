"""WinGo 30S: collect the *full five-digit premium* from the Platsaas results API.

This script updates the same collected_data/wingo_30s_history.csv used by the
older collector. Previously saved rounds are preserved. When Platsaas supplies a
full five-digit premium for an existing round, the script upgrades that field.

Run:
    pip install requests
    python wingo_premium_collector.py --once
    python wingo_premium_collector.py
    python wingo_premium_collector.py --backfill-days 5 --once

Stop continuous collection with Ctrl+C or by creating
collected_data/collector.stop. Do not run the old collector simultaneously.
"""

import argparse
import csv
import json
import shutil
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

API_URL = "https://lotteryresultapi.platsaas.com/api/GetWinResult"
TYPE_ID = 30                         # WinGo 30 seconds
PAGE_SIZE = 101                      # matches the webpage's request
POLL_INTERVAL_SECONDS = 15           # matches your existing script
BACKOFF_SECONDS = 300
IST = timezone(timedelta(hours=5, minutes=30))
OUTPUT_DIR = Path(__file__).resolve().parent / "collected_data"
CSV_PATH = OUTPUT_DIR / "wingo_30s_history.csv"
HANDOFF_PATH = OUTPUT_DIR / "antigravity_handoff.json"
STOP_FILE = OUTPUT_DIR / "collector.stop"

# Original columns are retained; new columns are appended for traceability.
CSV_COLUMNS = [
    "issueNumber", "issue_date", "game_code", "daily_round_num",
    "number", "size", "color", "primary_color", "has_violet", "parity",
    "premium", "sum", "gap_from_prev", "is_consecutive",
    "api_serviceTime", "fetched_at_ist", "source_mode",
    "startTime", "endTime", "premium_source", "premium_fetched_at_ist",
]


def parse_issue_metadata(issue: str) -> dict:
    if len(issue) == 17 and issue.isdigit():
        d = issue[:8]
        return {
            "issue_date": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
            "game_code": issue[8:13],
            "daily_round_num": int(issue[13:]),
        }
    return {"issue_date": "", "game_code": "", "daily_round_num": -1}


def derive_fields(number: str, color: str) -> dict:
    n = int(number)
    c = color.lower()
    primary = "red" if "red" in c else "green" if "green" in c else c
    return {
        "size": "Big" if n >= 5 else "Small",
        "primary_color": primary,
        "has_violet": 1 if "violet" in c else 0,
        "parity": "even" if n % 2 == 0 else "odd",
    }


def compute_gap(previous: str, current: str):
    if not previous:
        return "", 1
    if len(previous) == 17 and len(current) == 17 and previous.isdigit() and current.isdigit():
        if previous[:13] == current[:13]:
            diff = int(current[13:]) - int(previous[13:])
            return str(max(diff - 1, 0)), int(diff == 1)
        if int(previous[13:]) == 2880 and int(current[13:]) == 1:
            return "0", 1
        return "day_change", 0
    return "", 0


def get_page(session: requests.Session, date_str: str, index: int = 1) -> dict:
    """Read only publicly published results; no API key or signature is needed in supplied JS."""
    payload = {
        "PageSize": PAGE_SIZE,
        "PageIndex": index,
        "TypeId": TYPE_ID,
        "Time": date_str,
    }
    response = session.post(
        API_URL,
        params={"_t": int(time.time() * 1000)},
        json=payload,
        headers={"Accept": "application/json"},
        timeout=20,
    )
    response.raise_for_status()  # Respect API restrictions such as 403 and 429.
    body = response.json()
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        raise ValueError("Unexpected Platsaas response: expected a 'data' array")
    return body


def normalize_row(item: dict) -> dict | None:
    if not isinstance(item, dict) or str(item.get("state", "")) != "1":
        return None  # Pending row: premium/number are intentionally blank.
    issue = str(item.get("issueNumber", "")).strip()
    number = str(item.get("number", "")).strip()
    premium = str(item.get("premium", "")).strip()
    colour = str(item.get("colour", item.get("color", ""))).strip()
    if not issue.isdigit() or len(issue) != 17 or number not in {str(i) for i in range(10)}:
        return None
    if not (len(premium) == 5 and premium.isdigit()):
        print(f"[SKIP] Issue {issue}: premium is not exactly five digits: {premium!r}", flush=True)
        return None
    if premium[-1] != number:
        print(f"[WARNING] Issue {issue}: premium={premium} does not end in number={number}; ignored", flush=True)
        return None
    return {
        "issueNumber": issue,
        "number": number,
        "premium": premium,  # IMPORTANT: keep STRING (preserves leading zeros).
        "color": colour,
        "sum": "",       # This API does not supply a 'sum' field.
        "startTime": str(item.get("startTime") or ""),
        "endTime": str(item.get("endTime") or ""),
        "premium_source": "platsaas",
    }


def load_existing_records() -> dict:
    known = {}
    if not CSV_PATH.exists():
        return known
    with CSV_PATH.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            issue = (row.get("issueNumber") or "").strip()
            if issue:
                known[issue] = row
    return known


def merge_rows(known: dict, items: list, source_mode: str):
    """Keep historical rows and update older one-digit premiums when available."""
    added = updated = 0
    observed_at = datetime.now(IST).isoformat(timespec="seconds")
    for item in items:
        rec = normalize_row(item)
        if rec is None:
            continue
        issue = rec["issueNumber"]
        old = known.get(issue)
        if old is None:
            rec.update({
                "api_serviceTime": "", "fetched_at_ist": observed_at,
                "premium_fetched_at_ist": observed_at,
                "source_mode": source_mode,
            })
            known[issue] = rec
            added += 1
        else:
            if str(old.get("number", "")) not in ("", rec["number"]):
                print(f"[WARNING] Issue {issue} has conflicting winning numbers; retained original row", flush=True)
                continue
            # Upgrade premium when a previously stored row has only the result digit.
            if str(old.get("premium", "")) != rec["premium"] or not old.get("endTime"):
                old.update({
                    "number": rec["number"], "premium": rec["premium"],
                    "color": rec["color"] or old.get("color", ""),
                    "startTime": rec["startTime"], "endTime": rec["endTime"],
                    "premium_source": "platsaas", "premium_fetched_at_ist": observed_at,
                    "source_mode": "platsaas_premium_upgrade",
                })
                updated += 1
    return added, updated


def enriched_rows(known: dict) -> list:
    result = []
    last_id = ""
    for issue in sorted(known):
        old = known[issue]
        number = str(old.get("number", "")).strip()
        if number not in {str(i) for i in range(10)}:
            continue
        color = str(old.get("color", "")).strip()
        meta = parse_issue_metadata(issue)
        derived = derive_fields(number, color)
        gap, consecutive = compute_gap(last_id, issue)
        row = dict(old)
        row.update({
            "issueNumber": issue,
            **meta,
            "number": number,
            "color": color,
            **derived,
            "premium": str(old.get("premium", "")),
            "sum": str(old.get("sum", "")),
            "gap_from_prev": gap,
            "is_consecutive": consecutive,
        })
        result.append({col: row.get(col, "") for col in CSV_COLUMNS})
        last_id = issue
    return result


def save_all(known: dict):
    rows = enriched_rows(known)
    tmp_csv = CSV_PATH.with_suffix(".csv.tmp")
    with tmp_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    tmp_csv.replace(CSV_PATH)
    numbers = Counter(r["number"] for r in rows)
    full_premium = sum(
        len(r["premium"]) == 5 and r["premium"].isdigit() and r["premium"][-1] == r["number"]
        for r in rows
    )
    handoff = {
        "project": "WinGo_30S Premium Collector",
        "source": API_URL,
        "dataset_csv_path": str(CSV_PATH),
        "updated_at_ist": datetime.now(IST).isoformat(timespec="seconds"),
        "total_unique_rounds": len(rows),
        "five_digit_premium_verified_count": full_premium,
        "rounds_without_full_premium": len(rows) - full_premium,
        "earliest_issueNumber": rows[0]["issueNumber"] if rows else None,
        "latest_issueNumber": rows[-1]["issueNumber"] if rows else None,
        "distributions": {"numbers_0_to_9": {str(n): numbers.get(str(n), 0) for n in range(10)}},
        "columns": CSV_COLUMNS,
        "latest_20_rounds": rows[-20:],
    }
    tmp_json = HANDOFF_PATH.with_suffix(".json.tmp")
    with tmp_json.open("w", encoding="utf-8") as f:
        json.dump(handoff, f, indent=2)
    tmp_json.replace(HANDOFF_PATH)
    return rows


def display(rows: list, limit: int = 15):
    print("\n" + "=" * 100)
    print(f"WinGo 30S — total saved: {len(rows)} | latest {min(limit, len(rows))} rounds")
    print(f"{'Issue Number':<19} {'Premium':<9} {'Number':<7} {'Color':<15} {'End Time'}")
    print("-" * 100)
    for row in rows[-limit:]:
        print(f"{row['issueNumber']:<19} {row['premium']:<9} {row['number']:<7} "
              f"{row['color']:<15} {row['endTime']}")
    print("=" * 100 + "\n", flush=True)


def fetch_and_save(session: requests.Session, known: dict, day: str, index: int = 1, source_mode="live"):
    payload = get_page(session, day, index)
    items = payload["data"]
    added, updated = merge_rows(known, items, source_mode)
    if added or updated or not CSV_PATH.exists():
        rows = save_all(known)
        if added or updated:
            print(f"[{datetime.now(IST):%H:%M:%S} IST] New: {added}, premium upgrades: {updated}", flush=True)
            display(rows)
    return payload, added, updated


def main():
    parser = argparse.ArgumentParser(description="Collect five-digit WinGo 30S premiums")
    parser.add_argument("--once", action="store_true", help="Fetch once and exit")
    parser.add_argument("--backfill-days", type=int, default=0,
                        help="Optional: download paginated history for N calendar days (including today)")
    args = parser.parse_args()
    if args.backfill_days < 0 or args.backfill_days > 365:
        parser.error("--backfill-days must be between 0 and 365")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    STOP_FILE.unlink(missing_ok=True)

    known = load_existing_records()
    print(f"Loaded {len(known)} previously saved rounds.", flush=True)
    if CSV_PATH.exists():
        backup = OUTPUT_DIR / f"wingo_30s_history_backup_{datetime.now(IST):%Y%m%d_%H%M%S}.csv"
        shutil.copy2(CSV_PATH, backup)
        print(f"Backup saved: {backup}", flush=True)

    with requests.Session() as session:
        if args.backfill_days:
            today = datetime.now(IST).date()
            print(f"Backfilling {args.backfill_days} day(s)...", flush=True)
            for days_ago in range(args.backfill_days - 1, -1, -1):
                date_str = (today - timedelta(days=days_ago)).isoformat()
                page = 1
                while True:
                    try:
                        body, added, updated = fetch_and_save(session, known, date_str, page, "backfill")
                    except (requests.RequestException, ValueError) as exc:
                        print(f"[ERROR] Backfill {date_str} page {page}: {exc}", flush=True)
                        if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code in (403, 429):
                            print("The server refused the request. Stop and respect its access/rate limits.")
                            return
                        break
                    total_pages = body.get("totalPage")
                    if not body["data"] or (isinstance(total_pages, int) and page >= total_pages):
                        break
                    page += 1
                    if page > 100:  # avoid accidental infinite pagination
                        break
                    time.sleep(1.5)  # gentle pagination
            print("Backfill complete.", flush=True)

        if args.backfill_days and args.once:
            return
        if not args.backfill_days or not args.once:
            try:
                payload, _, _ = fetch_and_save(session, known, datetime.now(IST).date().isoformat(), 1)
                if not payload["data"]:
                    print("API returned no records for today.", flush=True)
            except (requests.RequestException, ValueError) as exc:
                print(f"First fetch failed: {exc}", flush=True)
                if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code in (403, 429):
                    return
            if args.once:
                return

        print(f"Polling every {POLL_INTERVAL_SECONDS} seconds. Press Ctrl+C to stop.", flush=True)
        try:
            while not STOP_FILE.exists():
                time.sleep(POLL_INTERVAL_SECONDS)
                try:
                    fetch_and_save(session, known, datetime.now(IST).date().isoformat(), 1)
                except requests.HTTPError as exc:
                    print(f"HTTP error: {exc}", flush=True)
                    if exc.response is not None and exc.response.status_code in (403, 429):
                        print("Server rejected the request; stopping to respect its limits.", flush=True)
                        break
                    time.sleep(min(BACKOFF_SECONDS, 30))
                except (requests.RequestException, ValueError, OSError) as exc:
                    print(f"Temporary fetch/save error: {exc}", flush=True)
        except KeyboardInterrupt:
            print("\nStopped by user.")


if __name__ == "__main__":
    import os as _publication_os
    if _publication_os.environ.get("WINGO_ENABLE_NETWORK") != "1":
        raise SystemExit("Archived collector. Set WINGO_ENABLE_NETWORK=1 only for explicitly authorized collection; not used by the audit suite.")
    main()
