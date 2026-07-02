#!/usr/bin/env python3
"""Keypoint-based geometric image similarity detector using OpenCV ORB."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from detectors.image.image_io import iter_normalized_frames
from provenance.panel_modality import resolve_panel_modality_routing


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
DEFAULT_MAX_DIMENSION = 1024
DEFAULT_MAX_FEATURES = 2500
DEFAULT_RATIO_THRESHOLD = 0.75
DEFAULT_MIN_GOOD_MATCHES = 30
DEFAULT_MIN_INLIERS = 24
DEFAULT_MIN_INLIER_RATIO = 0.25
DEFAULT_RANSAC_REPROJECTION_THRESHOLD = 5.0
DEFAULT_MAX_PAIR_COMPARISONS = 2500
DEFAULT_MIN_ROTATION_DEGREES = 3.0
DEFAULT_MIN_SCALE_DELTA = 0.12
DEFAULT_MIN_PERSPECTIVE_SCORE = 0.0015


def collect_images(root: Path) -> list[Path]:
    return [path for path in sorted(root.rglob("*")) if path.is_file() and path.suffix.lower() in IMAGE_EXTS]


def display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def load_provenance(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"nodes": [], "edges": []}
    return json.loads(path.read_text(encoding="utf-8"))


def resized_gray_array(img: Any, max_dimension: int) -> tuple[np.ndarray, float]:
    gray = np.asarray(img.convert("L"), dtype=np.uint8)
    height, width = gray.shape[:2]
    largest = max(width, height)
    if max_dimension <= 0 or largest <= max_dimension:
        return gray, 1.0
    scale = max_dimension / largest
    resized = cv2.resize(
        gray,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def detect_features(gray: np.ndarray, orb: cv2.ORB) -> tuple[list[Any], np.ndarray | None]:
    keypoints, descriptors = orb.detectAndCompute(gray, None)
    return list(keypoints or []), descriptors


def round_float(value: float, digits: int = 6) -> float:
    if not math.isfinite(float(value)):
        return 0.0
    return round(float(value), digits)


def normalize_homography(homography: np.ndarray) -> np.ndarray:
    if homography.shape != (3, 3):
        return homography
    denom = homography[2, 2]
    if denom and math.isfinite(float(denom)):
        return homography / denom
    return homography


def homography_payload(homography: np.ndarray) -> list[list[float]]:
    normalized = normalize_homography(homography)
    return [[round_float(value) for value in row] for row in normalized.tolist()]


def estimate_transform(homography: np.ndarray) -> dict[str, Any]:
    h = normalize_homography(homography)
    a = float(h[0, 0])
    b = float(h[0, 1])
    c = float(h[1, 0])
    d = float(h[1, 1])
    scale_x = math.sqrt(a * a + c * c)
    scale_y = math.sqrt(b * b + d * d)
    rotation = math.degrees(math.atan2(c, a)) if scale_x else 0.0
    return {
        "rotation_degrees": round_float(rotation, 3),
        "scale_x": round_float(scale_x, 4),
        "scale_y": round_float(scale_y, 4),
        "scale_estimate": round_float((scale_x + scale_y) / 2.0, 4),
        "translation_x": round_float(float(h[0, 2]), 3),
        "translation_y": round_float(float(h[1, 2]), 3),
        "perspective_score": round_float(math.sqrt(float(h[2, 0]) ** 2 + float(h[2, 1]) ** 2), 8),
    }


def has_nontrivial_geometric_change(
    transform: dict[str, Any],
    min_rotation_degrees: float,
    min_scale_delta: float,
    min_perspective_score: float,
) -> bool:
    if abs(float(transform.get("rotation_degrees", 0.0))) >= min_rotation_degrees:
        return True
    if abs(float(transform.get("scale_estimate", 1.0)) - 1.0) >= min_scale_delta:
        return True
    if float(transform.get("perspective_score", 0.0)) >= min_perspective_score:
        return True
    return False


def projected_corners(width: int, height: int, homography: np.ndarray) -> list[dict[str, float]]:
    corners = np.float32([[0, 0], [width, 0], [width, height], [0, height]]).reshape(-1, 1, 2)
    try:
        projected = cv2.perspectiveTransform(corners, normalize_homography(homography)).reshape(-1, 2)
    except Exception:  # noqa: BLE001 - corner projection is descriptive evidence only.
        return []
    return [{"x": round_float(x, 2), "y": round_float(y, 2)} for x, y in projected.tolist()]


def comparison_limit_candidate(records: list[dict[str, Any]], idx: int) -> dict[str, Any]:
    return {
        "candidate_id": f"KEYPOINT-COVERAGE-GAP-{idx:04d}",
        "detector": "image.keypoint_geometric_match",
        "candidate_type": "audit_coverage_gap",
        "locations": ["image.keypoint_geometric_match"],
        "evidence": {
            "message": "Keypoint geometric image screening was partially limited by the pair-comparison budget.",
            "records": records,
        },
        "evidence_strength": "weak_signal",
        "risk_suggestion": "R1_possible",
        "risk_cap_tags": ["audit_coverage_gap", "completeness_gap"],
        "benign_explanations": [
            "large image packages may need a focused deep scan on selected panels",
            "runtime limits prevent the keypoint detector from examining every image pair in this run",
        ],
        "required_materials": [
            "targeted deep scan for high-priority panels",
            "raw images and figure assembly files for unscreened or partially screened panels",
        ],
        "recommended_action": (
            "Run a focused deep scan or increase the keypoint pair-comparison budget before treating "
            "geometric image screening as complete."
        ),
        "requires_contextual_calibration": True,
    }


def keypoint_candidate(
    left: dict[str, Any],
    right: dict[str, Any],
    good_matches: list[Any],
    inlier_count: int,
    inlier_ratio: float,
    homography: np.ndarray,
    idx: int,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    candidate_id = f"KEYPOINT-{idx:04d}"
    transform = estimate_transform(homography)
    edge = {
        "left": left["path"],
        "right": right["path"],
        "similarity_scope": "keypoint_geometric",
        "same_image": False,
        "method": "ORB keypoint matching with RANSAC homography",
        "best_transform": "homography_ransac",
        "keypoints_left": len(left["keypoints"]),
        "keypoints_right": len(right["keypoints"]),
        "good_matches": len(good_matches),
        "inlier_count": inlier_count,
        "inlier_ratio": round_float(inlier_ratio, 4),
        "rotation_degrees": transform["rotation_degrees"],
        "scale_estimate": transform["scale_estimate"],
        "perspective_score": transform["perspective_score"],
        "estimated_transform": transform,
        "homography": homography_payload(homography),
        "projected_left_corners_in_right": projected_corners(left["width"], left["height"], homography),
        "thresholds": thresholds,
    }
    return {
        "candidate_id": candidate_id,
        "detector": "image.keypoint_geometric_match",
        "candidate_type": "keypoint_geometric_match",
        "locations": [left["path"], right["path"]],
        "evidence": {
            "edges": [edge],
            "representative_edge": edge,
            "method": "ORB keypoint matching with RANSAC homography",
        },
        "evidence_strength": "candidate",
        "risk_suggestion": "R2_or_R3_pending_context",
        "risk_cap_tags": [
            "image_similarity_candidate",
            "geometric_image_similarity",
            "keypoint_geometric_match",
        ],
        "benign_explanations": [
            "same field, channel registration, or shared raw acquisition may legitimately align keypoints",
            "adjacent crop, rescaling, export, or figure assembly history may explain the geometric match",
            "feature matches can be unstable on repetitive textures, charts, labels, or low-detail images",
        ],
        "required_materials": [
            "original image files",
            "acquisition metadata",
            "figure assembly file",
            "sample, field, channel, or lane map",
        ],
        "recommended_action": (
            "Inspect the geometric match against raw images, acquisition metadata, and figure assembly "
            "history before escalation."
        ),
        "requires_contextual_calibration": True,
    }


def compare_pair(
    left: dict[str, Any],
    right: dict[str, Any],
    matcher: cv2.BFMatcher,
    ratio_threshold: float,
    min_good_matches: int,
    min_inliers: int,
    min_inlier_ratio: float,
    ransac_reprojection_threshold: float,
) -> tuple[list[Any], int, float, np.ndarray | None]:
    left_descriptors = left["descriptors"]
    right_descriptors = right["descriptors"]
    if left_descriptors is None or right_descriptors is None:
        return [], 0, 0.0, None
    if len(left_descriptors) < 2 or len(right_descriptors) < 2:
        return [], 0, 0.0, None
    knn_matches = matcher.knnMatch(left_descriptors, right_descriptors, k=2)
    good_matches = []
    for pair in knn_matches:
        if len(pair) < 2:
            continue
        match, neighbor = pair
        if match.distance < ratio_threshold * neighbor.distance:
            good_matches.append(match)
    if len(good_matches) < min_good_matches:
        return good_matches, 0, 0.0, None

    left_points = np.float32([left["keypoints"][match.queryIdx].pt for match in good_matches]).reshape(-1, 1, 2)
    right_points = np.float32([right["keypoints"][match.trainIdx].pt for match in good_matches]).reshape(-1, 1, 2)
    homography, mask = cv2.findHomography(left_points, right_points, cv2.RANSAC, ransac_reprojection_threshold)
    if homography is None or mask is None:
        return good_matches, 0, 0.0, None
    inlier_count = int(mask.ravel().sum())
    inlier_ratio = inlier_count / max(1, len(good_matches))
    if inlier_count < min_inliers or inlier_ratio < min_inlier_ratio:
        return good_matches, inlier_count, inlier_ratio, homography
    return good_matches, inlier_count, inlier_ratio, homography


def scan(
    root: Path,
    provenance_path: Path | None,
    max_dimension: int,
    max_features: int,
    ratio_threshold: float,
    min_good_matches: int,
    min_inliers: int,
    min_inlier_ratio: float,
    ransac_reprojection_threshold: float,
    min_rotation_degrees: float,
    min_scale_delta: float,
    min_perspective_score: float,
    max_pair_comparisons: int | None,
) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit("Pillow is required: python3 -m pip install pillow") from exc

    provenance = load_provenance(provenance_path)
    routing = resolve_panel_modality_routing(provenance)
    excluded_panel_paths = {item["panel"] for item in routing.excluded_panels}
    orb = cv2.ORB_create(
        nfeatures=max_features,
        scaleFactor=1.2,
        nlevels=8,
        fastThreshold=7,
    )
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    images = []
    errors = []
    for path in collect_images(root):
        rel_path = display_path(path, root)
        if rel_path.startswith("figures/") and rel_path in excluded_panel_paths:
            continue
        try:
            with Image.open(path) as img:
                for frame_label, base in iter_normalized_frames(img):
                    gray, resize_scale = resized_gray_array(base, max_dimension)
                    keypoints, descriptors = detect_features(gray, orb)
                    images.append({
                        "path": f"{rel_path}{frame_label}",
                        "source_file": rel_path,
                        "frame_label": frame_label or None,
                        "width": int(gray.shape[1]),
                        "height": int(gray.shape[0]),
                        "resize_scale": round_float(resize_scale, 6),
                        "keypoints": keypoints,
                        "descriptors": descriptors,
                    })
        except Exception as exc:  # noqa: BLE001 - unreadable files should not abort an audit.
            errors.append({"path": rel_path, "error": str(exc)})

    thresholds = {
        "ratio_threshold": ratio_threshold,
        "min_good_matches": min_good_matches,
        "min_inliers": min_inliers,
        "min_inlier_ratio": min_inlier_ratio,
        "ransac_reprojection_threshold": ransac_reprojection_threshold,
        "min_rotation_degrees": min_rotation_degrees,
        "min_scale_delta": min_scale_delta,
        "min_perspective_score": min_perspective_score,
    }
    candidates = []
    pair_count = 0
    exhausted = False
    for left, right in itertools.combinations(images, 2):
        if max_pair_comparisons and pair_count >= max_pair_comparisons:
            exhausted = True
            break
        pair_count += 1
        good_matches, inlier_count, inlier_ratio, homography = compare_pair(
            left,
            right,
            matcher,
            ratio_threshold,
            min_good_matches,
            min_inliers,
            min_inlier_ratio,
            ransac_reprojection_threshold,
        )
        if homography is None:
            continue
        if inlier_count < min_inliers or inlier_ratio < min_inlier_ratio:
            continue
        transform = estimate_transform(homography)
        if not has_nontrivial_geometric_change(
            transform,
            min_rotation_degrees,
            min_scale_delta,
            min_perspective_score,
        ):
            continue
        candidates.append(keypoint_candidate(
            left,
            right,
            good_matches,
            inlier_count,
            inlier_ratio,
            homography,
            len(candidates) + 1,
            thresholds,
        ))

    limit_records: list[dict[str, Any]] = []
    if exhausted:
        limit_records.append({
            "path": "image.keypoint_geometric_match",
            "limit_type": "max_pair_comparisons",
            "image_items": len(images),
            "pair_comparisons_attempted": pair_count,
            "max_pair_comparisons": max_pair_comparisons,
        })
        candidates.append(comparison_limit_candidate(limit_records, len(candidates) + 1))

    return {
        "detector_name": "image.keypoint_geometric_match",
        "detector_version": "0.1.0",
        "input": {
            "root": str(root),
            "provenance_graph": str(provenance_path) if provenance_path else None,
            "modality_routing_enabled": True,
            "max_dimension": max_dimension,
            "max_features": max_features,
            **thresholds,
            "max_pair_comparisons": max_pair_comparisons,
            "opencv_version": cv2.__version__,
            "feature_detector": "ORB",
            "matcher": "BFMatcher(NORM_HAMMING) with Lowe ratio test",
            "geometric_model": "RANSAC homography",
            "near_identity_matches": "ignored_by_default_to_reduce_false_positives",
            "multi_frame_images": "screened_as_frame_level_items",
        },
        "images_screened": len(images),
        "pairwise_comparisons_attempted": pair_count,
        "candidate_pair_count": len([item for item in candidates if item["candidate_type"] != "audit_coverage_gap"]),
        "panels_excluded_from_keypoint_scan": list(routing.excluded_panels),
        "modality_conflicts": list(routing.modality_conflicts),
        "comparison_limit_records": limit_records,
        "comparison_budget_exhausted": exhausted,
        "candidates": candidates,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_dir", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--max-dimension", type=int, default=DEFAULT_MAX_DIMENSION)
    parser.add_argument("--max-features", type=int, default=DEFAULT_MAX_FEATURES)
    parser.add_argument("--ratio-threshold", type=float, default=DEFAULT_RATIO_THRESHOLD)
    parser.add_argument("--min-good-matches", type=int, default=DEFAULT_MIN_GOOD_MATCHES)
    parser.add_argument("--min-inliers", type=int, default=DEFAULT_MIN_INLIERS)
    parser.add_argument("--min-inlier-ratio", type=float, default=DEFAULT_MIN_INLIER_RATIO)
    parser.add_argument("--ransac-reprojection-threshold", type=float, default=DEFAULT_RANSAC_REPROJECTION_THRESHOLD)
    parser.add_argument("--min-rotation-degrees", type=float, default=DEFAULT_MIN_ROTATION_DEGREES)
    parser.add_argument("--min-scale-delta", type=float, default=DEFAULT_MIN_SCALE_DELTA)
    parser.add_argument("--min-perspective-score", type=float, default=DEFAULT_MIN_PERSPECTIVE_SCORE)
    parser.add_argument("--max-pair-comparisons", type=int, default=DEFAULT_MAX_PAIR_COMPARISONS)
    parser.add_argument("--output", type=Path, default=Path("keypoint_image_candidates.json"))
    args = parser.parse_args()

    root = args.image_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Image directory not found: {root}")
    output = args.output.expanduser().resolve()
    result = scan(
        root,
        args.provenance.expanduser().resolve() if args.provenance else None,
        args.max_dimension,
        args.max_features,
        args.ratio_threshold,
        args.min_good_matches,
        args.min_inliers,
        args.min_inlier_ratio,
        args.ransac_reprojection_threshold,
        args.min_rotation_degrees,
        args.min_scale_delta,
        args.min_perspective_score,
        args.max_pair_comparisons,
    )
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "images_screened": result["images_screened"],
        "pairwise_comparisons_attempted": result["pairwise_comparisons_attempted"],
        "candidates": len(result["candidates"]),
        "errors": len(result["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
