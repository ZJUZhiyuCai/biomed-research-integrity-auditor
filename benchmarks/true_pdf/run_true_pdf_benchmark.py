#!/usr/bin/env python3
"""Run the true-PDF intake benchmark and assert machine-readable PDF text is extracted."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "tmp" / "true_pdf_benchmark")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser().resolve()
    cases_dir = output_dir / "cases"
    report_path = (args.report or (output_dir / "benchmark_report.json")).expanduser().resolve()
    run([
        PYTHON,
        "benchmarks/true_pdf/generate_true_pdf_benchmark.py",
        "--output-dir",
        str(cases_dir),
    ])

    package = cases_dir / "true_pdf_001"
    expected = load_json(package / "expected_pdf_intake.json")
    pdf_path = package / expected["pdf"]
    pdf_bytes = pdf_path.read_bytes()
    raw_markers_visible = [
        marker for marker in expected["expected_markers"]
        if marker.encode("ascii") in pdf_bytes
    ]

    detector_output = output_dir / "text_overlap_candidates.json"
    run([
        PYTHON,
        "detectors/text/text_overlap_screen.py",
        str(package),
        "--output",
        str(detector_output),
    ])
    detector = load_json(detector_output)
    pdf_errors = [
        item for item in detector.get("errors", [])
        if item.get("path") == expected["pdf"]
    ]
    pdf_candidates = [
        item for item in detector.get("candidates", [])
        if expected["pdf"] in {
            item.get("evidence", {}).get("document_a"),
            item.get("evidence", {}).get("document_b"),
        }
    ]
    recovered_markers = [
        marker for marker in expected["expected_markers"]
        if any(
            marker in candidate.get("evidence", {}).get("text_snippet_a", "")
            or marker in candidate.get("evidence", {}).get("text_snippet_b", "")
            for candidate in pdf_candidates
        )
    ]

    checks = {
        "true_pdf_header_detected": pdf_bytes.startswith(b"%PDF-"),
        "compressed_markers_not_visible_in_raw_bytes": not raw_markers_visible,
        "pdf_text_extraction_succeeded": not pdf_errors,
        "expected_markers_recovered_from_pdf_text": set(recovered_markers) == set(expected["expected_markers"]),
        "text_overlap_candidate_from_extracted_pdf": bool(pdf_candidates),
        "non_pdf_prior_text_still_screened": detector.get("paragraphs_screened", 0) >= 1,
    }
    status = "passed" if all(checks.values()) else "failed"
    report = {
        "benchmark_id": expected["benchmark_id"],
        "status": status,
        "checks": checks,
        "raw_markers_visible": raw_markers_visible,
        "recovered_markers": recovered_markers,
        "detector_output": str(detector_output),
        "expected_status": expected["expected_status"],
        "success_condition": expected["success_condition"],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
