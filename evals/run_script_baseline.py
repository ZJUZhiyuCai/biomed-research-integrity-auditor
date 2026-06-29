#!/usr/bin/env python3
"""Run the non-LLM detector baseline for one synthetic case or package."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def has_files(path: Path, suffixes: set[str]) -> bool:
    return any(p.is_file() and p.suffix.lower() in suffixes for p in path.rglob("*"))


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
    output_dir.mkdir(parents=True, exist_ok=True)

    detector_outputs: list[Path] = []
    source_dir = package / "source_data"
    if source_dir.exists():
        stats_output = output_dir / "stats_consistency_findings.json"
        run([PYTHON, "skill/biomed-research-integrity-auditor/scripts/stats_consistency_check.py", str(source_dir), "--output", str(stats_output)])
        detector_outputs.append(stats_output)

        pseudo_output = output_dir / "pseudoreplication_candidates.json"
        run([PYTHON, "detectors/stats/pseudoreplication_screen.py", str(source_dir), "--output", str(pseudo_output)])
        detector_outputs.append(pseudo_output)

    if has_files(package, {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}):
        image_output = output_dir / "global_image_candidates.json"
        run([PYTHON, "detectors/image/global_near_duplicate.py", str(package), "--output", str(image_output)])
        detector_outputs.append(image_output)

    calibrated_output = output_dir / "calibrated_findings.json"
    if detector_outputs:
        cmd = [PYTHON, "calibrators/risk_cap_engine.py", "--mode", args.mode, "--output", str(calibrated_output)]
        for path in detector_outputs:
            cmd.extend(["--input", str(path)])
        run(cmd)

    summary = {
        "package": str(package),
        "mode": args.mode,
        "output_dir": str(output_dir),
        "detector_outputs": [str(path) for path in detector_outputs],
        "calibrated_findings": str(calibrated_output) if calibrated_output.exists() else None,
    }
    (output_dir / "baseline_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
