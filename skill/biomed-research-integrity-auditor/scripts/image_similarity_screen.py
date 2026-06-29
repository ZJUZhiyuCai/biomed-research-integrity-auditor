#!/usr/bin/env python3
"""Screen images for perceptual-hash similarity candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def average_hash(path: Path, hash_size: int = 8) -> int:
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit("Pillow is required: python3 -m pip install pillow") from exc

    with Image.open(path) as img:
        img = img.convert("L").resize((hash_size, hash_size))
        pixels = list(img.tobytes())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for idx, value in enumerate(pixels):
        if value >= avg:
            bits |= 1 << idx
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def scan(root: Path, threshold: int, hash_size: int) -> dict[str, Any]:
    images = [p for p in sorted(root.rglob("*")) if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    hashes = []
    errors = []
    for path in images:
        try:
            hashes.append({"path": str(path.relative_to(root)), "hash": average_hash(path, hash_size)})
        except Exception as exc:  # noqa: BLE001 - record unreadable files without aborting the audit.
            errors.append({"path": str(path.relative_to(root)), "error": str(exc)})

    candidates = []
    for i, left in enumerate(hashes):
        for right in hashes[i + 1:]:
            distance = hamming(left["hash"], right["hash"])
            if distance <= threshold:
                candidates.append({
                    "left": left["path"],
                    "right": right["path"],
                    "hamming_distance": distance,
                    "candidate_type": "image_similarity_candidate",
                    "evidence_strength": "candidate",
                    "risk_suggestion": "R2_or_R3_pending_context",
                    "requires_contextual_calibration": True,
                    "note": "Perceptual-hash candidate only; inspect source images and benign explanations. Detector output is not a final risk level.",
                })
    return {
        "root": str(root),
        "hash_size": hash_size,
        "threshold": threshold,
        "images_screened": len(hashes),
        "candidates": candidates,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_dir", type=Path)
    parser.add_argument("--threshold", type=int, default=6, help="Maximum Hamming distance for candidate pairs")
    parser.add_argument("--hash-size", type=int, default=8)
    parser.add_argument("--output", type=Path, default=Path("image_similarity_candidates.json"))
    args = parser.parse_args()
    root = args.image_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Image directory not found: {root}")
    result = scan(root, args.threshold, args.hash_size)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "images_screened": result["images_screened"],
        "candidates": len(result["candidates"]),
        "errors": len(result["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
