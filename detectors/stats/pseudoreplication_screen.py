#!/usr/bin/env python3
"""Screen source-data tables for possible unit-of-analysis mismatches."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


CSV_EXTS = {".csv", ".tsv"}
BIOLOGICAL_ID_COLUMNS = ("animal_id", "mouse_id", "rat_id", "subject_id", "patient_id", "donor_id")
TECHNICAL_ID_COLUMNS = ("field_id", "section_id", "well_id", "technical_replicate", "cell_id", "lesion_id", "image_id")


def normalize_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_").replace("-", "_")


def read_table(path: Path) -> list[dict[str, str]]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        return [{normalize_header(k): v for k, v in row.items() if k is not None} for row in reader]


def collect_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() in CSV_EXTS else []
    return [p for p in sorted(path.rglob("*")) if p.is_file() and p.suffix.lower() in CSV_EXTS]


def present_column(rows: list[dict[str, str]], candidates: tuple[str, ...]) -> str | None:
    if not rows:
        return None
    columns = set(rows[0])
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def group_column(rows: list[dict[str, str]]) -> str | None:
    for candidate in ("group", "condition", "treatment", "arm"):
        if rows and candidate in rows[0]:
            return candidate
    return None


def screen_table(path: Path, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    biological = present_column(rows, BIOLOGICAL_ID_COLUMNS)
    technical = present_column(rows, TECHNICAL_ID_COLUMNS)
    if not biological or not technical:
        return []

    group_col = group_column(rows)
    buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = row.get(group_col, "all") if group_col else "all"
        buckets[key].append(row)

    candidates = []
    for group, group_rows in buckets.items():
        biological_units = {row.get(biological, "") for row in group_rows if row.get(biological, "")}
        technical_units = {(row.get(biological, ""), row.get(technical, "")) for row in group_rows if row.get(technical, "")}
        if len(biological_units) >= 1 and len(technical_units) > len(biological_units):
            reported_n_basis_values = {row.get("reported_n_basis", "").lower() for row in group_rows}
            reported_technical = any(value in {"field", "fields", "well", "wells", "technical", "cell", "cells"} for value in reported_n_basis_values)
            candidate_id = f"STAT-PSEUDO-{len(candidates) + 1:04d}"
            candidates.append({
                "candidate_id": candidate_id,
                "detector": "stats.pseudoreplication_screen",
                "candidate_type": "pseudoreplication_candidate",
                "locations": [f"{path.name}:group={group}"],
                "evidence": {
                    "file": str(path),
                    "group": group,
                    "biological_id_column": biological,
                    "technical_id_column": technical,
                    "biological_unit_count": len(biological_units),
                    "technical_unit_count": len(technical_units),
                    "row_count": len(group_rows),
                    "reported_n_basis_values": sorted(v for v in reported_n_basis_values if v),
                    "reported_n_appears_technical": reported_technical,
                },
                "evidence_strength": "candidate",
                "risk_suggestion": "R2_or_R3_depending_on_claim_centrality",
                "risk_cap_tags": ["pseudoreplication_candidate"],
                "benign_explanations": [
                    "analysis may use a nested or mixed-effects model",
                    "technical replicates may have been averaged before inferential testing",
                    "reported n may be descriptive rather than inferential",
                ],
                "required_materials": [
                    "analysis code",
                    "statistical model specification",
                    "raw measurements by biological unit",
                    "reported n definition from methods or legend",
                ],
                "recommended_action": "Verify whether inferential n counts biological units; reanalyse at the biological-unit level or justify a nested model.",
                "requires_contextual_calibration": True,
            })
    return candidates


def scan(root: Path) -> dict[str, Any]:
    files = collect_files(root)
    candidates = []
    errors = []
    for file_path in files:
        try:
            candidates.extend(screen_table(file_path, read_table(file_path)))
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(file_path), "error": str(exc)})
    for idx, candidate in enumerate(candidates, start=1):
        candidate["candidate_id"] = f"STAT-PSEUDO-{idx:04d}"
    return {
        "detector_name": "stats.pseudoreplication_screen",
        "detector_version": "0.2.0",
        "input": {"root": str(root)},
        "candidates": candidates,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("pseudoreplication_candidates.json"))
    args = parser.parse_args()

    root = args.path.expanduser().resolve()
    result = scan(root)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "candidates": len(result["candidates"]),
        "errors": len(result["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
