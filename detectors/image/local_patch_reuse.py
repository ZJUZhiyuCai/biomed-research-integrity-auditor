#!/usr/bin/env python3
"""Local image patch reuse detector with provenance-aware pair exclusion."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from detectors.image.image_io import iter_normalized_frames
from provenance.panel_modality import resolve_panel_modality_routing


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
DEFAULT_MAX_TILES_PER_IMAGE = 2000
DEFAULT_MAX_TOTAL_TILE_COMPARISONS = 20_000_000
FIGURE_SOURCE_TRACEABILITY_RELATIONS = {
    "declared_derived_from",
    "declared_same_source",
    "same_membrane_reprobe",
}
FIGURE_FIGURE_TRACEABILITY_RELATIONS = {
    "same_field_different_channel",
    "same_membrane_reprobe",
}
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


def transformed(img: Any, transform_name: str) -> Any:
    if transform_name == "identity":
        return img.copy()
    from PIL import Image

    return img.transpose(getattr(Image.Transpose, TRANSFORMS[transform_name]))


def collect_images(root: Path) -> list[Path]:
    return [path for path in sorted(root.rglob("*")) if path.is_file() and path.suffix.lower() in IMAGE_EXTS]


def undirected_pair(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))


def bounds_to_region(bounds: tuple[int, int, int, int]) -> dict[str, int]:
    return {
        "x": bounds[0],
        "y": bounds[1],
        "width": bounds[2] - bounds[0],
        "height": bounds[3] - bounds[1],
    }


def bounds_overlap(left: tuple[int, int, int, int], right: tuple[int, int, int, int], padding: int = 0) -> bool:
    return not (
        left[2] + padding <= right[0]
        or right[2] + padding <= left[0]
        or left[3] + padding <= right[1]
        or right[3] + padding <= left[1]
    )


def distinct_within_image_regions(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
    min_gap: int,
) -> bool:
    if left == right:
        return False
    return not bounds_overlap(left, right, max(0, min_gap))


def load_provenance(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"edges": []}
    return json.loads(path.read_text(encoding="utf-8"))


def role_from_path(path: str) -> str:
    if path.startswith("figures/"):
        return "figure_panel"
    if path.startswith("raw_images/"):
        return "raw_image"
    if path.startswith("source_data/"):
        return "source_data"
    return "resource"


def is_authoritative_traceability_edge(edge: dict[str, Any]) -> bool:
    if edge.get("risk_effect") != "expected_traceability":
        return False
    source_path = str(edge.get("source_path", ""))
    target_path = str(edge.get("target_path", ""))
    if not source_path or not target_path or source_path == target_path:
        return False
    source_role = role_from_path(source_path)
    target_role = role_from_path(target_path)
    roles = {source_role, target_role}
    relation = str(edge.get("relation_type", "")).lower()
    if roles == {"figure_panel", "raw_image"} or roles == {"figure_panel", "source_data"}:
        return relation in FIGURE_SOURCE_TRACEABILITY_RELATIONS
    if source_role == "figure_panel" and target_role == "figure_panel":
        return relation in FIGURE_FIGURE_TRACEABILITY_RELATIONS
    return False


def expected_traceability_pairs(provenance: dict[str, Any]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for edge in provenance.get("edges", []) or []:
        if is_authoritative_traceability_edge(edge):
            pairs.add(undirected_pair(str(edge.get("source_path", "")), str(edge.get("target_path", ""))))
    return pairs


def luma_stats(img: Any) -> tuple[float, float]:
    pixels = luma_array(img)
    if pixels.size == 0:
        return 0.0, 0.0
    return float(np.mean(pixels)), float(np.std(pixels))


def luma_array(img: Any) -> np.ndarray:
    return np.asarray(img.convert("L"), dtype=np.float32)


def transformed_array(array: np.ndarray, transform_name: str) -> np.ndarray:
    if transform_name == "identity":
        return array
    if transform_name == "rot90":
        return np.rot90(array, 1)
    if transform_name == "rot180":
        return np.rot90(array, 2)
    if transform_name == "rot270":
        return np.rot90(array, 3)
    if transform_name == "flip_h":
        return np.fliplr(array)
    if transform_name == "flip_v":
        return np.flipud(array)
    if transform_name == "transpose":
        return array.T
    if transform_name == "transverse":
        return np.fliplr(np.flipud(array)).T
    raise ValueError(f"unsupported transform: {transform_name}")


def ncc_profile(array: np.ndarray) -> dict[str, Any]:
    values = np.asarray(array, dtype=np.float32).reshape(-1)
    if values.size == 0:
        return {"values": values, "centered": values, "energy": 0.0}
    centered = values - np.mean(values, dtype=np.float64)
    energy = float(np.dot(centered, centered))
    return {"values": values, "centered": centered, "energy": energy}


def normalized_cross_correlation_from_profile(left_profile: dict[str, Any], right_array: np.ndarray) -> float:
    right_profile = ncc_profile(right_array)
    left_values = left_profile["values"]
    right_values = right_profile["values"]
    if left_values.size != right_values.size or left_values.size == 0:
        return 0.0
    left_energy = float(left_profile["energy"])
    right_energy = float(right_profile["energy"])
    denominator = math.sqrt(left_energy * right_energy)
    if denominator == 0:
        return 1.0 if np.array_equal(left_values, right_values) else 0.0
    numerator = float(np.dot(left_profile["centered"], right_profile["centered"]))
    return max(-1.0, min(1.0, numerator / denominator))


def normalized_cross_correlation(left: Any, right: Any) -> float:
    left_array = luma_array(left)
    return normalized_cross_correlation_from_profile(ncc_profile(left_array), luma_array(right))


def tile_hashes(tile: Any, hash_size: int) -> dict[str, int]:
    return {
        "average_hash": average_hash(tile, hash_size),
        "difference_hash": difference_hash(tile, hash_size),
    }


def transformed_hashes(tile: dict[str, Any], transform_name: str, hash_size: int) -> dict[str, int]:
    cache = tile.setdefault("transformed_hashes", {})
    if transform_name not in cache:
        cache[transform_name] = tile_hashes(transformed(tile["image"], transform_name), hash_size)
    return cache[transform_name]


def transformed_tile_array(tile: dict[str, Any], transform_name: str) -> np.ndarray:
    return transformed_array(tile["array"], transform_name)


def contrast_enhanced_luma(img: Any) -> Any:
    from PIL import ImageOps

    return ImageOps.autocontrast(img.convert("L"))


def generate_tiles(
    img: Any,
    tile_size: int,
    stride: int,
    hash_size: int,
    min_stddev: float,
    view_name: str = "luma",
) -> list[dict[str, Any]]:
    width, height = img.size
    if width < tile_size or height < tile_size:
        return []
    tiles: list[dict[str, Any]] = []
    y_values = list(range(0, height - tile_size + 1, stride))
    x_values = list(range(0, width - tile_size + 1, stride))
    if y_values[-1] != height - tile_size:
        y_values.append(height - tile_size)
    if x_values[-1] != width - tile_size:
        x_values.append(width - tile_size)
    for y in y_values:
        for x in x_values:
            bounds = (x, y, x + tile_size, y + tile_size)
            tile = img.crop(bounds).convert("L")
            tile_array = luma_array(tile)
            _, stddev = float(np.mean(tile_array)), float(np.std(tile_array))
            if stddev < min_stddev:
                continue
            tiles.append({
                "bounds": bounds,
                "image": tile,
                "array": tile_array,
                "hashes": tile_hashes(tile, hash_size),
                "ncc_profile": ncc_profile(tile_array),
                "stddev": round(stddev, 3),
                "view": view_name,
                "tile_size": tile_size,
            })
    return tiles


def limit_tiles(
    tiles: list[dict[str, Any]],
    max_tiles: int | None,
) -> tuple[list[dict[str, Any]], bool]:
    if max_tiles is None or max_tiles <= 0 or len(tiles) <= max_tiles:
        return tiles, False
    if max_tiles == 1:
        return [tiles[len(tiles) // 2]], True
    step = (len(tiles) - 1) / (max_tiles - 1)
    indices = [min(len(tiles) - 1, round(idx * step)) for idx in range(max_tiles)]
    selected = [tiles[idx] for idx in dict.fromkeys(indices)]
    return selected, True


class ComparisonBudget:
    def __init__(self, max_comparisons: int | None) -> None:
        self.max_comparisons = max_comparisons if max_comparisons and max_comparisons > 0 else None
        self.used = 0
        self.exhausted = False

    def consume(self) -> bool:
        if self.max_comparisons is None:
            self.used += 1
            return True
        if self.used >= self.max_comparisons:
            self.exhausted = True
            return False
        self.used += 1
        return True


def best_tile_match(
    left_tile: dict[str, Any],
    right_tile: dict[str, Any],
    hash_threshold: int,
    hash_size: int,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for transform_name in TRANSFORMS:
        right_hashes = transformed_hashes(right_tile, transform_name, hash_size)
        distances = {
            method: hamming(left_tile["hashes"][method], right_hashes[method])
            for method in left_tile["hashes"]
        }
        distance = min(distances.values())
        if distance > hash_threshold:
            continue
        score = normalized_cross_correlation_from_profile(
            left_tile["ncc_profile"],
            transformed_tile_array(right_tile, transform_name),
        )
        if best is None or (score, -distance) > (best["score"], -best["hash_distance"]):
            best = {
                "best_transform": transform_name,
                "score": score,
                "hash_distance": distance,
                "hash_distances": distances,
            }
    return best


def union_region(bounds: list[tuple[int, int, int, int]]) -> dict[str, int]:
    return {
        "x": min(item[0] for item in bounds),
        "y": min(item[1] for item in bounds),
        "width": max(item[2] for item in bounds) - min(item[0] for item in bounds),
        "height": max(item[3] for item in bounds) - min(item[1] for item in bounds),
    }


def region_area(region: dict[str, int]) -> int:
    return int(region["width"]) * int(region["height"])


def merged_region_fraction(hits: list[dict[str, Any]], left_size: tuple[int, int], right_size: tuple[int, int]) -> float:
    region_a = union_region([
        (
            hit["region_a"]["x"],
            hit["region_a"]["y"],
            hit["region_a"]["x"] + hit["region_a"]["width"],
            hit["region_a"]["y"] + hit["region_a"]["height"],
        )
        for hit in hits
    ])
    region_b = union_region([
        (
            hit["region_b"]["x"],
            hit["region_b"]["y"],
            hit["region_b"]["x"] + hit["region_b"]["width"],
            hit["region_b"]["y"] + hit["region_b"]["height"],
        )
        for hit in hits
    ])
    left_area = max(1, left_size[0] * left_size[1])
    right_area = max(1, right_size[0] * right_size[1])
    return max(region_area(region_a) / left_area, region_area(region_b) / right_area)


def crop_from_region(img: Any, region: dict[str, int]) -> Any:
    box = (
        region["x"],
        region["y"],
        region["x"] + region["width"],
        region["y"] + region["height"],
    )
    return img.crop(box)


def display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def save_evidence_crops(
    root: Path,
    evidence_dir: Path,
    candidate_id: str,
    left: dict[str, Any],
    right: dict[str, Any],
    region_left: dict[str, int],
    region_right: dict[str, int],
) -> dict[str, str]:
    from PIL import Image

    evidence_dir.mkdir(parents=True, exist_ok=True)
    left_crop = crop_from_region(left["image"], region_left)
    right_crop = crop_from_region(right["image"], region_right)
    left_name = f"{candidate_id}_A.png"
    right_name = f"{candidate_id}_B.png"
    side_name = f"{candidate_id}_side_by_side.png"
    left_crop.save(evidence_dir / left_name)
    right_crop.save(evidence_dir / right_name)
    side = Image.new("RGB", (left_crop.width + right_crop.width, max(left_crop.height, right_crop.height)), (255, 255, 255))
    side.paste(left_crop.convert("RGB"), (0, 0))
    side.paste(right_crop.convert("RGB"), (left_crop.width, 0))
    side.save(evidence_dir / side_name)
    return {
        "crop_a": display_path(evidence_dir / left_name, root),
        "crop_b": display_path(evidence_dir / right_name, root),
        "side_by_side": display_path(evidence_dir / side_name, root),
    }


def scan_pair(
    left: dict[str, Any],
    right: dict[str, Any],
    hash_threshold: int,
    hash_size: int,
    ncc_threshold: float,
    max_region_fraction: float,
    budget: ComparisonBudget | None = None,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen_regions: set[tuple[tuple[int, int, int, int], tuple[int, int, int, int], str]] = set()
    for left_tile in left["tiles"]:
        for right_tile in right["tiles"]:
            if budget is not None and not budget.consume():
                return hits
            best = best_tile_match(left_tile, right_tile, hash_threshold, hash_size)
            if not best or best["score"] < ncc_threshold:
                continue
            key = (left_tile["bounds"], right_tile["bounds"], best["best_transform"])
            if key in seen_regions:
                continue
            seen_regions.add(key)
            hits.append({
                "region_a": bounds_to_region(left_tile["bounds"]),
                "region_b": bounds_to_region(right_tile["bounds"]),
                "best_transform": best["best_transform"],
                "score": round(float(best["score"]), 6),
                "hash_distance": int(best["hash_distance"]),
                "hash_distances": best["hash_distances"],
                "tile_stddev_a": left_tile["stddev"],
                "tile_stddev_b": right_tile["stddev"],
            })
    if hits and merged_region_fraction(hits, left["image"].size, right["image"].size) > max_region_fraction:
        return []
    return hits


def scan_within_image(
    image: dict[str, Any],
    tiles: list[dict[str, Any]],
    hash_threshold: int,
    hash_size: int,
    ncc_threshold: float,
    max_region_fraction: float,
    min_gap: int,
    min_tile_hits: int,
    require_displacement_cluster: bool = False,
    budget: ComparisonBudget | None = None,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen_regions: set[tuple[tuple[int, int, int, int], tuple[int, int, int, int], str]] = set()
    for left_index, left_tile in enumerate(tiles):
        for right_tile in tiles[left_index + 1:]:
            if budget is not None and not budget.consume():
                return hits
            if not distinct_within_image_regions(left_tile["bounds"], right_tile["bounds"], min_gap):
                continue
            best = best_tile_match(left_tile, right_tile, hash_threshold, hash_size)
            if not best or best["score"] < ncc_threshold:
                continue
            ordered_bounds = tuple(sorted((left_tile["bounds"], right_tile["bounds"])))
            key = (ordered_bounds[0], ordered_bounds[1], best["best_transform"])
            if key in seen_regions:
                continue
            seen_regions.add(key)
            hits.append({
                "region_a": bounds_to_region(left_tile["bounds"]),
                "region_b": bounds_to_region(right_tile["bounds"]),
                "best_transform": best["best_transform"],
                "score": round(float(best["score"]), 6),
                "hash_distance": int(best["hash_distance"]),
                "hash_distances": best["hash_distances"],
                "tile_stddev_a": left_tile["stddev"],
                "tile_stddev_b": right_tile["stddev"],
                "detection_view": left_tile.get("view", "luma"),
                "tile_size": left_tile.get("tile_size"),
            })
    if len(hits) < min_tile_hits:
        return []
    if require_displacement_cluster:
        hits = best_displacement_cluster(hits, image["image"].size, max_region_fraction, min_tile_hits)
        if not hits:
            return []
    elif merged_region_fraction(hits, image["image"].size, image["image"].size) > max_region_fraction:
        return []
    return hits


def coverage_gap_candidate(records: list[dict[str, Any]], idx: int) -> dict[str, Any]:
    return {
        "candidate_id": f"IMG-COVERAGE-GAP-{idx:04d}",
        "detector": "image.local_patch_reuse",
        "candidate_type": "audit_coverage_gap",
        "locations": sorted({str(record.get("path") or "local_patch_reuse") for record in records}),
        "evidence": {
            "message": "Local patch / same-image copy-move screening was partially limited by runtime budget.",
            "records": records,
        },
        "evidence_strength": "weak_signal",
        "risk_suggestion": "R1_possible",
        "risk_cap_tags": ["audit_coverage_gap", "completeness_gap"],
        "benign_explanations": [
            "large high-resolution packages may require a deep scan on selected figures",
            "runtime limits prevent the local detector from examining every tile pair in this run",
        ],
        "required_materials": [
            "targeted deep scan for high-priority panels",
            "raw images and figure assembly files for any unscreened or partially screened panels",
        ],
        "recommended_action": "Run a focused deep scan on the listed files or increase local screening budgets before treating local-patch coverage as complete.",
        "requires_contextual_calibration": True,
    }


def displacement_key(hit: dict[str, Any], bin_size: int = 32) -> tuple[int, int, str]:
    dx = int(hit["region_b"]["x"]) - int(hit["region_a"]["x"])
    dy = int(hit["region_b"]["y"]) - int(hit["region_a"]["y"])
    return (
        round(dx / bin_size) * bin_size,
        round(dy / bin_size) * bin_size,
        str(hit.get("best_transform", "identity")),
    )


def best_displacement_cluster(
    hits: list[dict[str, Any]],
    image_size: tuple[int, int],
    max_region_fraction: float,
    min_tile_hits: int,
) -> list[dict[str, Any]]:
    groups: dict[tuple[int, int, str], list[dict[str, Any]]] = defaultdict(list)
    for hit in hits:
        groups[displacement_key(hit)].append(hit)

    eligible = []
    for key, group in groups.items():
        if len(group) < min_tile_hits:
            continue
        if merged_region_fraction(group, image_size, image_size) > max_region_fraction:
            continue
        best_score = max(float(hit["score"]) for hit in group)
        mean_score = sum(float(hit["score"]) for hit in group) / len(group)
        eligible.append((len(group), best_score, mean_score, key, group))
    if not eligible:
        return []
    return max(eligible, key=lambda item: (item[0], item[1], item[2]))[-1]


def candidate_from_hits(
    root: Path,
    evidence_dir: Path,
    left: dict[str, Any],
    right: dict[str, Any],
    hits: list[dict[str, Any]],
    idx: int,
    tile_size: int,
    stride: int,
    same_image: bool = False,
) -> dict[str, Any]:
    candidate_id = f"{'COPYMOVE' if same_image else 'LOCALPATCH'}-{idx:04d}"
    best_hit = max(hits, key=lambda item: (item["score"], -item["hash_distance"]))
    region_a = union_region([
        (
            hit["region_a"]["x"],
            hit["region_a"]["y"],
            hit["region_a"]["x"] + hit["region_a"]["width"],
            hit["region_a"]["y"] + hit["region_a"]["height"],
        )
        for hit in hits
    ])
    region_b = union_region([
        (
            hit["region_b"]["x"],
            hit["region_b"]["y"],
            hit["region_b"]["x"] + hit["region_b"]["width"],
            hit["region_b"]["y"] + hit["region_b"]["height"],
        )
        for hit in hits
    ])
    evidence_paths = save_evidence_crops(root, evidence_dir, candidate_id, left, right, region_a, region_b)
    similarity_scope = "same_image_copy_move" if same_image else "local_patch"
    edge = {
        "left": left["path"],
        "right": right["path"],
        "similarity_scope": similarity_scope,
        "same_image": same_image,
        "region_a": region_a,
        "region_b": region_b,
        "tile_hits": hits,
        "tile_hit_count": len(hits),
        "best_transform": best_hit["best_transform"],
        "score": best_hit["score"],
        "hash_distance": best_hit["hash_distance"],
        "detection_view": best_hit.get("detection_view", "luma"),
        "evidence_crops": evidence_paths,
    }
    risk_tags = ["image_similarity_candidate", "local_patch_reuse"]
    if same_image:
        risk_tags.append("same_image_copy_move")
    return {
        "candidate_id": candidate_id,
        "detector": "image.local_patch_reuse",
        "candidate_type": "same_image_copy_move" if same_image else "local_patch_reuse",
        "locations": [left["path"]] if same_image else [left["path"], right["path"]],
        "evidence": {
            "edges": [edge],
            "representative_edge": edge,
            "tile_size": tile_size,
            "stride": stride,
        },
        "evidence_strength": "candidate",
        "risk_suggestion": "R3_possible",
        "risk_cap_tags": risk_tags,
        "benign_explanations": [
            "same raw field, channel, membrane, or crop may be intentionally reused with disclosure",
            "same-image local similarities can arise from repeated biological structures or image registration artifacts",
            "image registration, compression, or downsampling may create local similarities",
            "source/raw records are needed before escalation",
        ],
        "required_materials": [
            "original image files",
            "acquisition metadata",
            "figure assembly file",
            "sample, field, channel, or lane map",
        ],
        "recommended_action": "Inspect local patch coordinates against raw images, acquisition metadata, and figure assembly records before escalation.",
        "requires_contextual_calibration": True,
    }


def scan(
    root: Path,
    provenance_path: Path | None,
    evidence_dir: Path,
    tile_size: int,
    stride: int,
    hash_size: int,
    hash_threshold: int,
    ncc_threshold: float,
    min_stddev: float,
    max_region_fraction: float,
    within_image_ncc_threshold: float,
    within_image_min_gap: int,
    within_image_min_tile_hits: int,
    low_contrast_stddev_threshold: float,
    low_contrast_min_stddev: float,
    low_contrast_ncc_threshold: float,
    max_tiles_per_image: int | None = DEFAULT_MAX_TILES_PER_IMAGE,
    max_total_tile_comparisons: int | None = DEFAULT_MAX_TOTAL_TILE_COMPARISONS,
) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit("Pillow is required: python3 -m pip install pillow") from exc

    provenance = load_provenance(provenance_path)
    excluded_pairs = expected_traceability_pairs(provenance)
    routing = resolve_panel_modality_routing(provenance)
    excluded_panel_paths = {item["panel"] for item in routing.excluded_panels}
    image_paths = collect_images(root)
    images = []
    errors = []
    limit_records: list[dict[str, Any]] = []
    comparison_budget = ComparisonBudget(max_total_tile_comparisons)
    panels_excluded_from_deep_scan = list(routing.excluded_panels)
    modality_conflicts = list(routing.modality_conflicts)
    for path in image_paths:
        rel_path = str(path.relative_to(root))
        if rel_path.startswith("figures/") and rel_path in excluded_panel_paths:
            continue
        try:
            with Image.open(path) as img:
                for frame_label, base in iter_normalized_frames(img):
                    tiles = generate_tiles(base, tile_size, stride, hash_size, min_stddev)
                    original_tile_count = len(tiles)
                    tiles, tiles_limited = limit_tiles(tiles, max_tiles_per_image)
                    if tiles_limited:
                        limit_records.append({
                            "path": f"{rel_path}{frame_label}",
                            "limit_type": "max_tiles_per_image",
                            "view": "luma",
                            "available_tiles": original_tile_count,
                            "screened_tiles": len(tiles),
                            "max_tiles_per_image": max_tiles_per_image,
                        })
                    _, image_stddev = luma_stats(base)
                    low_contrast_tiles = []
                    if image_stddev < low_contrast_stddev_threshold:
                        low_contrast_tiles = generate_tiles(
                            contrast_enhanced_luma(base),
                            tile_size,
                            stride,
                            hash_size,
                            low_contrast_min_stddev,
                            "low_contrast_autocontrast",
                        )
                        original_low_contrast_tile_count = len(low_contrast_tiles)
                        low_contrast_tiles, low_contrast_limited = limit_tiles(
                            low_contrast_tiles,
                            max_tiles_per_image,
                        )
                        if low_contrast_limited:
                            limit_records.append({
                                "path": f"{rel_path}{frame_label}",
                                "limit_type": "max_tiles_per_image",
                                "view": "low_contrast_autocontrast",
                                "available_tiles": original_low_contrast_tile_count,
                                "screened_tiles": len(low_contrast_tiles),
                                "max_tiles_per_image": max_tiles_per_image,
                            })
                    images.append({
                        "path": f"{rel_path}{frame_label}",
                        "source_file": rel_path,
                        "frame_label": frame_label or None,
                        "image": base.copy(),
                        "tiles": tiles,
                        "low_contrast_tiles": low_contrast_tiles,
                        "stddev": round(image_stddev, 3),
                    })
        except Exception as exc:  # noqa: BLE001 - unreadable files should not abort an audit.
            errors.append({"path": str(path.relative_to(root)), "error": str(exc)})

    candidates = []
    same_image_candidate_count = 0
    for image in images:
        if comparison_budget.exhausted:
            break
        hits = []
        if image["tiles"]:
            hits = scan_within_image(
                image,
                image["tiles"],
                hash_threshold,
                hash_size,
                max(ncc_threshold, within_image_ncc_threshold),
                max_region_fraction,
                within_image_min_gap,
                within_image_min_tile_hits,
                budget=comparison_budget,
            )
        if not hits and image["low_contrast_tiles"] and not comparison_budget.exhausted:
            hits = scan_within_image(
                image,
                image["low_contrast_tiles"],
                hash_threshold,
                hash_size,
                max(ncc_threshold, low_contrast_ncc_threshold),
                max_region_fraction,
                within_image_min_gap,
                within_image_min_tile_hits,
                True,
                comparison_budget,
            )
        if not hits:
            continue
        same_image_candidate_count += 1
        candidates.append(candidate_from_hits(
            root,
            evidence_dir,
            image,
            image,
            hits,
            len(candidates) + 1,
            tile_size,
            stride,
            same_image=True,
        ))

    excluded_pair_count = 0
    for i, left in enumerate(images):
        if comparison_budget.exhausted:
            break
        for right in images[i + 1:]:
            if comparison_budget.exhausted:
                break
            if undirected_pair(left["path"], right["path"]) in excluded_pairs:
                excluded_pair_count += 1
                continue
            if not left["tiles"] or not right["tiles"]:
                continue
            hits = scan_pair(
                left,
                right,
                hash_threshold,
                hash_size,
                ncc_threshold,
                max_region_fraction,
                comparison_budget,
            )
            if not hits:
                continue
            candidates.append(candidate_from_hits(
                root,
                evidence_dir,
                left,
                right,
                hits,
                len(candidates) + 1,
                tile_size,
                stride,
            ))

    if comparison_budget.exhausted:
        limit_records.append({
            "path": "local_patch_reuse",
            "limit_type": "max_total_tile_comparisons",
            "tile_comparisons_attempted": comparison_budget.used,
            "max_total_tile_comparisons": max_total_tile_comparisons,
        })
    if limit_records:
        candidates.append(coverage_gap_candidate(limit_records, len(candidates) + 1))

    return {
        "detector_name": "image.local_patch_reuse",
        "detector_version": "0.5.0",
        "input": {
            "root": str(root),
            "provenance_graph": str(provenance_path) if provenance_path else None,
            "modality_routing_enabled": True,
            "tile_size": tile_size,
            "stride": stride,
            "hash_size": hash_size,
            "hash_threshold": hash_threshold,
            "ncc_threshold": ncc_threshold,
            "min_stddev": min_stddev,
            "max_region_fraction": max_region_fraction,
            "within_image_ncc_threshold": within_image_ncc_threshold,
            "within_image_min_gap": within_image_min_gap,
            "within_image_min_tile_hits": within_image_min_tile_hits,
            "low_contrast_stddev_threshold": low_contrast_stddev_threshold,
            "low_contrast_min_stddev": low_contrast_min_stddev,
            "low_contrast_ncc_threshold": low_contrast_ncc_threshold,
            "max_tiles_per_image": max_tiles_per_image,
            "max_total_tile_comparisons": max_total_tile_comparisons,
            "ncc_backend": "numpy",
            "transforms": list(TRANSFORMS),
            "multi_frame_images": "screened_as_frame_level_items",
        },
        "images_screened": len(images),
        "panels_excluded_from_deep_scan": panels_excluded_from_deep_scan,
        "modality_conflicts": modality_conflicts,
        "candidate_pair_count": len(candidates),
        "same_image_candidate_count": same_image_candidate_count,
        "excluded_expected_traceability_pairs": excluded_pair_count,
        "tile_limit_records": limit_records,
        "tile_comparisons_attempted": comparison_budget.used,
        "comparison_budget_exhausted": comparison_budget.exhausted,
        "candidates": candidates,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_dir", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--tile-size", type=int, default=128)
    parser.add_argument("--stride", type=int, default=64)
    parser.add_argument("--hash-size", type=int, default=8)
    parser.add_argument("--hash-threshold", type=int, default=4)
    parser.add_argument("--ncc-threshold", type=float, default=0.985)
    parser.add_argument("--min-stddev", type=float, default=8.0)
    parser.add_argument("--max-region-fraction", type=float, default=0.65)
    parser.add_argument("--within-image-ncc-threshold", type=float, default=0.995)
    parser.add_argument("--within-image-min-gap", type=int, default=16)
    parser.add_argument("--within-image-min-tile-hits", type=int, default=2)
    parser.add_argument("--low-contrast-stddev-threshold", type=float, default=8.0)
    parser.add_argument("--low-contrast-min-stddev", type=float, default=8.0)
    parser.add_argument("--low-contrast-ncc-threshold", type=float, default=0.995)
    parser.add_argument("--max-tiles-per-image", type=int, default=DEFAULT_MAX_TILES_PER_IMAGE)
    parser.add_argument("--max-total-tile-comparisons", type=int, default=DEFAULT_MAX_TOTAL_TILE_COMPARISONS)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("local_patch_candidates.json"))
    args = parser.parse_args()

    root = args.image_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Image directory not found: {root}")
    output = args.output.expanduser().resolve()
    evidence_dir = (args.evidence_dir or (output.parent / "evidence" / "local_patch")).expanduser().resolve()
    result = scan(
        root,
        args.provenance.expanduser().resolve() if args.provenance else None,
        evidence_dir,
        args.tile_size,
        args.stride,
        args.hash_size,
        args.hash_threshold,
        args.ncc_threshold,
        args.min_stddev,
        args.max_region_fraction,
        args.within_image_ncc_threshold,
        args.within_image_min_gap,
        args.within_image_min_tile_hits,
        args.low_contrast_stddev_threshold,
        args.low_contrast_min_stddev,
        args.low_contrast_ncc_threshold,
        args.max_tiles_per_image,
        args.max_total_tile_comparisons,
    )
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "images_screened": result["images_screened"],
        "candidates": len(result["candidates"]),
        "same_image_candidates": result["same_image_candidate_count"],
        "excluded_expected_traceability_pairs": result["excluded_expected_traceability_pairs"],
        "errors": len(result["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
