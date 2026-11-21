"""Compare completed WinGo_30S results from two read-only history APIs.

Usage:
    pip install requests
    python compare_wingo_apis.py

Set TRION_API_KEY in your environment, or enter it at the hidden prompt.
No API keys are written to output files.
"""

import csv
import getpass
import os
import time
from collections import Counter
from pathlib import Path

import requests

DRAW_API = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"
TRION_API = "https://wingo30.com/api/developer/30-sec-game-history"
TARGET_ROUNDS = 500
MAX_PAGES = 100
PAUSE_SECONDS = 1.2  # Respect the documented 60 requests/minute limit
OUTPUT_DIR = Path("wingo_api_comparison")


def request_json(session, url, params):
    """Retry transient server errors and rate limits, not authentication failures."""
    for attempt in range(4):
        response = session.get(url, params=params, timeout=(10, 30))
        if response.status_code == 401:
            raise RuntimeError(
                "TRION returned HTTP 401. Obtain your own API key from "
                "https://wingo30.com/developer and set TRION_API_KEY."
            )
        if response.status_code in (429, 500, 502, 503, 504):
            delay = response.headers.get("Retry-After", "")
            try:
                delay = min(max(float(delay), 1.0), 60.0)
            except ValueError:
                delay = min(2 ** (attempt + 1), 30)
            print(f"HTTP {response.status_code}; retrying after {delay:g}s")
            time.sleep(delay)
            continue
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError("Endpoint returned non-JSON data") from exc
    raise RuntimeError("Endpoint did not respond after multiple attempts")


def normalize_colors(value):
    if isinstance(value, list):
        pieces = value
    elif isinstance(value, str):
        pieces = value.split(",")
    else:
        pieces = []
    return ",".join(sorted({str(v).strip().lower() for v in pieces if str(v).strip()}))


def add_record(records, *, period, number, color, source, timestamp=""):
    period = str(period).strip()  # Preserve IDs as strings, including leading zeroes
    digit = int(number)
    if not (0 <= digit <= 9):
        raise ValueError(f"Unexpected digit for {period}: {digit}")
    rec = {
        "period_id": period,
        "number": digit,
        "color": normalize_colors(color),
        "timestamp": str(timestamp or ""),
        "source": source,
    }
    if period in records and records[period]["number"] != digit:
        raise ValueError(f"Conflicting results from {source} for {period}")
    records[period] = rec


def get_draw_history(session):
    records = {}
    for page in range(1, MAX_PAGES + 1):
        payload = request_json(
            session, DRAW_API,
            {"pageNo": page, "pageSize": 100},
        )
        if payload.get("code") not in (0, None):
            raise RuntimeError(f"Draw API returned code={payload.get('code')}")
        data = payload.get("data") or {}
        rows = data.get("list") or []
        if not rows:
            break
        for row in rows:
            add_record(
                records, period=row["issueNumber"],
                number=row["number"], color=row.get("color", ""),
                source="draw.ar-lottery01.com",
            )
        print(f"Draw API: page {page}, {len(records)} distinct rounds")
        if len(records) >= TARGET_ROUNDS or page >= int(data.get("totalPage") or page):
            break
        time.sleep(PAUSE_SECONDS)
    return records


def get_trion_history(session):
    records = {}
    for page in range(1, MAX_PAGES + 1):
        payload = request_json(
            session, TRION_API,
            {"page": page, "limit": 100},
        )
        if payload.get("ok") is not True:
            raise RuntimeError(f"TRION API reported an error: {payload.get('error', payload.get('message'))}")
        rows = payload.get("data") or []
        if not rows:
            break
        for row in rows:
            add_record(
                records, period=row["period"],
                number=row["number"],
                color=row.get("colors", row.get("color", "")),
                timestamp=row.get("time", row.get("blockTimestamp", "")),
                source="wingo30.com",
            )
        print(f"TRION API: page {page}, {len(records)} distinct rounds")
        pagination = payload.get("pagination") or {}
        if len(records) >= TARGET_ROUNDS:
            break
        if pagination.get("hasNextPage") is False:
            break
        if pagination.get("totalPages") and page >= int(pagination["totalPages"]):
            break
        time.sleep(PAUSE_SECONDS)
    return records


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    token = os.environ.get("TRION_API_KEY", "").strip()
    if not token:
        token = getpass.getpass("Enter your TRION API key (input hidden): ").strip()
    if not token:
        raise SystemExit("A TRION API key is required. Obtain one from wingo30.com/developer.")

    OUTPUT_DIR.mkdir(exist_ok=True)
    draw_session = requests.Session()
    draw_session.headers.update({"Accept": "application/json"})
    trion_session = requests.Session()
    trion_session.headers.update({
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    })

    draw = get_draw_history(draw_session)
    trion = get_trion_history(trion_session)

    fields = ["period_id", "number", "color", "timestamp", "source"]
    write_csv(OUTPUT_DIR / "draw_history.csv", sorted(draw.values(), key=lambda r: r["period_id"]), fields)
    write_csv(OUTPUT_DIR / "trion_history.csv", sorted(trion.values(), key=lambda r: r["period_id"]), fields)

    comparison = []
    stats = Counter()
    for period in sorted(set(draw) | set(trion)):
        a, b = draw.get(period), trion.get(period)
        if a is None:
            status = "ONLY_TRION"
        elif b is None:
            status = "ONLY_DRAW"
        elif a["number"] != b["number"]:
            status = "NUMBER_MISMATCH"
        elif a["color"] and b["color"] and a["color"] != b["color"]:
            status = "COLOR_MISMATCH"
        else:
            status = "MATCH"
        stats[status] += 1
        comparison.append({
            "period_id": period,
            "draw_number": "" if a is None else a["number"],
            "trion_number": "" if b is None else b["number"],
            "draw_color": "" if a is None else a["color"],
            "trion_color": "" if b is None else b["color"],
            "trion_timestamp": "" if b is None else b["timestamp"],
            "status": status,
        })

    write_csv(
        OUTPUT_DIR / "comparison.csv", comparison,
        ["period_id", "draw_number", "trion_number", "draw_color",
         "trion_color", "trion_timestamp", "status"],
    )

    overlaps = len(set(draw) & set(trion))
    print("\n===== COMPARISON =====")
    print(f"Draw records: {len(draw)}; TRION records: {len(trion)}")
    print(f"Exact matching period IDs: {overlaps}")
    for key in ["MATCH", "NUMBER_MISMATCH", "COLOR_MISMATCH", "ONLY_DRAW", "ONLY_TRION"]:
        print(f"{key}: {stats[key]}")
    print("Draw period ID lengths:", dict(Counter(map(len, draw))))
    print("TRION period ID lengths:", dict(Counter(map(len, trion))))
    print("Sample draw IDs:", sorted(draw, reverse=True)[:3])
    print("Sample TRION IDs:", sorted(trion, reverse=True)[:3])
    if overlaps == 0:
        print("\nNo exact period-ID overlap. Different ID formats, game feeds, or date ranges")
        print("could explain this. DO NOT match records by suffix or row position alone.")
    print(f"\nReports saved in: {OUTPUT_DIR.resolve()}")
    print("These results compare completed rounds; they do not reveal secret RNG seeds.")


if __name__ == "__main__":
    import os as _publication_os
    if _publication_os.environ.get("WINGO_ENABLE_NETWORK") != "1":
        raise SystemExit("Archived collector. Set WINGO_ENABLE_NETWORK=1 only for explicitly authorized collection; not used by the audit suite.")
    try:
        main()
    except requests.RequestException as exc:
        raise SystemExit(f"HTTP/network error: {exc}") from exc
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"Comparison failed: {exc}") from exc
