"""
WinGo API Comparison Script
Compares API 1 (Original WinGo) vs API 2 (TRION AI) historical results.

Reuses validation logic from colour-ai/wingo_investigation/collect_history.py.
"""

import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ===================================
# CONFIGURATION
# ===================================

API1_URL = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"
API2_URL = "https://wingo30.com/api/developer/30-sec-game-history"

# Bearer token for API 2 from environment variable (never hardcoded)
API2_KEY = os.environ.get("TRION_API_KEY", "")

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_DIR / "results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_ROUNDS = 500
REQUEST_DELAY = 0.4  # seconds between page requests

VALID_NUMBERS = {str(i) for i in range(10)}

# Deterministic colour mapping (reused from master dataset logic)
def number_to_colour(n: int) -> str:
    if n == 0: return "Red+Violet"
    if n == 5: return "Green+Violet"
    if n in (1, 3, 7, 9): return "Green"
    if n in (2, 4, 6, 8): return "Red"
    return "Unknown"

def number_to_size(n: int) -> str:
    return "Small" if n <= 4 else "Big"


# ===================================
# STEP 1: PROBE API STRUCTURES
# ===================================

def probe_api1():
    """Probe API 1 response structure."""
    print("\n--- Probing API 1 (Original WinGo) ---")
    try:
        resp = requests.get(
            API1_URL,
            params={"pageNo": 1, "pageSize": 5},
            headers={"Accept": "application/json"},
            timeout=15,
        )
        print(f"HTTP Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"Response body (first 500 chars): {resp.text[:500]}")
            return None

        payload = resp.json()
        print(f"Top-level keys: {list(payload.keys())}")
        print(f"code: {payload.get('code')}, msg: {payload.get('msg')}")

        data = payload.get("data", {})
        print(f"data keys: {list(data.keys())}")
        print(f"pageNo: {data.get('pageNo')}, totalPage: {data.get('totalPage')}, totalCount: {data.get('totalCount')}")

        records = data.get("list", [])
        print(f"Records returned: {len(records)}")
        if records:
            print(f"First record keys: {list(records[0].keys())}")
            print(f"First record sample: {json.dumps(records[0], indent=2)}")
        return payload

    except Exception as e:
        print(f"[ERROR] API 1 probe failed: {e}")
        return None


def probe_api2():
    """Probe API 2 response structure."""
    print("\n--- Probing API 2 (TRION AI) ---")
    headers = {"Accept": "application/json"}
    if API2_KEY:
        headers["Authorization"] = f"Bearer {API2_KEY}"
    else:
        print("[NOTICE] No TRION_API_KEY environment variable set. Trying without auth.")

    try:
        resp = requests.get(
            API2_URL,
            params={"page": 1, "limit": 5},
            headers=headers,
            timeout=15,
        )
        print(f"HTTP Status: {resp.status_code}")
        print(f"Content-Type: {resp.headers.get('Content-Type', 'N/A')}")

        if resp.status_code == 401:
            print("[AUTH REQUIRED] API 2 returned 401 Unauthorized.")
            print("Set the TRION_API_KEY environment variable with your Bearer token.")
            print(f"Response body: {resp.text[:500]}")
            return None
        if resp.status_code == 403:
            print("[FORBIDDEN] API 2 returned 403 Forbidden.")
            print(f"Response body: {resp.text[:500]}")
            return None
        if resp.status_code != 200:
            print(f"Response body (first 500 chars): {resp.text[:500]}")
            return None

        try:
            payload = resp.json()
        except ValueError:
            print(f"[ERROR] Non-JSON response body (first 500 chars): {resp.text[:500]}")
            return None

        if isinstance(payload, dict):
            print(f"Top-level keys: {list(payload.keys())}")
            for k, v in payload.items():
                if isinstance(v, list):
                    print(f"  {k}: list of {len(v)} items")
                    if v:
                        print(f"    First item keys: {list(v[0].keys()) if isinstance(v[0], dict) else type(v[0]).__name__}")
                        print(f"    First item: {json.dumps(v[0], indent=2) if isinstance(v[0], dict) else v[0]}")
                elif isinstance(v, dict):
                    print(f"  {k}: dict with keys {list(v.keys())}")
                else:
                    print(f"  {k}: ({type(v).__name__}) -> {repr(v)}")
        elif isinstance(payload, list):
            print(f"Top-level is a list of {len(payload)} items.")
            if payload and isinstance(payload[0], dict):
                print(f"First item keys: {list(payload[0].keys())}")
                print(f"First item: {json.dumps(payload[0], indent=2)}")

        return payload

    except Exception as e:
        print(f"[ERROR] API 2 probe failed: {e}")
        return None


# ===================================
# STEP 2: FETCH RECORDS
# ===================================

def fetch_api1(max_rounds=MAX_ROUNDS):
    """Fetch up to max_rounds from API 1.
    
    The live API only serves a static 10-record window and ignores pagination,
    so we also load from the local collected CSV (collected by collect_history.py
    and collect_live.py) to get a full historical dataset.
    """
    print(f"\n{'='*60}")
    print(f"FETCHING API 1 (Original WinGo) — up to {max_rounds} rounds")
    print(f"{'='*60}")

    records = {}

    # First: fetch the live 10-record window from the API
    try:
        resp = requests.get(
            API1_URL,
            params={"pageNo": 1, "pageSize": 100},
            headers={"Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") == 0:
            items = payload.get("data", {}).get("list", [])
            for item in items:
                if not isinstance(item, dict):
                    continue
                period = str(item.get("issueNumber", "")).strip()
                num_str = str(item.get("number", "")).strip()
                if period and period.isdigit() and num_str in VALID_NUMBERS:
                    records[period] = {
                        "period_id": period,
                        "number": int(num_str),
                        "api_colour": str(item.get("color", "")).strip(),
                        "premium": str(item.get("premium", "")).strip(),
                        "service_time": str(payload.get("serviceTime", "")).strip(),
                    }
            print(f"  Live API window: {len(records)} records fetched.")
    except Exception as e:
        print(f"  [WARNING] Live API fetch failed: {e}")

    # Second: augment with locally collected CSV data
    local_csv = PROJECT_DIR / "wingo_investigation" / "collected_data" / "wingo_30s_history.csv"
    if local_csv.exists():
        import csv as csv_mod
        with local_csv.open("r", encoding="utf-8") as f:
            reader = csv_mod.DictReader(f)
            local_count = 0
            for row in reader:
                period = str(row.get("issueNumber", "")).strip()
                num_str = str(row.get("number", "")).strip()
                if period and period.isdigit() and num_str in VALID_NUMBERS:
                    if period not in records:
                        records[period] = {
                            "period_id": period,
                            "number": int(num_str),
                            "api_colour": str(row.get("color", "")).strip(),
                            "premium": str(row.get("premium", "")).strip(),
                            "service_time": str(row.get("api_serviceTime", "")).strip(),
                        }
                        local_count += 1
        print(f"  Local collected CSV: {local_count} additional records loaded from {local_csv.name}")
    else:
        print(f"  [INFO] No local CSV found at {local_csv}")

    # Trim to max_rounds (most recent)
    if len(records) > max_rounds:
        sorted_pids = sorted(records.keys(), reverse=True)[:max_rounds]
        records = {pid: records[pid] for pid in sorted_pids}
        print(f"  Trimmed to most recent {max_rounds} records.")

    print(f"API 1 total unique records: {len(records)}")
    return records


def fetch_api2(max_rounds=MAX_ROUNDS):
    """Fetch up to max_rounds from API 2 with pagination."""
    print(f"\n{'='*60}")
    print(f"FETCHING API 2 (TRION AI) — up to {max_rounds} rounds")
    print(f"{'='*60}")

    headers = {"Accept": "application/json"}
    if API2_KEY:
        headers["Authorization"] = f"Bearer {API2_KEY}"
    else:
        print("[NOTICE] No TRION_API_KEY. Trying unauthenticated.")

    records = {}
    page = 1
    limit = 100

    while len(records) < max_rounds:
        try:
            resp = requests.get(
                API2_URL,
                params={"page": page, "limit": limit},
                headers=headers,
                timeout=15,
            )
        except Exception as e:
            print(f"[ERROR] API 2 page {page} request failed: {e}")
            break

        if resp.status_code == 401:
            print("[AUTH ERROR] API 2 returned 401. Set TRION_API_KEY env var.")
            print(f"Response: {resp.text[:300]}")
            break
        if resp.status_code == 403:
            print("[FORBIDDEN] API 2 returned 403.")
            print(f"Response: {resp.text[:300]}")
            break
        if resp.status_code != 200:
            print(f"[ERROR] API 2 page {page} HTTP {resp.status_code}: {resp.text[:300]}")
            break

        try:
            payload = resp.json()
        except ValueError:
            print(f"[ERROR] API 2 page {page} non-JSON response: {resp.text[:300]}")
            break

        # Adapt to response structure
        items = []
        total_pages = 1

        if isinstance(payload, dict):
            # Try common structures: data.list, data, results, records
            if "data" in payload:
                d = payload["data"]
                if isinstance(d, dict):
                    items = d.get("list", d.get("results", d.get("records", [])))
                    total_pages = int(d.get("totalPage", d.get("total_pages", d.get("pages", 1))))
                elif isinstance(d, list):
                    items = d
            elif "results" in payload:
                items = payload["results"]
                total_pages = int(payload.get("total_pages", payload.get("pages", 1)))
            elif "records" in payload:
                items = payload["records"]
            elif "list" in payload:
                items = payload["list"]
            else:
                # Maybe the dict itself has period-like keys
                print(f"[INFO] API 2 unexpected dict structure. Keys: {list(payload.keys())}")
                break
        elif isinstance(payload, list):
            items = payload
        else:
            print(f"[ERROR] API 2 returned unexpected type: {type(payload).__name__}")
            break

        if not items:
            print(f"[INFO] API 2 page {page}: empty result set. Stopping.")
            break

        new_count = 0
        for item in items:
            if not isinstance(item, dict):
                continue

            # Try common field names for period ID
            period = ""
            for k in ("issueNumber", "issue_number", "period", "period_id", "periodId", "round_id", "id"):
                if k in item and item[k] is not None:
                    period = str(item[k]).strip()
                    break

            # Try common field names for number
            num_val = None
            for k in ("number", "winning_number", "result", "digit", "outcome"):
                if k in item and item[k] is not None:
                    try:
                        num_val = int(item[k])
                    except (ValueError, TypeError):
                        pass
                    break

            if not period or num_val is None or not (0 <= num_val <= 9):
                continue

            # Try common field names for colour
            colour = ""
            for k in ("color", "colour", "winning_color", "winning_colour"):
                if k in item and item[k] is not None:
                    colour = str(item[k]).strip()
                    break

            # Try common field names for timestamp
            timestamp = ""
            for k in ("timestamp", "time", "created_at", "draw_time", "openTime", "api_serviceTime"):
                if k in item and item[k] is not None:
                    timestamp = str(item[k]).strip()
                    break

            if period not in records:
                records[period] = {
                    "period_id": period,
                    "number": num_val,
                    "api_colour": colour,
                    "timestamp": timestamp,
                }
                new_count += 1

        print(f"  Page {page}: received {len(items)}, new={new_count}, total={len(records)}")

        if new_count == 0 or page >= total_pages:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    print(f"API 2 total unique records: {len(records)}")
    return records


# ===================================
# STEP 3: NORMALIZE & COMPARE
# ===================================

def normalize_record(rec, source):
    """Add deterministic colour and size based on number."""
    num = rec["number"]
    return {
        "period_id": rec["period_id"],
        "number": num,
        "colour_deterministic": number_to_colour(num),
        "colour_api": rec.get("api_colour", ""),
        "size": number_to_size(num),
        "source": source,
        "timestamp": rec.get("timestamp", rec.get("service_time", "")),
    }


def export_csv(filepath, rows, fieldnames):
    """Write rows to CSV."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Exported: {filepath} ({len(rows)} rows)")


def compare_apis(api1_records, api2_records):
    """Compare two sets of records and produce summary + CSV exports."""
    print(f"\n{'='*60}")
    print("COMPARING API RESULTS")
    print(f"{'='*60}")

    # Normalize
    norm1 = {pid: normalize_record(r, "API1_Original") for pid, r in api1_records.items()}
    norm2 = {pid: normalize_record(r, "API2_TRION") for pid, r in api2_records.items()}

    pids1 = set(norm1.keys())
    pids2 = set(norm2.keys())

    common_pids = sorted(pids1 & pids2)
    only_api1 = sorted(pids1 - pids2)
    only_api2 = sorted(pids2 - pids1)

    # Compare common records
    number_matches = 0
    number_mismatches = []
    colour_matches = 0
    colour_mismatches = []
    timestamp_diffs = []

    comparison_rows = []

    for pid in common_pids:
        r1 = norm1[pid]
        r2 = norm2[pid]

        num_match = r1["number"] == r2["number"]
        col_match = r1["colour_deterministic"] == r2["colour_deterministic"]

        if num_match:
            number_matches += 1
        else:
            number_mismatches.append({
                "period_id": pid,
                "api1_number": r1["number"],
                "api2_number": r2["number"],
            })

        if col_match:
            colour_matches += 1
        else:
            colour_mismatches.append({
                "period_id": pid,
                "api1_colour": r1["colour_deterministic"],
                "api2_colour": r2["colour_deterministic"],
            })

        ts1 = r1.get("timestamp", "")
        ts2 = r2.get("timestamp", "")
        ts_diff = "N/A"
        if ts1 and ts2 and ts1 != ts2:
            ts_diff = f"API1={ts1} vs API2={ts2}"
            timestamp_diffs.append({"period_id": pid, "diff": ts_diff})
        elif ts1 == ts2:
            ts_diff = "Match"

        comparison_rows.append({
            "period_id": pid,
            "api1_number": r1["number"],
            "api2_number": r2["number"],
            "number_match": "YES" if num_match else "NO",
            "api1_colour": r1["colour_deterministic"],
            "api2_colour": r2["colour_deterministic"],
            "colour_match": "YES" if col_match else "NO",
            "api1_colour_raw": r1["colour_api"],
            "api2_colour_raw": r2["colour_api"],
            "api1_timestamp": ts1,
            "api2_timestamp": ts2,
            "timestamp_match": ts_diff,
        })

    # Export CSVs
    print("\nExporting CSV files...")

    api_fields = ["period_id", "number", "colour_deterministic", "colour_api", "size", "source", "timestamp"]
    api1_rows = sorted(norm1.values(), key=lambda r: r["period_id"])
    export_csv(OUTPUT_DIR / "api1_results.csv", api1_rows, api_fields)

    api2_rows = sorted(norm2.values(), key=lambda r: r["period_id"])
    export_csv(OUTPUT_DIR / "api2_results.csv", api2_rows, api_fields)

    comp_fields = [
        "period_id",
        "api1_number", "api2_number", "number_match",
        "api1_colour", "api2_colour", "colour_match",
        "api1_colour_raw", "api2_colour_raw",
        "api1_timestamp", "api2_timestamp", "timestamp_match",
    ]
    export_csv(OUTPUT_DIR / "comparison.csv", comparison_rows, comp_fields)

    # Calculate agreement
    total_common = len(common_pids)
    agreement = (number_matches / total_common * 100) if total_common > 0 else 0.0

    # Print Summary
    print(f"\n{'='*50}")
    print("===== WINGO API COMPARISON =====")
    print(f"{'='*50}")
    print()
    print(f"API 1 records:              {len(api1_records):,}")
    print(f"API 2 records:              {len(api2_records):,}")
    print()
    print(f"Matching period IDs:        {total_common:,}")
    print(f"Matching winning numbers:   {number_matches:,}")
    print(f"Number mismatches:          {len(number_mismatches):,}")
    print(f"Colour mismatches:          {len(colour_mismatches):,}")
    print()
    print(f"Only in API 1:              {len(only_api1):,}")
    print(f"Only in API 2:              {len(only_api2):,}")
    print()
    print(f"Timestamp differences:      {len(timestamp_diffs):,}")
    print(f"Overall agreement:          {agreement:.2f}%")

    if number_mismatches:
        print(f"\n--- Number Mismatches (showing up to 10) ---")
        for m in number_mismatches[:10]:
            print(f"  Period {m['period_id']}: API1={m['api1_number']} vs API2={m['api2_number']}")

    if colour_mismatches:
        print(f"\n--- Colour Mismatches (showing up to 10) ---")
        for m in colour_mismatches[:10]:
            print(f"  Period {m['period_id']}: API1={m['api1_colour']} vs API2={m['api2_colour']}")

    if only_api1:
        print(f"\n--- Periods Only in API 1 (first 10) ---")
        for pid in only_api1[:10]:
            print(f"  {pid}")

    if only_api2:
        print(f"\n--- Periods Only in API 2 (first 10) ---")
        for pid in only_api2[:10]:
            print(f"  {pid}")

    print(f"\nCSV files saved to: {OUTPUT_DIR}")


# ===================================
# MAIN
# ===================================

if __name__ == "__main__":
    print("=" * 60)
    print("WINGO API COMPARISON TOOL")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # Step 1: Probe both APIs
    print("\n[STEP 1] Probing API response structures...")
    probe1 = probe_api1()
    probe2 = probe_api2()

    api1_ok = probe1 is not None
    api2_ok = probe2 is not None

    print(f"\nAPI 1 reachable: {api1_ok}")
    print(f"API 2 reachable: {api2_ok}")

    # Step 2: Fetch records
    api1_records = {}
    api2_records = {}

    if api1_ok:
        api1_records = fetch_api1(MAX_ROUNDS)
    else:
        print("\n[SKIP] API 1 unreachable. Cannot fetch records.")

    if api2_ok:
        api2_records = fetch_api2(MAX_ROUNDS)
    else:
        print("\n[SKIP] API 2 unreachable. Cannot fetch records.")

    # Step 3: Compare
    if api1_records or api2_records:
        compare_apis(api1_records, api2_records)
    else:
        print("\n[ERROR] No records fetched from either API. Cannot compare.")

    print("\nFinished.")
