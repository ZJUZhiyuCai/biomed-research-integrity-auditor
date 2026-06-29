#!/usr/bin/env python3
"""Run the scanned-PDF OCR benchmark."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ocr_runtime_available() -> bool:
    return (
        shutil.which("tesseract") is not None
        and importlib.util.find_spec("fitz") is not None
        and importlib.util.find_spec("pytesseract") is not None
    )


def token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def marker_recovered(marker: str, candidates: list[dict]) -> bool:
    marker_tokens = token_set(marker)
    if not marker_tokens:
        return False
    for candidate in candidates:
        snippet = (
            candidate.get("evidence", {}).get("text_snippet_a", "")
            + " "
            + candidate.get("evidence", {}).get("text_snippet_b", "")
        )
        recovered = token_set(snippet)
        if len(marker_tokens & recovered) / len(marker_tokens) >= 0.82:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "tmp" / "scanned_pdf_benchmark")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--skip-if-unavailable", action="store_true")
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser().resolve()
    report_path = (args.report or (output_dir / "benchmark_report.json")).expanduser().resolve()
    if not ocr_runtime_available():
        report = {
            "benchmark_id": "scanned_pdf_001",
            "status": "skipped_ocr_runtime_unavailable",
            "checks": {
                "tesseract_binary_available": shutil.which("tesseract") is not None,
                "pymupdf_available": importlib.util.find_spec("fitz") is not None,
                "pytesseract_available": importlib.util.find_spec("pytesseract") is not None,
            },
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if args.skip_if_unavailable else 1

    cases_dir = output_dir / "cases"
    run([
        PYTHON,
        "benchmarks/scanned_pdf/generate_scanned_pdf_benchmark.py",
        "--output-dir",
        str(cases_dir),
    ])

    package = cases_dir / "scanned_pdf_001"
    expected = load_json(package / "expected_ocr_intake.json")
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
        if marker_recovered(marker, pdf_candidates)
    ]

    checks = {
        "scanned_pdf_header_detected": pdf_bytes.startswith(b"%PDF-"),
        "markers_not_visible_in_raw_bytes": not raw_markers_visible,
        "ocr_text_extraction_succeeded": not pdf_errors,
        "expected_markers_recovered_from_ocr_text": set(recovered_markers) == set(expected["expected_markers"]),
        "text_overlap_candidate_from_ocr_pdf": bool(pdf_candidates),
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
