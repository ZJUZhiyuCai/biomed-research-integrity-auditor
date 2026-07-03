#!/usr/bin/env python3
"""Weak splice-forensics triage for exported image panels.

This detector is deliberately conservative. ELA, JPEG residuals, local
noise-map outliers, JPEG ghost profile prompts, and CFA-like grid
inconsistencies are not proof of manipulation; they are prompts to inspect the
original acquisition files, assembly history, and specialist image-forensics
tools when an exported panel has localized residual/noise/compression/grid
anomalies.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

from detectors.image.image_io import normalized_rgb


DETECTOR_NAME = "image.splice_forensics_triage"
DETECTOR_VERSION = "0.2.0"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
JPEG_EXTS = {".jpg", ".jpeg"}


def relpath(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def collect_images(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTS)


def open_rgb(path: Path) -> Any:
    from PIL import Image

    with Image.open(path) as img:
        return normalized_rgb(img).copy()


def resize_for_screen(img: Any, max_dimension: int) -> Any:
    width, height = img.size
    max_side = max(width, height)
    if max_side <= max_dimension:
        return img.copy()
    scale = max_dimension / float(max_side)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return img.resize(new_size)


def robust_z(value: float, values: list[float]) -> float:
    import numpy as np

    if not values:
        return 0.0
    arr = np.asarray(values, dtype=np.float32)
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    if mad <= 1e-6:
        std = float(np.std(arr))
        return 0.0 if std <= 1e-6 else (value - median) / std
    return 0.6745 * (value - median) / mad


def tile_stats(array: Any, tile_size: int, stride: int) -> list[dict[str, Any]]:
    import numpy as np

    height, width = array.shape[:2]
    tiles: list[dict[str, Any]] = []
    if width < tile_size or height < tile_size:
        return tiles
    for y in range(0, height - tile_size + 1, stride):
        for x in range(0, width - tile_size + 1, stride):
            tile = array[y:y + tile_size, x:x + tile_size]
            tiles.append({
                "x": int(x),
                "y": int(y),
                "width": int(tile_size),
                "height": int(tile_size),
                "mean": float(np.mean(tile)),
                "stddev": float(np.std(tile)),
            })
    return tiles


def ela_residual_array(img: Any, quality: int) -> Any:
    import numpy as np
    from PIL import ImageChops

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    from PIL import Image

    with Image.open(buffer) as compressed:
        diff = ImageChops.difference(img, compressed.convert("RGB"))
    return np.asarray(diff.convert("L"), dtype=np.float32)


def jpeg_residual_tile_stats_by_quality(img: Any, qualities: list[int], tile_size: int, stride: int) -> dict[int, list[dict[str, Any]]]:
    return {
        quality: tile_stats(ela_residual_array(img, quality=quality), tile_size, stride)
        for quality in qualities
    }


def jpeg_ghost_profile_tile(
    img: Any,
    qualities: list[int],
    tile_size: int,
    stride: int,
) -> dict[str, Any] | None:
    """Find a local multi-quality JPEG recompression-profile outlier.

    This is intentionally weak. It looks for a tile whose minimum residual over
    several recompression qualities is much lower than the rest of the panel,
    which can be a JPEG-ghost prompt but can also arise from ordinary flat
    regions, annotations, denoising, or export pipelines.
    """
    if not qualities:
        return None
    by_quality = jpeg_residual_tile_stats_by_quality(img, qualities, tile_size, stride)
    first_tiles = by_quality.get(qualities[0], [])
    if not first_tiles:
        return None
    profile_tiles: list[dict[str, Any]] = []
    for idx, base_tile in enumerate(first_tiles):
        means: list[float] = []
        for quality in qualities:
            tiles = by_quality.get(quality, [])
            if idx >= len(tiles):
                break
            means.append(float(tiles[idx].get("mean", 0.0)))
        if len(means) != len(qualities):
            continue
        min_mean = min(means)
        max_mean = max(means)
        min_quality = qualities[means.index(min_mean)]
        profile_tiles.append({
            "x": int(base_tile.get("x", 0)),
            "y": int(base_tile.get("y", 0)),
            "width": int(base_tile.get("width", tile_size)),
            "height": int(base_tile.get("height", tile_size)),
            "mean": float(min_mean),
            "stddev": float(max_mean - min_mean),
            "profile_min_mean": float(min_mean),
            "profile_max_mean": float(max_mean),
            "profile_range": float(max_mean - min_mean),
            "profile_min_quality": int(min_quality),
        })
    if not profile_tiles:
        return None
    values = [float(tile["profile_min_mean"]) for tile in profile_tiles]
    best = min(profile_tiles, key=lambda tile: float(tile["profile_min_mean"]))
    best = dict(best)
    best["robust_z"] = float(-robust_z(float(best["profile_min_mean"]), values))
    best["tile_count"] = len(profile_tiles)
    best["jpeg_ghost_qualities"] = qualities
    return best


def highpass_noise_array(img: Any) -> Any:
    import cv2
    import numpy as np

    gray = np.asarray(img.convert("L"), dtype=np.float32)
    blurred = cv2.GaussianBlur(gray, (0, 0), sigmaX=1.2)
    residual = gray - blurred
    return np.abs(residual)


def cfa_grid_energy_array(img: Any) -> Any:
    """Return a weak Bayer/CFA-like 2x2 chroma-grid energy map.

    This is not sensor-pattern authentication. It only looks for localized
    high-frequency 2x2 chroma-grid energy that differs from the rest of the
    exported panel enough to justify raw-file or specialist review.
    """
    import cv2
    import numpy as np

    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    chroma_opponent = ((rgb[:, :, 0] - rgb[:, :, 1]) + (rgb[:, :, 2] - rgb[:, :, 1])) / 2.0
    kernels = [
        np.asarray([[1.0, -1.0], [-1.0, 1.0]], dtype=np.float32),
        np.asarray([[1.0, -1.0], [1.0, -1.0]], dtype=np.float32),
        np.asarray([[1.0, 1.0], [-1.0, -1.0]], dtype=np.float32),
    ]
    responses = [
        np.abs(cv2.filter2D(chroma_opponent, ddepth=-1, kernel=kernel / 4.0))
        for kernel in kernels
    ]
    energy = np.maximum.reduce(responses)
    return cv2.GaussianBlur(energy, (0, 0), sigmaX=0.6)


def strongest_tile(tiles: list[dict[str, Any]], key: str = "mean") -> dict[str, Any] | None:
    if not tiles:
        return None
    values = [float(tile.get(key, 0.0)) for tile in tiles]
    best = max(tiles, key=lambda tile: float(tile.get(key, 0.0)))
    best = dict(best)
    best["robust_z"] = float(robust_z(float(best.get(key, 0.0)), values))
    best["tile_count"] = len(tiles)
    return best


def candidate(
    index: int,
    path: str,
    analysis_type: str,
    tile: dict[str, Any],
    image_size: tuple[int, int],
    risk_suggestion: str = "R2",
) -> dict[str, Any]:
    metric_labels = {
        "jpeg_ela_residual_outlier": "ELA/JPEG residual",
        "jpeg_ghost_profile_outlier": "JPEG ghost recompression profile",
        "noise_residual_outlier": "high-pass noise residual",
        "cfa_grid_consistency_outlier": "CFA-like chroma grid energy",
    }
    interpretations = {
        "jpeg_ghost_profile_outlier": (
            "Localized multi-quality JPEG recompression residual profile differs from the rest of an exported JPEG panel. "
            "This is a weak JPEG-ghost triage signal requiring the original file, export history, and specialist review; "
            "it is not robust JPEG ghost analysis."
        ),
        "cfa_grid_consistency_outlier": (
            "Localized CFA-like 2x2 chroma-grid energy differs from the rest of an exported image panel. "
            "This is a weak triage signal requiring raw acquisition files, camera/channel metadata, and specialist review; "
            "it is not sensor-pattern authentication."
        ),
    }
    metric_label = metric_labels.get(analysis_type, "image-forensics residual")
    interpretation_text = interpretations.get(
        analysis_type,
        (
            "Localized compression/noise residual anomaly detected in an exported image panel. "
            "This is a weak triage signal requiring raw acquisition files and specialist review."
        ),
    )
    evidence = {
        "analysis_type": analysis_type,
        "path": path,
        "metric": metric_label,
        "region": {
            "x": tile.get("x"),
            "y": tile.get("y"),
            "width": tile.get("width"),
            "height": tile.get("height"),
        },
        "tile_mean": round(float(tile.get("mean", 0.0)), 4),
        "tile_stddev": round(float(tile.get("stddev", 0.0)), 4),
        "robust_z": round(float(tile.get("robust_z", 0.0)), 4),
        "tile_count": int(tile.get("tile_count", 0) or 0),
        "image_width": image_size[0],
        "image_height": image_size[1],
        "interpretation": interpretation_text,
    }
    for key in (
        "profile_min_mean",
        "profile_max_mean",
        "profile_range",
        "profile_min_quality",
        "jpeg_ghost_qualities",
    ):
        if key in tile:
            value = tile[key]
            if isinstance(value, float):
                value = round(value, 4)
            evidence[key] = value
    return {
        "candidate_id": f"IMG-SPLICE-TRIAGE-{index:04d}",
        "detector": DETECTOR_NAME,
        "candidate_type": "splice_forensics_triage_signal",
        "locations": [path],
        "evidence": evidence,
        "evidence_strength": "weak_signal",
        "risk_suggestion": risk_suggestion,
        "risk_cap_tags": [
            "splice_forensics_triage_signal",
            "weak_forensic_triage_signal",
        ],
        "benign_explanations": [
            "Different regions may contain genuine structure, labels, annotations, scale bars, or compression artifacts from export settings.",
            "Uneven illumination, denoising, sharpening, microscope stitching, or figure-assembly export can create localized residual differences.",
            "Demosaicing, color-channel processing, compression, or instrument/export pipelines can create CFA-like grid energy without implying image manipulation.",
            "JPEG ghost-like residual profiles can be caused by ordinary flat regions, annotations, denoising, resampling, or repeated export/compression.",
        ],
        "required_materials": [
            "original raw or uncropped acquisition file",
            "camera, scanner, microscope, or channel acquisition metadata when available",
            "figure assembly/export history",
            "specialist image-forensics review or external-tool report if the signal persists",
        ],
        "recommended_action": (
            "Review the highlighted region against the raw acquisition file and figure assembly history; "
            "treat this as a weak splice-forensics prompt, not as a conclusion."
        ),
        "requires_contextual_calibration": True,
    }


def analyze_image(
    package: Path,
    path: Path,
    tile_size: int,
    stride: int,
    max_dimension: int,
    ela_z_threshold: float,
    noise_z_threshold: float,
    cfa_z_threshold: float,
    cfa_mean_threshold: float,
    jpeg_ghost_z_threshold: float,
    jpeg_ghost_range_threshold: float,
    jpeg_ghost_qualities: list[int],
    min_tiles: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    rel = relpath(package, path)
    img = resize_for_screen(open_rgb(path), max_dimension)
    image_size = img.size
    diagnostics: dict[str, Any] = {
        "path": rel,
        "width": image_size[0],
        "height": image_size[1],
        "jpeg_ela_screened": path.suffix.lower() in JPEG_EXTS,
        "jpeg_ghost_screened": path.suffix.lower() in JPEG_EXTS,
        "noise_screened": True,
        "cfa_grid_screened": True,
        "signals": [],
    }

    if path.suffix.lower() in JPEG_EXTS:
        ela_tiles = tile_stats(ela_residual_array(img, quality=90), tile_size, stride)
        best = strongest_tile(ela_tiles)
        if best:
            diagnostics["ela_best_robust_z"] = round(float(best["robust_z"]), 4)
            diagnostics["ela_tile_count"] = int(best["tile_count"])
            if best["tile_count"] >= min_tiles and best["robust_z"] >= ela_z_threshold:
                diagnostics["signals"].append("jpeg_ela_residual_outlier")
                candidates.append(candidate(0, rel, "jpeg_ela_residual_outlier", best, image_size))
        ghost = jpeg_ghost_profile_tile(img, jpeg_ghost_qualities, tile_size, stride)
        if ghost:
            diagnostics["jpeg_ghost_best_robust_z"] = round(float(ghost["robust_z"]), 4)
            diagnostics["jpeg_ghost_profile_range"] = round(float(ghost["profile_range"]), 4)
            diagnostics["jpeg_ghost_min_quality"] = int(ghost["profile_min_quality"])
            diagnostics["jpeg_ghost_tile_count"] = int(ghost["tile_count"])
            if (
                ghost["tile_count"] >= min_tiles
                and ghost["robust_z"] >= jpeg_ghost_z_threshold
                and ghost["profile_range"] >= jpeg_ghost_range_threshold
            ):
                diagnostics["signals"].append("jpeg_ghost_profile_outlier")
                candidates.append(candidate(0, rel, "jpeg_ghost_profile_outlier", ghost, image_size))

    noise_tiles = tile_stats(highpass_noise_array(img), tile_size, stride)
    best_noise = strongest_tile(noise_tiles, key="stddev")
    if best_noise:
        diagnostics["noise_best_robust_z"] = round(float(best_noise["robust_z"]), 4)
        diagnostics["noise_tile_count"] = int(best_noise["tile_count"])
        if best_noise["tile_count"] >= min_tiles and best_noise["robust_z"] >= noise_z_threshold:
            diagnostics["signals"].append("noise_residual_outlier")
            candidates.append(candidate(0, rel, "noise_residual_outlier", best_noise, image_size))

    cfa_tiles = tile_stats(cfa_grid_energy_array(img), tile_size, stride)
    best_cfa = strongest_tile(cfa_tiles)
    if best_cfa:
        diagnostics["cfa_best_robust_z"] = round(float(best_cfa["robust_z"]), 4)
        diagnostics["cfa_best_mean"] = round(float(best_cfa.get("mean", 0.0)), 4)
        diagnostics["cfa_tile_count"] = int(best_cfa["tile_count"])
        if (
            best_cfa["tile_count"] >= min_tiles
            and best_cfa["robust_z"] >= cfa_z_threshold
            and float(best_cfa.get("mean", 0.0)) >= cfa_mean_threshold
        ):
            diagnostics["signals"].append("cfa_grid_consistency_outlier")
            candidates.append(candidate(0, rel, "cfa_grid_consistency_outlier", best_cfa, image_size))

    return candidates, diagnostics


def build_payload(
    package: Path,
    tile_size: int = 96,
    stride: int = 96,
    max_dimension: int = 1200,
    max_images: int = 250,
    ela_z_threshold: float = 8.0,
    noise_z_threshold: float = 8.0,
    cfa_z_threshold: float = 3.5,
    cfa_mean_threshold: float = 10.0,
    jpeg_ghost_z_threshold: float = 4.0,
    jpeg_ghost_range_threshold: float = 4.0,
    jpeg_ghost_qualities: list[int] | None = None,
    min_tiles: int = 16,
) -> dict[str, Any]:
    images = collect_images(package)
    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    screened = 0
    limit_reached = False
    jpeg_ghost_qualities = jpeg_ghost_qualities or [65, 75, 85, 95]

    for path in images:
        if screened >= max_images:
            limit_reached = True
            break
        try:
            found, diag = analyze_image(
                package,
                path,
                tile_size,
                stride,
                max_dimension,
                ela_z_threshold,
                noise_z_threshold,
                cfa_z_threshold,
                cfa_mean_threshold,
                jpeg_ghost_z_threshold,
                jpeg_ghost_range_threshold,
                jpeg_ghost_qualities,
                min_tiles,
            )
            screened += 1
            diagnostics.append(diag)
            for item in found:
                item["candidate_id"] = f"IMG-SPLICE-TRIAGE-{len(candidates) + 1:04d}"
                candidates.append(item)
        except Exception as exc:  # noqa: BLE001 - surface unreadable images as detector errors.
            errors.append({
                "path": relpath(package, path),
                "error": f"{type(exc).__name__}: {exc}",
            })

    if limit_reached:
        candidates.append({
            "candidate_id": f"IMG-SPLICE-TRIAGE-{len(candidates) + 1:04d}",
            "detector": DETECTOR_NAME,
            "candidate_type": "audit_coverage_gap",
            "locations": [str(package)],
            "evidence": {
                "stage": "splice_forensics_triage",
                "images_total": len(images),
                "images_screened": screened,
                "max_images": max_images,
                "message": "Splice-forensics triage reached its image budget.",
            },
            "evidence_strength": "weak_signal",
            "risk_suggestion": "R1",
            "risk_cap_tags": ["audit_coverage_gap", "completeness_gap"],
            "benign_explanations": [
                "The package may be larger than the fast triage budget.",
            ],
            "required_materials": [
                "focused deep image-forensics run or external image-review packet",
            ],
            "recommended_action": "Run a focused deep scan or external image review before treating splice-forensics triage as complete.",
            "requires_contextual_calibration": True,
        })

    return {
        "detector_name": DETECTOR_NAME,
        "detector_version": DETECTOR_VERSION,
        "input": {
            "package": str(package),
            "tile_size": tile_size,
            "stride": stride,
            "max_dimension": max_dimension,
            "max_images": max_images,
            "ela_z_threshold": ela_z_threshold,
            "noise_z_threshold": noise_z_threshold,
            "cfa_z_threshold": cfa_z_threshold,
            "cfa_mean_threshold": cfa_mean_threshold,
            "jpeg_ghost_z_threshold": jpeg_ghost_z_threshold,
            "jpeg_ghost_range_threshold": jpeg_ghost_range_threshold,
            "jpeg_ghost_qualities": jpeg_ghost_qualities,
            "min_tiles": min_tiles,
        },
        "images_screened": screened,
        "image_files_total": len(images),
        "candidate_signal_count": sum(
            1 for item in candidates if item.get("candidate_type") == "splice_forensics_triage_signal"
        ),
        "coverage_limit_reached": limit_reached,
        "diagnostics": diagnostics[:200],
        "scope_note": (
            "ELA/JPEG residual, noise-map, JPEG ghost-profile, and CFA-like grid outliers are weak triage prompts. "
            "They can be caused by ordinary export, annotation, compression, denoising, demosaicing, or imaging differences "
            "and require raw files and expert review."
        ),
        "candidates": candidates,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path, default=Path("splice_forensics_candidates.json"))
    parser.add_argument("--tile-size", type=int, default=96)
    parser.add_argument("--stride", type=int, default=96)
    parser.add_argument("--max-dimension", type=int, default=1200)
    parser.add_argument("--max-images", type=int, default=250)
    parser.add_argument("--ela-z-threshold", type=float, default=8.0)
    parser.add_argument("--noise-z-threshold", type=float, default=8.0)
    parser.add_argument("--cfa-z-threshold", type=float, default=3.5)
    parser.add_argument("--cfa-mean-threshold", type=float, default=10.0)
    parser.add_argument("--jpeg-ghost-z-threshold", type=float, default=4.0)
    parser.add_argument("--jpeg-ghost-range-threshold", type=float, default=4.0)
    parser.add_argument("--jpeg-ghost-qualities", default="65,75,85,95")
    parser.add_argument("--min-tiles", type=int, default=16)
    args = parser.parse_args()

    package = args.package.expanduser().resolve()
    output = args.output.expanduser().resolve()
    payload = build_payload(
        package,
        tile_size=args.tile_size,
        stride=args.stride,
        max_dimension=args.max_dimension,
        max_images=args.max_images,
        ela_z_threshold=args.ela_z_threshold,
        noise_z_threshold=args.noise_z_threshold,
        cfa_z_threshold=args.cfa_z_threshold,
        cfa_mean_threshold=args.cfa_mean_threshold,
        jpeg_ghost_z_threshold=args.jpeg_ghost_z_threshold,
        jpeg_ghost_range_threshold=args.jpeg_ghost_range_threshold,
        jpeg_ghost_qualities=[int(item) for item in str(args.jpeg_ghost_qualities).split(",") if item.strip()],
        min_tiles=args.min_tiles,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "images_screened": payload["images_screened"],
        "candidate_signal_count": payload["candidate_signal_count"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
