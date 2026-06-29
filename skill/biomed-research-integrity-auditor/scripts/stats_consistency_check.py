#!/usr/bin/env python3
"""Check biomedical source-data summaries for simple consistency issues."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


CSV_EXTS = {".csv", ".tsv"}
NUMERIC_HINTS = ("mean", "sd", "sem", "se", "n", "p", "p_value", "pvalue")


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"na", "n/a", "nan", "null", "-"}:
        return None
    if text.startswith("<"):
        text = text[1:]
    try:
        return float(text)
    except ValueError:
        return None


def normalize_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_").replace("-", "_")


def read_table(path: Path) -> list[dict[str, str]]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        rows = []
        for row in reader:
            rows.append({normalize_header(k): v for k, v in row.items() if k is not None})
        return rows


def row_label(path: Path, idx: int, row: dict[str, str]) -> str:
    for key in ("id", "group", "condition", "figure", "panel", "comparison"):
        if row.get(key):
            return f"{path.name}:row{idx}:{key}={row[key]}"
    return f"{path.name}:row{idx}"


def check_rows(path: Path, rows: list[dict[str, str]], sem_tolerance: float) -> list[dict[str, Any]]:
    findings = []
    for idx, row in enumerate(rows, start=2):
        mean = parse_float(row.get("mean"))
        sd = parse_float(row.get("sd"))
        sem = parse_float(row.get("sem") or row.get("se"))
        n = parse_float(row.get("n"))
        p_value = parse_float(row.get("p") or row.get("p_value") or row.get("pvalue"))
        label = row_label(path, idx, row)

        if n is not None and (n <= 0 or abs(n - round(n)) > 1e-9):
            findings.append(issue(label, "R2", "n is non-positive or non-integer", {"n": n}))

        if sd is not None and sd < 0:
            findings.append(issue(label, "R3", "SD is negative", {"sd": sd}))
        if sem is not None and sem < 0:
            findings.append(issue(label, "R3", "SEM is negative", {"sem": sem}))

        if sd is not None and sem is not None and n is not None and n > 1:
            expected_sd = sem * math.sqrt(n)
            tolerance = max(sem_tolerance, abs(expected_sd) * sem_tolerance)
            if abs(sd - expected_sd) > tolerance:
                findings.append(issue(label, "R2", "SD is not consistent with SEM * sqrt(n)", {
                    "sd": sd,
                    "sem": sem,
                    "n": n,
                    "expected_sd_from_sem": expected_sd,
                }))
            if abs(sd - sem) <= tolerance and n > 2:
                findings.append(issue(label, "R2", "SD and SEM are nearly identical despite n > 2", {
                    "sd": sd,
                    "sem": sem,
                    "n": n,
                }))

        if p_value is not None and not (0 <= p_value <= 1):
            findings.append(issue(label, "R3", "p value is outside [0, 1]", {"p_value": p_value}))

        if mean is not None and sd is not None and abs(mean) > 0 and sd / abs(mean) < 1e-6:
            findings.append(issue(label, "R1", "Extremely small relative SD; weak triage signal", {
                "mean": mean,
                "sd": sd,
            }))
    return findings


def issue(location: str, risk_level: str, message: str, values: dict[str, Any]) -> dict[str, Any]:
    return {
        "finding_id": "",
        "risk_level": risk_level,
        "module": "Numerical and Statistical Consistency",
        "location": location,
        "finding_type": message,
        "evidence": values,
        "note": "Screening result only; inspect source data, analysis code, rounding, and benign explanations.",
    }


def collect_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() in CSV_EXTS else []
    return [p for p in sorted(path.rglob("*")) if p.is_file() and p.suffix.lower() in CSV_EXTS]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="CSV/TSV file or folder containing source-data tables")
    parser.add_argument("--sem-tolerance", type=float, default=1e-3)
    parser.add_argument("--output", type=Path, default=Path("stats_consistency_findings.json"))
    args = parser.parse_args()

    target = args.path.expanduser().resolve()
    files = collect_files(target)
    findings = []
    errors = []
    for file_path in files:
        try:
            rows = read_table(file_path)
            findings.extend(check_rows(file_path, rows, args.sem_tolerance))
        except Exception as exc:  # noqa: BLE001 - report unreadable data without aborting.
            errors.append({"path": str(file_path), "error": str(exc)})
    for idx, item in enumerate(findings, start=1):
        item["finding_id"] = f"BIOMED-STAT-{idx:04d}"
    result = {
        "path": str(target),
        "files_screened": [str(p) for p in files],
        "findings": findings,
        "errors": errors,
    }
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "files_screened": len(files),
        "findings": len(findings),
        "errors": len(errors),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
