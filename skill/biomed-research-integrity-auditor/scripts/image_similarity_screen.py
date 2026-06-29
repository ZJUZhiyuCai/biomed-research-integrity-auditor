#!/usr/bin/env python3
"""Deprecated wrapper for the global image near-duplicate detector."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_dir", type=Path)
    parser.add_argument("--threshold", type=int, default=6, help="Maximum Hamming distance for candidate edges")
    parser.add_argument("--hash-size", type=int, default=8)
    parser.add_argument("--output", type=Path, default=Path("image_similarity_candidates.json"))
    args = parser.parse_args()

    print(
        "DEPRECATED: use scripts/audit_package.py or detectors/image/global_near_duplicate.py; "
        "delegating to the global near-duplicate detector.",
        file=sys.stderr,
    )
    cmd = [
        sys.executable,
        str(ROOT / "detectors" / "image" / "global_near_duplicate.py"),
        str(args.image_dir),
        "--threshold",
        str(args.threshold),
        "--hash-size",
        str(args.hash_size),
        "--output",
        str(args.output),
    ]
    completed = subprocess.run(cmd, cwd=ROOT, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
