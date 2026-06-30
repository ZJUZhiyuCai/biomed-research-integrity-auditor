#!/usr/bin/env python3
"""Compare two audit output directories for re-audit review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.submission_qc import build_re_audit_diff, write_json, write_re_audit_diff_csv  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous_output_dir", type=Path)
    parser.add_argument("current_output_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("re_audit_diff.json"))
    parser.add_argument("--csv", type=Path, default=Path("re_audit_diff.csv"))
    args = parser.parse_args()

    previous = args.previous_output_dir.expanduser().resolve()
    current = args.current_output_dir.expanduser().resolve()
    if not previous.is_dir():
        raise SystemExit(f"previous audit output directory not found: {previous}")
    if not current.is_dir():
        raise SystemExit(f"current audit output directory not found: {current}")

    diff = build_re_audit_diff(previous, current)
    write_json(args.output, diff)
    write_re_audit_diff_csv(args.csv, diff)
    print(json.dumps({
        "output": str(args.output),
        "csv": str(args.csv),
        "previous_overall_risk": diff["overall_risk"]["previous"],
        "current_overall_risk": diff["overall_risk"]["current"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
