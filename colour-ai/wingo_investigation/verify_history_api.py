import sys
import requests

CANDIDATE_URL = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"
PARAMS = {
    "pageNo": 1,
    "pageSize": 100
}
TIMEOUT_SECONDS = 10


def describe_type(value):
    return type(value).__name__


def main():
    print("=== Step 1: Testing Candidate Historical API ===")
    print(f"Target URL: {CANDIDATE_URL}")
    print(f"Query Parameters: {PARAMS}\n")

    try:
        # Make a single GET request with a strict timeout.
        # No cookies, tokens, or signatures are sent or printed.
        response = requests.get(
            CANDIDATE_URL,
            params=PARAMS,
             headers={"Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout:
        print(f"[ERROR] Request timed out after {TIMEOUT_SECONDS} seconds.")
        sys.exit(1)
    except requests.exceptions.RequestException as exc:
        print(f"[ERROR] Network or connection failure: {exc}")
        sys.exit(1)

    print(f"HTTP Status Code: {response.status_code}")
    print(f"Content-Type Header: {response.headers.get('Content-Type', 'Not provided')}")

    if response.status_code != 200:
        print("\n[WARNING] Endpoint did not return HTTP 200 OK.")
        print("First 300 characters of response body:")
        print(response.text[:300])
        sys.exit(1)

    try:
        payload = response.json()
    except ValueError:
        print("\n[ERROR] Response body is not valid JSON.")
        print("First 300 characters of response body:")
        print(response.text[:300])
        sys.exit(1)

    print("\n--- Top-Level JSON Keys and Types ---")
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k != "data":
                print(f"  {k}: ({describe_type(v)}) -> {repr(v)}")
            else:
                print(f"  {k}: ({describe_type(v)})")
    else:
        print(f"Top-level JSON is a {describe_type(payload)}, not a dict.")
        sys.exit(1)

    data = payload.get("data")
    if not isinstance(data, dict):
        print("\n[WARNING] 'data' field is missing or is not a JSON object.")
        sys.exit(1)

    print("\n--- 'data' Object Keys, Types, and Pagination Metadata ---")
    for k, v in data.items():
        if k == "list" and isinstance(v, list):
            print(f"  list: (list) -> length = {len(v)} records returned")
        else:
            print(f"  {k}: ({describe_type(v)}) -> {repr(v)}")

    records = data.get("list")
    if isinstance(records, list) and len(records) > 0:
        first_record = records[0]
        last_record = records[-1]
        print("\n--- First Record Field Names and Value Types ---")
        if isinstance(first_record, dict):
            for field_name, field_val in first_record.items():
                print(f"  {field_name}: ({describe_type(field_val)}) -> {repr(field_val)}")
            print(f"\nFirst issueNumber in page: {repr(first_record.get('issueNumber'))}")
            print(f"Last issueNumber in page:  {repr(last_record.get('issueNumber'))}")
        else:
            print(f"First item in 'list' is a {describe_type(first_record)}: {repr(first_record)}")
    else:
        print("\n[WARNING] 'data.list' is empty or not a list.")


if __name__ == "__main__":
    main()
