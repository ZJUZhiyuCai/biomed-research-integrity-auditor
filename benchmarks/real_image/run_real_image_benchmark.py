#!/usr/bin/env python3
"""Run the real-microscopy-image benchmark."""

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
    parser.add_argument("--output-dir", type=Path, default=ROOT / "tmp" / "real_image_benchmark")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser().resolve()
    cases_dir = output_dir / "cases"
    report_path = (args.report or (output_dir / "benchmark_report.json")).expanduser().resolve()
    run([
        PYTHON,
        "benchmarks/real_image/generate_real_image_benchmark.py",
        "--output-dir",
        str(cases_dir),
    ])

    package = cases_dir / "real_image_001"
    expected = load_json(package / "expected_real_image_intake.json")
    detector_output = output_dir / "global_image_candidates.json"
    run([
        PYTHON,
        "detectors/image/global_near_duplicate.py",
        str(package),
        "--output",
        str(detector_output),
    ])
    detector = load_json(detector_output)
    pair = set(expected["expected_duplicate_pair"])
    bit16_pair = set(expected["expected_16bit_pair"])
    matched_edges = [
        edge
        for candidate in detector.get("candidates", [])
        for edge in candidate.get("evidence", {}).get("edges", [])
        if {edge.get("left"), edge.get("right")} == pair
    ]
    matched_16bit_edges = [
        edge
        for candidate in detector.get("candidates", [])
        for edge in candidate.get("evidence", {}).get("edges", [])
        if {edge.get("left"), edge.get("right")} == bit16_pair
    ]
    checks = {
        "source_asset_present": (ROOT / expected["source_asset"]).exists(),
        "images_screened": detector.get("images_screened", 0) >= 5,
        "expected_pair_detected": bool(matched_edges),
        "expected_transform_detected": any(edge.get("best_transform") == expected["expected_transform"] for edge in matched_edges),
        "expected_16bit_pair_detected": bool(matched_16bit_edges),
        "expected_16bit_transform_detected": any(edge.get("best_transform") == expected["expected_transform"] for edge in matched_16bit_edges),
        "no_detector_errors": not detector.get("errors"),
    }
    status = "passed" if all(checks.values()) else "failed"
    report = {
        "benchmark_id": expected["benchmark_id"],
        "status": status,
        "checks": checks,
        "matched_edges": matched_edges,
        "matched_16bit_edges": matched_16bit_edges,
        "detector_output": str(detector_output),
        "source_metadata": expected["source_metadata"],
        "expected_status": expected["expected_status"],
        "success_condition": expected["success_condition"],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
