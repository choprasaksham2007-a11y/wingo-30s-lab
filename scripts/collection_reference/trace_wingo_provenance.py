"""Collect *public HTTP provenance evidence* for WinGo 30S result publication.

Only makes ordinary requests to the public API endpoints you've already observed.
No login, tokens, authentication bypass, or private server probing.

Install: py -m pip install requests
Run:     py trace_wingo_provenance.py --samples 5 --interval 30
Output:  collected_data/result_provenance.jsonl

This script cannot identify a private RNG origin by itself. The recorded request
IDs are for authorized operators to correlate against their backend/CDN logs.
"""

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc
OUT = Path(__file__).resolve().parent / "collected_data" / "result_provenance.jsonl"
ENDPOINTS = {
    "platsaas": "https://lotteryresultapi.platsaas.com/api/GetWinResult",
    "draw_history": "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json",
    "draw_schedule": "https://draw.ar-lottery01.com/WinGo/WinGo_30S.json",
}
# Whitelist: do NOT save cookies, Authorization, access tokens, or all headers.
SAFE_HEADERS = (
    "date", "cf-ray", "cf-cache-status", "x-oss-request-id", "etag",
    "last-modified", "age", "cache-control", "server", "content-type", "via",
    "x-cache", "x-served-by", "content-md5",
)


def now_utc():
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def summarize_records(name, data):
    if not isinstance(data, dict):
        return {"error": "Not a JSON object"}
    if name == "platsaas":
        items = data.get("data", [])
        if not isinstance(items, list):
            items = []
        # 0=pending, 1=completed; no assumption that all fields are present.
        return {
            "totalCount": data.get("totalCount"),
            "totalPage": data.get("totalPage"),
            "rounds": [{
                "issueNumber": str(x.get("issueNumber", "")),
                "premium": str(x.get("premium", "")),
                "number": str(x.get("number", "")),
                "state": x.get("state"),
                "startTime": x.get("startTime"),
                "endTime": x.get("endTime"),
            } for x in items[:101] if isinstance(x, dict)],
        }
    if name == "draw_history":
        obj = data.get("data", {})
        items = obj.get("list", []) if isinstance(obj, dict) else []
        return {"rounds": [{
            "issueNumber": str(x.get("issueNumber", "")),
            "premium": str(x.get("premium", "")),
            "number": str(x.get("number", "")),
        } for x in items[:100] if isinstance(x, dict)]}
    if name == "draw_schedule":
        candidate = data.get("data") if isinstance(data.get("data"), dict) else data
        return {k: candidate.get(k) for k in ("previous", "current", "next")}
    return {}


def fetch(session, name, date_str):
    started = now_utc()
    t0 = time.monotonic()
    record = {"source": name, "request_started_utc": started}
    try:
        if name == "platsaas":
            response = session.post(
                ENDPOINTS[name],
                params={"_t": int(time.time() * 1000)},
                json={"PageSize": 101, "PageIndex": 1, "TypeId": 30, "Time": date_str},
                headers={"Accept": "application/json"},
                timeout=20,
            )
        elif name == "draw_history":
            response = session.get(
                ENDPOINTS[name],
                params={"pageNo": 1, "pageSize": 100},
                headers={"Accept": "application/json"},
                timeout=20,
            )
        else:
            response = session.get(
                ENDPOINTS[name], headers={"Accept": "application/json"}, timeout=20,
            )
        record.update({
            "request_finished_utc": now_utc(),
            "duration_ms": round((time.monotonic() - t0) * 1000),
            "url": response.url,
            "status_code": response.status_code,
            "response_headers": {k: response.headers.get(k) for k in SAFE_HEADERS if response.headers.get(k) is not None},
        })
        try:
            record["data"] = summarize_records(name, response.json())
        except ValueError:
            record["error"] = "Response not JSON; body intentionally not saved"
    except requests.RequestException as exc:
        record.update({
            "request_finished_utc": now_utc(),
            "duration_ms": round((time.monotonic() - t0) * 1000),
            "error": f"{type(exc).__name__}: {exc}",
        })
    return record


def check_matching(platsaas, history):
    p = platsaas.get("data", {}).get("rounds", [])
    h = history.get("data", {}).get("rounds", [])
    history_by_id = {x["issueNumber"]: x for x in h if x.get("issueNumber")}
    comparisons = []
    for x in p:
        if str(x.get("state")) != "1" or not x.get("issueNumber"):
            continue
        y = history_by_id.get(x["issueNumber"])
        if y is None:
            continue
        premium = x.get("premium", "")
        comparisons.append({
            "issueNumber": x["issueNumber"],
            "platsaas_premium": premium,
            "platsaas_number": x.get("number"),
            "draw_number": y.get("number"),
            "numbers_match": x.get("number") == y.get("number"),
            "premium_last_digit_matches": bool(premium) and premium[-1] == x.get("number"),
        })
    return comparisons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=1, help="Number of observation cycles (default 1)")
    parser.add_argument("--interval", type=int, default=30, help="Seconds between cycles, minimum 30")
    parser.add_argument("--date", help="Platsaas Time field (YYYY-MM-DD), default current IST day")
    args = parser.parse_args()
    if args.samples < 1 or args.samples > 200:
        parser.error("--samples must be 1..200")
    if args.interval < 30:
        parser.error("--interval must be at least 30 seconds")
    day = args.date or datetime.now(IST).strftime("%Y-%m-%d")
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        parser.error("--date must be YYYY-MM-DD")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        for i in range(args.samples):
            capture = {
                "captured_at_utc": now_utc(),
                "date_requested": day,
                "responses": [fetch(session, name, day) for name in ENDPOINTS],
            }
            by_name = {x["source"]: x for x in capture["responses"]}
            comparisons = check_matching(by_name["platsaas"], by_name["draw_history"])
            capture["matched_rounds"] = comparisons
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(capture, ensure_ascii=False, separators=(",", ":")) + "\n")

            print(f"\nCapture {i + 1}/{args.samples} | {capture['captured_at_utc']}")
            for response in capture["responses"]:
                headers = response.get("response_headers", {})
                status = response.get("status_code", response.get("error", "error"))
                print(f"  {response['source']}: HTTP {status}, cf-ray={headers.get('cf-ray', '-')}, "
                      f"x-oss-request-id={headers.get('x-oss-request-id', '-')}, "
                      f"etag={headers.get('etag', '-')}")
            print(f"  Correlated completed rounds: {len(comparisons)}")
            for row in comparisons[:5]:
                print(f"    {row['issueNumber']} premium={row['platsaas_premium']} "
                      f"number={row['platsaas_number']} draw={row['draw_number']} "
                      f"match={row['numbers_match']}")
            print(f"  Saved: {OUT}")
            if i < args.samples - 1:
                time.sleep(args.interval)


if __name__ == "__main__":
    import os as _publication_os
    if _publication_os.environ.get("WINGO_ENABLE_NETWORK") != "1":
        raise SystemExit("Archived collector. Set WINGO_ENABLE_NETWORK=1 only for explicitly authorized collection; not used by the audit suite.")
    main()
