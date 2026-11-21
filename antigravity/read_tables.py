"""List, reconstruct or verify historical table values without network access."""

import argparse
import csv
import gzip
import hashlib
import json
from functools import lru_cache
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def json_lines(name):
    with gzip.open(HERE / "tables" / name, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def normalized_row(row):
    while row and row[-1] == "":
        row.pop()
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choices = parser.add_mutually_exclusive_group(required=True)
    choices.add_argument("--list", action="store_true")
    choices.add_argument("--table", type=int, metavar="ID")
    choices.add_argument("--verify-all", action="store_true")
    parser.add_argument("--output", type=Path, help="New CSV file for --table")
    parser.add_argument("--datasets", type=Path, help="Directory with downloaded v1.0.0 CSVs")
    parser.add_argument("--workspace", type=Path, help="Extracted v1.1.0 colour-ai directory")
    args = parser.parse_args()
    tables = json_lines("table-maps.jsonl.gz")
    if args.list:
        for item in tables:
            print(f"{item['id']:3}  {len(item['rows']):6}  {item['source']}  {item['sheet']}")
        return
    if args.table is not None and (not 0 <= args.table < len(tables) or not args.output):
        parser.error("--table requires a listed table ID and --output FILE")
    names = json.loads((HERE / "tables/reference-files.json").read_text("utf-8"))
    additional_rows = json_lines("unique-rows.jsonl.gz")

    @lru_cache(maxsize=None)
    def reference_rows(file_id):
        name = names[file_id]
        if name.startswith("v1.0.0/"):
            if args.datasets is None:
                parser.error(f"Supply --datasets to resolve {name}")
            path = args.datasets / name.removeprefix("v1.0.0/")
        elif name.startswith("v1.1.0/colour-ai/"):
            if args.workspace is None:
                parser.error(f"Supply --workspace to resolve {name}")
            path = args.workspace / name.removeprefix("v1.1.0/colour-ai/")
        else:
            path = ROOT / name
        if not path.is_file():
            parser.error(f"Missing reference file: {path}")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return [normalized_row(row) for row in csv.reader(stream)]

    csv.field_size_limit(4_000_000)
    selected = tables if args.verify_all else [tables[args.table]]
    for item in selected:
        digest = hashlib.sha256()
        resolved = []
        for ref in item["rows"]:
            if isinstance(ref, int):
                row = additional_rows[ref]
            else:
                file_id, one_based_row = ref
                row = reference_rows(file_id)[one_based_row - 1]
            serialized = json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode()
            digest.update(hashlib.sha256(serialized).digest())
            if args.table is not None:
                resolved.append(row)
        if digest.hexdigest() != item["normalized_sha256"]:
            parser.exit(1, f"Checksum mismatch in table {item['id']}\n")
        if args.table is not None:
            with args.output.open("x", encoding="utf-8", newline="") as out:
                csv.writer(out).writerows(resolved)
    print(f"Verified {len(selected)} historical table(s).")


if __name__ == "__main__":
    main()
