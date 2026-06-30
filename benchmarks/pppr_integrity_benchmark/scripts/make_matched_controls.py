#!/usr/bin/env python3
"""Build matched-control metadata from local article manifests.

Controls are "no known public concern at snapshot date", never "clean papers".
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
    "source",
    "source_url",
    "public_concern",
    "retracted",
    "correction",
    "expression_of_concern",
    "reinstated",
    "available_in_pmc_oa",
    "license",
    "known_public_concern_at_snapshot",
    "snapshot_date",
    "notes",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig", errors="ignore") as handle:
        return list(csv.DictReader(handle))


def identifier_set(rows: list[dict[str, str]]) -> set[str]:
    ids = set()
    for row in rows:
        for key in ("doi", "pmid", "pmcid"):
            value = str(row.get(key, "") or "").strip().lower()
            if value:
                ids.add(f"{key}:{value}")
    return ids


def row_has_public_concern(row: dict[str, str], excluded_ids: set[str]) -> bool:
    for key in ("doi", "pmid", "pmcid"):
        value = str(row.get(key, "") or "").strip().lower()
        if value and f"{key}:{value}" in excluded_ids:
            return True
    return False


def make_controls(article_rows: list[dict[str, str]], excluded_ids: set[str], snapshot_date: str, limit: int | None) -> list[dict[str, str]]:
    controls = []
    for row in article_rows:
        if row_has_public_concern(row, excluded_ids):
            continue
        controls.append({
            "case_id": row.get("case_id") or f"control_{len(controls) + 1:06d}",
            "doi": row.get("doi", ""),
            "pmid": row.get("pmid", ""),
            "pmcid": row.get("pmcid", ""),
            "source": row.get("source", "pmc_oa_candidate"),
            "source_url": row.get("source_url", row.get("pmc_oa_url", "")),
            "public_concern": "0",
            "retracted": "0",
            "correction": "0",
            "expression_of_concern": "0",
            "reinstated": "0",
            "available_in_pmc_oa": row.get("available_in_pmc_oa", "1" if row.get("pmcid") else "0"),
            "license": row.get("license", ""),
            "known_public_concern_at_snapshot": "false",
            "snapshot_date": snapshot_date,
            "notes": "Matched comparison case: no known PubPeer/RWDB signal at snapshot date; not a clean-paper label.",
        })
        if limit is not None and len(controls) >= limit:
            break
    return controls


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, required=True, help="Candidate article manifest CSV.")
    parser.add_argument("--exclude", type=Path, action="append", default=[], help="Concern/status manifest CSV to exclude.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshot-date", required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    article_rows = read_csv(args.articles)
    excluded: set[str] = set()
    for path in args.exclude:
        excluded.update(identifier_set(read_csv(path)))
    controls = make_controls(article_rows, excluded, args.snapshot_date, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(controls)
    print(f"Wrote {len(controls)} matched-control row(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
