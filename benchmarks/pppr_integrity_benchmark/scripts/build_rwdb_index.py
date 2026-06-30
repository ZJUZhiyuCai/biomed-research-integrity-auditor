#!/usr/bin/env python3
"""Normalize local Crossref/Retraction Watch CSV exports into benchmark metadata.

This script does not download data. Obtain RWDB/Crossref data through permitted channels, then
point --input at the local CSV.
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
    "source_url",
    "publication_status",
    "retraction_nature",
    "retraction_reason",
    "subject",
    "journal",
    "publisher",
    "original_date",
    "status_date",
    "snapshot_date",
    "notes",
]


def first_value(row: dict[str, str], *names: str) -> str:
    normalized = {key.strip().lower(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name.lower())
        if value:
            return value.strip()
    return ""


def publication_status(nature: str) -> str:
    lower = nature.lower()
    if "retract" in lower:
        return "retracted"
    if "expression" in lower and "concern" in lower:
        return "expression_of_concern"
    if "correct" in lower or "errat" in lower or "corrig" in lower:
        return "corrected"
    if "reinstate" in lower:
        return "reinstated"
    return "publication_status_event"


def normalize_rows(inputs: list[Path], snapshot_date: str, case_prefix: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for path in inputs:
        with path.open(newline="", encoding="utf-8-sig", errors="ignore") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                doi = first_value(row, "OriginalPaperDOI", "DOI", "original_doi")
                pmid = first_value(row, "OriginalPaperPubMedID", "PMID", "PubMedID")
                key = (doi.lower(), pmid)
                if key in seen:
                    continue
                seen.add(key)
                nature = first_value(row, "RetractionNature", "UpdateType", "Nature")
                rows.append({
                    "case_id": f"{case_prefix}_{len(rows) + 1:06d}",
                    "doi": doi,
                    "pmid": pmid,
                    "pmcid": first_value(row, "PMCID", "OriginalPaperPMCID"),
                    "source_url": first_value(row, "RetractionDOI", "RetractionURL", "URL"),
                    "publication_status": publication_status(nature),
                    "retraction_nature": nature,
                    "retraction_reason": first_value(row, "Reason", "Reasons"),
                    "subject": first_value(row, "Subject"),
                    "journal": first_value(row, "Journal", "OriginalPaperJournal"),
                    "publisher": first_value(row, "Publisher"),
                    "original_date": first_value(row, "OriginalPaperDate", "OriginalDate"),
                    "status_date": first_value(row, "RetractionDate", "UpdateDate"),
                    "snapshot_date": snapshot_date,
                    "notes": "RWDB/Crossref metadata is article-level status information, not finding-level ground truth.",
                })
    return rows


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True, help="Local RWDB/Crossref CSV export.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshot-date", required=True)
    parser.add_argument("--case-prefix", default="rwdb")
    args = parser.parse_args()

    for path in args.input:
        if not path.is_file():
            raise SystemExit(f"Input CSV not found: {path}")
    rows = normalize_rows([path.expanduser().resolve() for path in args.input], args.snapshot_date, args.case_prefix)
    write_rows(args.output, rows)
    print(f"Wrote {len(rows)} row(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
