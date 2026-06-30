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

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from detectors.image.image_io import iter_normalized_frames
from provenance.panel_modality import resolve_panel_modality_routing


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
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
    pixels = list(img.convert("L").tobytes())
    if not pixels:
        return 0.0, 0.0
    mean = sum(pixels) / len(pixels)
    variance = sum((value - mean) ** 2 for value in pixels) / len(pixels)
    return mean, math.sqrt(variance)


def normalized_cross_correlation(left: Any, right: Any) -> float:
    left_pixels = list(left.convert("L").tobytes())
    right_pixels = list(right.convert("L").tobytes())
    if len(left_pixels) != len(right_pixels) or not left_pixels:
        return 0.0
    mean_left = sum(left_pixels) / len(left_pixels)
    mean_right = sum(right_pixels) / len(right_pixels)
    numerator = 0.0
    left_energy = 0.0
    right_energy = 0.0
    for left_value, right_value in zip(left_pixels, right_pixels):
        dl = left_value - mean_left
        dr = right_value - mean_right
        numerator += dl * dr
        left_energy += dl * dl
        right_energy += dr * dr
    denominator = math.sqrt(left_energy * right_energy)
    if denominator == 0:
        return 1.0 if left_pixels == right_pixels else 0.0
    return max(-1.0, min(1.0, numerator / denominator))


def tile_hashes(tile: Any, hash_size: int) -> dict[str, int]:
    return {
        "average_hash": average_hash(tile, hash_size),
        "difference_hash": difference_hash(tile, hash_size),
    }


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
            _, stddev = luma_stats(tile)
            if stddev < min_stddev:
                continue
            tiles.append({
                "bounds": bounds,
                "image": tile,
                "hashes": tile_hashes(tile, hash_size),
                "stddev": round(stddev, 3),
                "view": view_name,
                "tile_size": tile_size,
            })
    return tiles


def best_tile_match(
    left_tile: dict[str, Any],
    right_tile: dict[str, Any],
    hash_threshold: int,
    hash_size: int,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for transform_name in TRANSFORMS:
        right_img = transformed(right_tile["image"], transform_name)
        right_hashes = tile_hashes(right_img, hash_size)
        distances = {
            method: hamming(left_tile["hashes"][method], right_hashes[method])
            for method in left_tile["hashes"]
        }
        distance = min(distances.values())
        if distance > hash_threshold:
            continue
        score = normalized_cross_correlation(left_tile["image"], right_img)
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
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen_regions: set[tuple[tuple[int, int, int, int], tuple[int, int, int, int], str]] = set()
    for left_tile in left["tiles"]:
        for right_tile in right["tiles"]:
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
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen_regions: set[tuple[tuple[int, int, int, int], tuple[int, int, int, int], str]] = set()
    for left_index, left_tile in enumerate(tiles):
        for right_tile in tiles[left_index + 1:]:
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
            )
        if not hits and image["low_contrast_tiles"]:
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
        for right in images[i + 1:]:
            if undirected_pair(left["path"], right["path"]) in excluded_pairs:
                excluded_pair_count += 1
                continue
            if not left["tiles"] or not right["tiles"]:
                continue
            hits = scan_pair(left, right, hash_threshold, hash_size, ncc_threshold, max_region_fraction)
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

    return {
        "detector_name": "image.local_patch_reuse",
        "detector_version": "0.4.1",
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
            "transforms": list(TRANSFORMS),
            "multi_frame_images": "screened_as_frame_level_items",
        },
        "images_screened": len(images),
        "panels_excluded_from_deep_scan": panels_excluded_from_deep_scan,
        "modality_conflicts": modality_conflicts,
        "candidate_pair_count": len(candidates),
        "same_image_candidate_count": same_image_candidate_count,
        "excluded_expected_traceability_pairs": excluded_pair_count,
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
