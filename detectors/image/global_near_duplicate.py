#!/usr/bin/env python3
"""Global image near-duplicate detector using multiple hashes and D4 transforms."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

from detectors.image.image_io import DEFAULT_MAX_FRAMES, normalized_frame_inventory


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
TRANSFORMS = {
    "identity": None,
    "rot90": "ROTATE_90",
    "rot180": "ROTATE_180",
    "rot270": "ROTATE_270",
    "flip_h": "FLIP_LEFT_RIGHT",
    "flip_v": "FLIP_TOP_BOTTOM",
    "transpose": "TRANSPOSE",
    "transverse": "TRANSVERSE",
}
MIN_INFORMATION_STDDEV = 1.0
MIN_INFORMATION_ENTROPY = 0.25
MIN_HASH_METHOD_AGREEMENT = 2


def hamming(left: int, right: int) -> int:
    return bin(left ^ right).count("1")


def average_hash(img: Any, hash_size: int = 8) -> int:
    small = img.convert("L").resize((hash_size, hash_size))
    pixels = list(small.tobytes())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for idx, value in enumerate(pixels):
        if value >= avg:
            bits |= 1 << idx
    return bits


def difference_hash(img: Any, hash_size: int = 8) -> int:
    small = img.convert("L").resize((hash_size + 1, hash_size))
    pixels = list(small.tobytes())
    bits = 0
    for y in range(hash_size):
        row = pixels[y * (hash_size + 1):(y + 1) * (hash_size + 1)]
        for x in range(hash_size):
            if row[x] > row[x + 1]:
                bits |= 1 << (y * hash_size + x)
    return bits


def dct_1d(values: list[float]) -> list[float]:
    n = len(values)
    result = []
    factor = math.pi / n
    for k in range(n):
        total = 0.0
        for i, value in enumerate(values):
            total += value * math.cos((i + 0.5) * k * factor)
        result.append(total)
    return result


def perceptual_hash(img: Any, hash_size: int = 8, highfreq_factor: int = 4) -> int:
    size = hash_size * highfreq_factor
    small = img.convert("L").resize((size, size))
    pixels = list(small.tobytes())
    rows = [dct_1d([float(v) for v in pixels[y * size:(y + 1) * size]]) for y in range(size)]
    coeffs = []
    for x in range(size):
        col = dct_1d([rows[y][x] for y in range(size)])
        coeffs.append(col)
    low = []
    for y in range(hash_size):
        for x in range(hash_size):
            if x == 0 and y == 0:
                continue
            low.append(coeffs[x][y])
    median = sorted(low)[len(low) // 2]
    bits = 0
    for idx, value in enumerate(low):
        if value >= median:
            bits |= 1 << idx
    return bits


def hash_bundle(img: Any, hash_size: int) -> dict[str, int]:
    return {
        "average_hash": average_hash(img, hash_size),
        "difference_hash": difference_hash(img, hash_size),
        "perceptual_hash": perceptual_hash(img, hash_size),
    }


def information_profile(img: Any) -> dict[str, Any]:
    from PIL import ImageStat

    gray = img.convert("L")
    if max(gray.size) > 512:
        gray.thumbnail((512, 512))
    stddev = float(ImageStat.Stat(gray).stddev[0])
    entropy = float(gray.entropy())
    low_information = stddev < MIN_INFORMATION_STDDEV and entropy < MIN_INFORMATION_ENTROPY
    return {
        "luminance_stddev": round(stddev, 4),
        "luminance_entropy": round(entropy, 4),
        "low_information": low_information,
    }


def transformed(img: Any, transform_name: str) -> Any:
    if transform_name == "identity":
        return img.copy()
    from PIL import Image

    transpose_name = TRANSFORMS[transform_name]
    assert transpose_name is not None
    return img.transpose(getattr(Image.Transpose, transpose_name))


def collect_images(root: Path) -> list[Path]:
    return [
        path for path in sorted(root.rglob("*"))
        if not path.is_symlink() and path.is_file() and path.suffix.lower() in IMAGE_EXTS
    ]


def connected_components(nodes: list[str], edges: list[dict[str, Any]]) -> list[list[str]]:
    adjacency: dict[str, set[str]] = {node: set() for node in nodes}
    for edge in edges:
        adjacency[edge["left"]].add(edge["right"])
        adjacency[edge["right"]].add(edge["left"])

    components: list[list[str]] = []
    seen: set[str] = set()
    for node in nodes:
        if node in seen or not adjacency[node]:
            continue
        stack = [node]
        component = []
        seen.add(node)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    return components


def cluster_candidates(edges: list[dict[str, Any]], nodes: list[str], threshold: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for component in connected_components(nodes, edges):
        component_edges = [
            edge for edge in edges
            if edge["left"] in component and edge["right"] in component
        ]
        representative = min(component_edges, key=lambda item: (item["best_hamming_distance"], item["left"], item["right"]))
        candidate_id = f"IMGCLUSTER-{len(candidates) + 1:04d}"
        candidates.append({
            "candidate_id": candidate_id,
            "detector": "image.global_near_duplicate",
            "candidate_type": "image_reuse_cluster",
            "locations": component,
            "evidence": {
                "cluster_id": candidate_id,
                "members": component,
                "edges": component_edges,
                "representative_edge": representative,
                "threshold": threshold,
            },
            "evidence_strength": "candidate",
            "risk_suggestion": "R2_or_R3_pending_context",
            "risk_cap_tags": ["image_similarity_candidate", "global_image_similarity", "image_reuse_cluster"],
            "benign_explanations": [
                "same field or membrane intentionally reused with disclosure",
                "adjacent crop or shared source image",
                "figure assembly placeholder or export artifact",
            ],
            "required_materials": [
                "original image files",
                "acquisition metadata",
                "figure assembly file",
                "sample or lane map",
            ],
            "recommended_action": "Inspect the image cluster against raw images and sample identity before risk escalation.",
            "requires_contextual_calibration": True,
        })
    return candidates


def scan(root: Path, threshold: int, hash_size: int) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit("Pillow is required: python3 -m pip install pillow") from exc

    image_paths = collect_images(root)
    images: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    frame_limits: list[dict[str, Any]] = []
    for path in image_paths:
        try:
            with Image.open(path) as img:
                rel = str(path.relative_to(root))
                frames, total_frames, frames_truncated = normalized_frame_inventory(img)
                if frames_truncated:
                    frame_limits.append({
                        "path": rel,
                        "frames_total": total_frames,
                        "frames_screened": len(frames),
                        "max_frames": DEFAULT_MAX_FRAMES,
                    })
                for frame_label, base in frames:
                    transform_hashes = {
                        name: hash_bundle(transformed(base, name), hash_size)
                        for name in TRANSFORMS
                    }
                    images.append({
                        "path": f"{rel}{frame_label}",
                        "source_file": rel,
                        "frame_label": frame_label or None,
                        "information": information_profile(base),
                        "hashes": transform_hashes,
                    })
        except Exception as exc:  # noqa: BLE001 - unreadable files should not abort an audit.
            errors.append({"path": str(path.relative_to(root)), "error": str(exc)})

    edges: list[dict[str, Any]] = []
    low_information_paths = [
        item["path"] for item in images
        if item["information"]["low_information"]
    ]
    comparisons_skipped_low_information = 0
    intra_stack_pairs_skipped = 0
    for i, left in enumerate(images):
        left_hashes = left["hashes"]["identity"]
        for right in images[i + 1:]:
            if left["source_file"] == right["source_file"]:
                intra_stack_pairs_skipped += 1
                continue
            if left["information"]["low_information"] or right["information"]["low_information"]:
                comparisons_skipped_low_information += 1
                continue
            best: dict[str, Any] | None = None
            for transform_name, right_hashes in right["hashes"].items():
                distances = {
                    method: hamming(left_hashes[method], right_hashes[method])
                    for method in left_hashes
                }
                min_method = min(distances, key=lambda method: distances[method])
                score = distances[min_method]
                methods_within_threshold = sorted(
                    method for method, distance in distances.items()
                    if distance <= threshold
                )
                agreement = len(methods_within_threshold)
                if best is None or (agreement, -score) > (best["agreement"], -best["distance"]):
                    best = {
                        "transform": transform_name,
                        "method": min_method,
                        "distance": score,
                        "distances": distances,
                        "agreement": agreement,
                        "methods_within_threshold": methods_within_threshold,
                    }
            if best and best["distance"] <= threshold and best["agreement"] >= MIN_HASH_METHOD_AGREEMENT:
                edges.append({
                    "left": left["path"],
                    "right": right["path"],
                    "best_transform": best["transform"],
                    "best_hash_method": best["method"],
                    "best_hamming_distance": best["distance"],
                    "all_method_distances": best["distances"],
                    "hash_methods_within_threshold": best["methods_within_threshold"],
                })
    candidates = cluster_candidates(edges, [item["path"] for item in images], threshold)
    for record in frame_limits:
        candidates.append({
            "candidate_id": f"IMG-FRAME-LIMIT-{len(candidates) + 1:04d}",
            "detector": "image.global_near_duplicate",
            "candidate_type": "audit_coverage_gap",
            "locations": [record["path"]],
            "finding_type": "multi-frame image screening limit reached",
            "evidence": {
                **record,
                "message": "Only the first configured frames were screened; later frames remain outside automated image coverage.",
            },
            "evidence_strength": "weak_signal",
            "risk_suggestion": "R1_max",
            "risk_cap_tags": ["audit_coverage_gap", "completeness_gap"],
            "benign_explanations": ["The file may be a routine Z-stack, time series, or multi-page acquisition."],
            "required_materials": ["focused frame-range review or an increased frame screening budget"],
            "recommended_action": "Run a focused review of the unscreened frames before treating the stack as fully screened.",
            "requires_contextual_calibration": True,
        })

    return {
        "detector_name": "image.global_near_duplicate",
        "detector_version": "0.5.0",
        "input": {
            "root": str(root),
            "hash_size": hash_size,
            "threshold": threshold,
            "transforms": list(TRANSFORMS),
            "hash_methods": ["average_hash", "difference_hash", "perceptual_hash"],
            "minimum_hash_method_agreement": MIN_HASH_METHOD_AGREEMENT,
            "low_information_gate": {
                "minimum_luminance_stddev": MIN_INFORMATION_STDDEV,
                "minimum_luminance_entropy": MIN_INFORMATION_ENTROPY,
                "rule": "excluded only when both metrics are below threshold",
            },
            "multi_frame_images": "screened_as_frame_level_items",
            "max_frames_per_file": DEFAULT_MAX_FRAMES,
        },
        "images_screened": len(images),
        "low_information_images_excluded": low_information_paths,
        "low_information_image_count": len(low_information_paths),
        "pairwise_comparisons_skipped_low_information": comparisons_skipped_low_information,
        "intra_stack_pairs_skipped": intra_stack_pairs_skipped,
        "frame_screening_limits": frame_limits,
        "pairwise_edges": len(edges),
        "candidates": candidates,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_dir", type=Path)
    parser.add_argument("--threshold", type=int, default=6)
    parser.add_argument("--hash-size", type=int, default=8)
    parser.add_argument("--output", type=Path, default=Path("global_image_candidates.json"))
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
