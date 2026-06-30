#!/usr/bin/env python3
"""Normalize a manually curated or API-authorized PubPeer case manifest.

This script intentionally does not fetch PubPeer pages or comments.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


OUTPUT_COLUMNS = [
    "case_id",
    "doi",
    "pmid",
    "pmcid",
    "pubpeer_url",
    "comment_count",
    "first_comment_date",
    "last_comment_date",
    "manual_issue_category",
    "label_strength",
    "snapshot_date",
    "notes",
]


def value(row: dict[str, str], *names: str) -> str:
    lowered = {key.strip().lower(): item for key, item in row.items()}
    for name in names:
        item = lowered.get(name.lower())
        if item:
            return item.strip()
    return ""


def normalize(input_path: Path, snapshot_date: str, case_prefix: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with input_path.open(newline="", encoding="utf-8-sig", errors="ignore") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append({
                "case_id": value(row, "case_id") or f"{case_prefix}_{len(rows) + 1:06d}",
                "doi": value(row, "doi", "DOI"),
                "pmid": value(row, "pmid", "PMID"),
                "pmcid": value(row, "pmcid", "PMCID"),
                "pubpeer_url": value(row, "pubpeer_url", "url"),
                "comment_count": value(row, "comment_count", "comments"),
                "first_comment_date": value(row, "first_comment_date"),
                "last_comment_date": value(row, "last_comment_date"),
                "manual_issue_category": value(row, "manual_issue_category", "issue_category"),
                "label_strength": value(row, "label_strength") or "weak_pubpeer_signal",
                "snapshot_date": value(row, "snapshot_date") or snapshot_date,
                "notes": value(row, "notes") or "PubPeer is used as public-concern discovery metadata only.",
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshot-date", required=True)
    parser.add_argument("--case-prefix", default="pubpeer")
    args = parser.parse_args()

    if not args.input.is_file():
        raise SystemExit(f"Input manifest not found: {args.input}")
    rows = normalize(args.input, args.snapshot_date, args.case_prefix)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} row(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
