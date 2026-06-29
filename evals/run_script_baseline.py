#!/usr/bin/env python3
"""Run the non-LLM audit pipeline baseline for one synthetic case or package."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="Case id such as case_010")
    parser.add_argument("--package", type=Path, help="Package directory; overrides --case")
    parser.add_argument("--mode", choices=["internal_presubmission", "external_public_material", "response_to_concern"], default="internal_presubmission")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    package = args.package.expanduser().resolve() if args.package else (ROOT / "evals" / "cases" / str(args.case)).resolve()
    if not package.exists():
        raise SystemExit(f"Package not found: {package}")
    output_dir = (args.output_dir or (ROOT / "evals" / "outputs" / "script_baseline" / package.name)).resolve()
    cmd = [
        PYTHON,
        "scripts/audit_package.py",
        str(package),
        "--mode",
        args.mode,
        "--output-dir",
        str(output_dir),
        "--case-id",
        package.name,
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    summary_path = output_dir / "pipeline_summary.json"
    print(json.dumps(json.loads(summary_path.read_text(encoding="utf-8")), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
