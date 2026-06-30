#!/usr/bin/env python3
"""Run the auditor over a directory of benchmark packages."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PYTHON = sys.executable


def selected_cases(packages_dir: Path, split: Path | None) -> list[Path]:
    if split is None:
        return [path for path in sorted(packages_dir.iterdir()) if path.is_dir()]
    wanted = {
        line.strip()
        for line in split.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    return [packages_dir / case_id for case_id in sorted(wanted) if (packages_dir / case_id).is_dir()]


def run_case(package: Path, output_dir: Path, mode: str) -> dict[str, object]:
    case_output = output_dir / package.name
    cmd = [
        PYTHON,
        "scripts/audit_package.py",
        str(package),
        "--mode",
        mode,
        "--case-id",
        package.name,
        "--output-dir",
        str(case_output),
        "--external-literature-provider",
        "none",
    ]
    started = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    elapsed = time.time() - started
    summary_path = case_output / "AUDIT_JSON_SUMMARY.json"
    pipeline_path = case_output / "pipeline_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    return {
        "case_id": package.name,
        "package": str(package),
        "output_dir": str(case_output),
        "returncode": proc.returncode,
        "elapsed_seconds": round(elapsed, 3),
        "overall_risk": summary.get("overall_risk"),
        "finding_count": len(summary.get("findings", []) or []),
        "pipeline_summary": str(pipeline_path) if pipeline_path.is_file() else "",
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--split", type=Path)
    parser.add_argument("--mode", default="external_public_material", choices=[
        "internal_presubmission",
        "external_public_material",
        "response_to_concern",
    ])
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    packages = selected_cases(args.packages_dir.expanduser().resolve(), args.split.expanduser().resolve() if args.split else None)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = [run_case(package, args.output_dir, args.mode) for package in packages]
    payload = {"case_count": len(results), "results": results}
    summary = args.summary or (args.output_dir / "benchmark_run_summary.json")
    summary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"summary": str(summary), "case_count": len(results)}, indent=2))
    return 0 if all(item["returncode"] == 0 for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
