import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

API_URL = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "collected_data"
VALID_NUMBERS = {str(i) for i in range(10)}
REQUIRED_FIELDS = ("issueNumber", "number", "color", "premium", "sum")

CSV_COLUMNS = [
    "issueNumber",
    "number",
    "color",
    "premium",
    "sum",
    "record_timestamp",
    "api_serviceTime",
    "fetched_at_utc",
    "source_page",
]


def load_existing_records(csv_path: Path) -> dict:
    """Load previously saved records by issueNumber so we never overwrite or duplicate."""
    existing = {}
    if not csv_path.exists():
        return existing

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            issue_id = str(row.get("issueNumber", "")).strip()
            if issue_id:
                existing[issue_id] = {
                    "issueNumber": issue_id,
                    "number": str(row.get("number", "")),
                    "color": str(row.get("color", "")),
                    "premium": str(row.get("premium", "")),
                    "sum": str(row.get("sum", "")),
                }
    return existing


def append_csv_rows(csv_path: Path, columns: list, rows: list):
    """Append rows incrementally and flush to disk immediately."""
    if not rows:
        return
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)
        f.flush()


def append_raw_jsonl(jsonl_path: Path, entry: dict):
    """Save raw response metadata and structure incrementally."""
    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        f.flush()


def validate_record(item: dict) -> tuple:
    """
    Validate a single record from data.list.
    Returns (is_valid, missing_fields_list, reason_if_malformed, normalized_dict).
    """
    if not isinstance(item, dict):
        return False, [], "Record is not a JSON object", {}

    missing = [field for field in REQUIRED_FIELDS if field not in item or item[field] is None]
    if missing:
        return False, missing, f"Missing required fields: {missing}", {}

    issue_number = str(item["issueNumber"]).strip()
    number_str = str(item["number"]).strip()
    color_str = str(item["color"]).strip()
    premium_str = str(item["premium"]).strip()
    sum_str = str(item["sum"]).strip()

    if not issue_number or not issue_number.isdigit():
        return False, [], f"Invalid issueNumber: {repr(issue_number)}", {}

    if number_str not in VALID_NUMBERS:
        return False, [], f"Invalid winning number (expected '0'-'9'): {repr(number_str)}", {}

    if not color_str:
        return False, [], "Empty color string", {}

    # Preserve per-record timestamp only if the API ever provides one; do not invent it.
    record_ts = ""
    for ts_key in ("timestamp", "createTime", "openTime", "drawTime"):
        if ts_key in item and item[ts_key] is not None:
            record_ts = str(item[ts_key]).strip()
            break

    normalized = {
        "issueNumber": issue_number,
        "number": number_str,
        "color": color_str,
        "premium": premium_str,
        "sum": sum_str,
        "record_timestamp": record_ts,
    }
    return True, [], "", normalized


def main():
    parser = argparse.ArgumentParser(description="WinGo 30S Validated Historical Collector")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to store collected CSV and raw JSONL files",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Maximum number of pages to request if pagination is supported",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Delay in seconds between page requests",
    )
    args = parser.parse_args()

    output_dir: Path = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    history_csv = output_dir / "wingo_30s_history.csv"
    conflicts_csv = output_dir / "history_conflicts.csv"
    raw_jsonl = output_dir / "raw_history_pages.jsonl"

    known_records = load_existing_records(history_csv)

    print("=== Step 3: WinGo 30S Historical Collector ===")
    print(f"Output directory:          {output_dir}")
    print(f"Previously saved records:  {len(known_records)}")

    stats = {
        "pages_requested": 0,
        "api_failures": 0,
        "records_received": 0,
        "new_records": 0,
        "duplicates": 0,
        "conflicts": 0,
        "malformed_records": 0,
        "missing_field_records": 0,
    }

    page_no = 1
    max_pages_to_fetch = args.max_pages

    while page_no <= max_pages_to_fetch:
        stats["pages_requested"] += 1
        fetched_at_utc = datetime.now(timezone.utc).isoformat()
        params = {"pageNo": page_no, "pageSize": 10}

        try:
            response = requests.get(
                API_URL,
                params=params,
                headers={"Accept": "application/json"},
                timeout=10,
            )
        except requests.exceptions.RequestException as exc:
            stats["api_failures"] += 1
            print(f"[ERROR] Page {page_no} request failed: {exc}")
            break

        if response.status_code != 200:
            stats["api_failures"] += 1
            print(f"[ERROR] Page {page_no} returned HTTP {response.status_code}")
            break

        try:
            payload = response.json()
        except ValueError:
            stats["api_failures"] += 1
            print(f"[ERROR] Page {page_no} returned non-JSON body")
            break

        if not isinstance(payload, dict) or payload.get("code") != 0:
            stats["api_failures"] += 1
            print(f"[ERROR] Page {page_no} returned API error code: {payload.get('code')} ({payload.get('msg')})")
            break

        data = payload.get("data")
        if not isinstance(data, dict):
            stats["api_failures"] += 1
            print(f"[ERROR] Page {page_no} missing 'data' object")
            break

        returned_page_no = data.get("pageNo")
        total_page = data.get("totalPage")
        records = data.get("list")

        if not isinstance(records, list) or len(records) == 0:
            print(f"[INFO] Page {page_no} returned an empty list. Stopping pagination.")
            break

        # Save raw page response incrementally
        append_raw_jsonl(
            raw_jsonl,
            {
                "requested_page": page_no,
                "returned_pageNo": returned_page_no,
                "fetched_at_utc": fetched_at_utc,
                "serviceTime": payload.get("serviceTime"),
                "record_count": len(records),
                "first_issue": records[0].get("issueNumber") if isinstance(records[0], dict) else None,
                "last_issue": records[-1].get("issueNumber") if isinstance(records[-1], dict) else None,
                "payload": payload,
            },
        )

        if isinstance(total_page, int) and total_page > 0:
            max_pages_to_fetch = min(args.max_pages, total_page)

        service_time = str(payload.get("serviceTime", ""))
        new_rows_this_page = []
        conflict_rows_this_page = []
        new_in_page_count = 0

        for item in records:
            stats["records_received"] += 1
            is_valid, missing_fields, reason, norm = validate_record(item)

            if not is_valid:
                if missing_fields:
                    stats["missing_field_records"] += 1
                else:
                    stats["malformed_records"] += 1
                print(f"[WARNING] Invalid record on page {page_no}: {reason}")
                continue

            issue_id = norm["issueNumber"]
            row_to_save = {
                **norm,
                "api_serviceTime": service_time,
                "fetched_at_utc": fetched_at_utc,
                "source_page": page_no,
            }

            if issue_id in known_records:
                prev = known_records[issue_id]
                # Check if core outcome fields match identically
                if (
                    prev["number"] == norm["number"]
                    and prev["color"] == norm["color"]
                    and prev["premium"] == norm["premium"]
                    and prev["sum"] == norm["sum"]
                ):
                    stats["duplicates"] += 1
                else:
                    stats["conflicts"] += 1
                    print(
                        f"[CONFLICT] issueNumber {issue_id} has conflicting values! "
                        f"Existing={prev} vs New={norm}"
                    )
                    conflict_rows_this_page.append(row_to_save)
            else:
                known_records[issue_id] = {
                    "issueNumber": issue_id,
                    "number": norm["number"],
                    "color": norm["color"],
                    "premium": norm["premium"],
                    "sum": norm["sum"],
                }
                new_rows_this_page.append(row_to_save)
                stats["new_records"] += 1
                new_in_page_count += 1

        # Save incrementally after every page
        append_csv_rows(history_csv, CSV_COLUMNS, new_rows_this_page)
        append_csv_rows(conflicts_csv, CSV_COLUMNS, conflict_rows_this_page)

        first_id = records[0].get("issueNumber") if isinstance(records[0], dict) else "?"
        last_id = records[-1].get("issueNumber") if isinstance(records[-1], dict) else "?"
        print(
            f"Page {page_no:2d} (API reported pageNo={returned_page_no}): "
            f"received={len(records)}, new={new_in_page_count}, "
            f"range=[{last_id} .. {first_id}]"
        )

        # Check whether the endpoint ignores pagination parameters
        if page_no >= 2 and (returned_page_no == 1 or new_in_page_count == 0):
            print(
                f"\n[NOTICE] Requested pageNo={page_no}, but server returned "
                f"pageNo={returned_page_no} with {new_in_page_count} new records."
            )
            print(
                "[NOTICE] This confirms the .json URL serves a static/cached 10-record window "
                "and ignores pageNo pagination. Stopping pagination cleanly."
            )
            break

        page_no += 1
        if page_no <= max_pages_to_fetch:
            time.sleep(args.delay)

    print("\n=== Collection Summary Report ===")
    print(f"Pages requested:          {stats['pages_requested']}")
    print(f"API failures:             {stats['api_failures']}")
    print(f"Total records received:   {stats['records_received']}")
    print(f"New records saved:        {stats['new_records']}")
    print(f"Duplicate records:        {stats['duplicates']}")
    print(f"Conflicting records:      {stats['conflicts']}")
    print(f"Malformed records:        {stats['malformed_records']}")
    print(f"Missing-field records:    {stats['missing_field_records']}")
    print(f"Total unique in dataset:  {len(known_records)}")
    print(f"Saved CSV path:           {history_csv}")
    print(f"Saved raw JSONL path:     {raw_jsonl}")


if __name__ == "__main__":
    main()
