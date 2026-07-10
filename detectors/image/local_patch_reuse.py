#!/usr/bin/env python3
"""Local image patch reuse detector with provenance-aware pair exclusion."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]

from detectors.image.image_io import iter_normalized_frames
from provenance.panel_modality import resolve_panel_modality_routing


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
DEFAULT_MAX_TILES_PER_IMAGE = 2000
DEFAULT_MAX_TOTAL_TILE_COMPARISONS = 20_000_000
GRAPHIC_TILE_SUPPRESSION_SCOPE = "figure_panels_only"
COMPOSITE_PANEL_CUTTER_SCOPE = "figure_panels_only"
DEFAULT_MAX_COMPOSITE_SUBPANELS = 64
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

    transpose_name = TRANSFORMS[transform_name]
    assert transpose_name is not None
    return img.transpose(getattr(Image.Transpose, transpose_name))


def collect_images(root: Path) -> list[Path]:
    return [
        path for path in sorted(root.rglob("*"))
        if not path.is_symlink() and path.is_file() and path.suffix.lower() in IMAGE_EXTS
    ]


def undirected_pair(left: str, right: str) -> tuple[str, str]:
    first, second = sorted((left, right))
    return first, second


def provenance_comparison_path(image: dict[str, Any]) -> str:
    return str(image.get("provenance_path") or image.get("path") or "")


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
        if not is_authoritative_traceability_edge(edge):
            continue
        source_path = str(edge.get("source_path", ""))
        target_path = str(edge.get("target_path", ""))
        roles = {role_from_path(source_path), role_from_path(target_path)}
        if roles == {"figure_panel", "raw_image"} or roles == {"figure_panel", "source_data"}:
            pairs.add(undirected_pair(source_path, target_path))
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


def graphic_tile_profile(tile_rgb: Any, include_texture: bool = False) -> dict[str, float]:
    rgb = np.asarray(tile_rgb.convert("RGB"), dtype=np.float32)
    if rgb.size == 0:
        return {
            "near_white_share": 0.0,
            "ink_share": 0.0,
            "dark_share": 0.0,
            "colored_share": 0.0,
            "edge_share": 0.0,
            "edge_to_ink_ratio": 0.0,
            "quantized_unique_colors": 0.0,
            "vertical_stripe_ratio": 0.0,
        }
    luma = (0.299 * rgb[:, :, 0]) + (0.587 * rgb[:, :, 1]) + (0.114 * rgb[:, :, 2])
    near_white_share = float(np.mean(luma >= 238.0))
    ink_share = float(np.mean(luma < 238.0))
    dark_share = float(np.mean(luma <= 96.0))
    channel_range = np.max(rgb, axis=2) - np.min(rgb, axis=2)
    colored_share = float(np.mean(channel_range >= 35.0))
    quantized_unique_colors = 0.0
    vertical_stripe_ratio = 0.0
    if include_texture:
        quantized = (rgb.astype(np.uint32) // 32).reshape(-1, 3)
        packed = (quantized[:, 0] * 64) + (quantized[:, 1] * 8) + quantized[:, 2]
        quantized_unique_colors = float(np.unique(packed).size)
        col_variance = float(np.var(np.mean(luma, axis=0)))
        row_variance = float(np.var(np.mean(luma, axis=1)))
        vertical_stripe_ratio = col_variance / max(row_variance, 1.0)
    if luma.shape[0] < 2 or luma.shape[1] < 2:
        edge_share = 0.0
    else:
        horizontal = np.abs(np.diff(luma, axis=1))
        vertical = np.abs(np.diff(luma, axis=0))
        edge_pixels = (
            int(np.count_nonzero(horizontal >= 38.0))
            + int(np.count_nonzero(vertical >= 38.0))
        )
        edge_denominator = horizontal.size + vertical.size
        edge_share = float(edge_pixels / max(1, edge_denominator))
    return {
        "near_white_share": near_white_share,
        "ink_share": ink_share,
        "dark_share": dark_share,
        "colored_share": colored_share,
        "edge_share": edge_share,
        "edge_to_ink_ratio": edge_share / max(ink_share, 0.001),
        "quantized_unique_colors": quantized_unique_colors,
        "vertical_stripe_ratio": vertical_stripe_ratio,
    }


def chart_text_axis_suppression_reason(tile_rgb: Any, stddev: float) -> str | None:
    """Identify presentation-layer tiles before local biological-image reuse screening.

    This intentionally targets sparse white-background chart/text/axis regions in exported
    figure panels. Broad dark content is retained so white-background blots are less likely
    to be suppressed.
    """

    profile = graphic_tile_profile(tile_rgb, include_texture=True)
    if (
        profile["quantized_unique_colors"] <= 10
        and profile["edge_share"] <= 0.07
        and profile["vertical_stripe_ratio"] >= 6.0
        and stddev >= 32.0
    ):
        return "solid_vertical_color_bar_region"
    if (
        profile["near_white_share"] >= 0.60
        and profile["colored_share"] >= 0.12
        and profile["quantized_unique_colors"] <= 48
        and profile["edge_share"] <= 0.08
        and stddev >= 30.0
    ):
        return "solid_color_legend_region"
    if profile["near_white_share"] >= 0.98 and profile["ink_share"] <= 0.04:
        return "blank_or_sparse_presentation_region"
    if (
        profile["near_white_share"] >= 0.72
        and profile["ink_share"] <= 0.30
        and profile["dark_share"] <= 0.12
        and profile["colored_share"] <= 0.18
        and profile["edge_to_ink_ratio"] >= 0.10
        and stddev <= 85.0
    ):
        return "chart_text_axis_region"
    return None


def rounded_profile(profile: dict[str, float]) -> dict[str, float]:
    return {key: round(float(value), 4) for key, value in sorted(profile.items())}


def region_profile(img: Any, include_texture: bool = True) -> dict[str, float]:
    profile = graphic_tile_profile(img, include_texture=include_texture)
    _, stddev = luma_stats(img)
    profile["stddev"] = float(stddev)
    return profile


def region_is_image_like(img: Any, min_dimension: int) -> tuple[bool, str, dict[str, float]]:
    width, height = img.size
    profile = region_profile(img)
    if width < min_dimension or height < min_dimension:
        return False, "too_small_for_local_patch_screening", profile
    suppression_reason = chart_text_axis_suppression_reason(img, profile["stddev"])
    if suppression_reason in {"solid_vertical_color_bar_region", "solid_color_legend_region"}:
        return False, suppression_reason, profile
    if suppression_reason:
        if profile["dark_share"] < 0.06 and profile["colored_share"] < 0.14:
            return False, "presentation_like_chart_text_axis_region", profile
    if profile["near_white_share"] < 0.72 and profile["ink_share"] >= 0.22:
        return True, "dense_image_like_region", profile
    if profile["colored_share"] >= 0.18 and profile["ink_share"] >= 0.10:
        return True, "colored_image_like_region", profile
    if profile["dark_share"] >= 0.06 and profile["ink_share"] >= 0.08:
        return True, "dark_band_or_photo_region", profile
    if (
        profile["stddev"] >= 24.0
        and profile["ink_share"] >= 0.16
        and profile["edge_to_ink_ratio"] <= 0.45
    ):
        return True, "textured_image_like_region", profile
    return False, "presentation_or_low_information_region", profile


def block_has_image_content(block: Any) -> bool:
    profile = region_profile(block, include_texture=False)
    if profile["near_white_share"] < 0.68 and profile["ink_share"] >= 0.24:
        return True
    if profile["colored_share"] >= 0.20 and profile["ink_share"] >= 0.08:
        return True
    if profile["dark_share"] >= 0.10 and profile["ink_share"] >= 0.10:
        return True
    return (
        profile["stddev"] >= 28.0
        and profile["ink_share"] >= 0.16
        and profile["edge_to_ink_ratio"] <= 0.45
    )


def dilate_mask(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    result = mask.astype(bool)
    for _ in range(iterations):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        expanded = np.zeros_like(result, dtype=bool)
        for y_offset in range(3):
            for x_offset in range(3):
                expanded |= padded[y_offset:y_offset + result.shape[0], x_offset:x_offset + result.shape[1]]
        result = expanded
    return result


def connected_components(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    visited = np.zeros_like(mask, dtype=bool)
    components: list[tuple[int, int, int, int, int]] = []
    rows, cols = mask.shape
    for row in range(rows):
        for col in range(cols):
            if visited[row, col] or not mask[row, col]:
                continue
            stack = [(row, col)]
            visited[row, col] = True
            min_row = max_row = row
            min_col = max_col = col
            count = 0
            while stack:
                current_row, current_col = stack.pop()
                count += 1
                min_row = min(min_row, current_row)
                max_row = max(max_row, current_row)
                min_col = min(min_col, current_col)
                max_col = max(max_col, current_col)
                for next_row in range(max(0, current_row - 1), min(rows, current_row + 2)):
                    for next_col in range(max(0, current_col - 1), min(cols, current_col + 2)):
                        if visited[next_row, next_col] or not mask[next_row, next_col]:
                            continue
                        visited[next_row, next_col] = True
                        stack.append((next_row, next_col))
            components.append((min_col, min_row, max_col + 1, max_row + 1, count))
    return components


def expand_bounds(
    bounds: tuple[int, int, int, int],
    padding: int,
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    width, height = image_size
    return (
        max(0, bounds[0] - padding),
        max(0, bounds[1] - padding),
        min(width, bounds[2] + padding),
        min(height, bounds[3] + padding),
    )


def bounds_close_or_overlap(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
    padding: int,
) -> bool:
    return bounds_overlap(left, right, padding)


def merge_nearby_bounds(
    bounds_list: list[tuple[int, int, int, int]],
    padding: int,
) -> list[tuple[int, int, int, int]]:
    merged = list(bounds_list)
    changed = True
    while changed:
        changed = False
        next_bounds: list[tuple[int, int, int, int]] = []
        while merged:
            current = merged.pop(0)
            match_index = None
            for idx, other in enumerate(merged):
                if bounds_close_or_overlap(current, other, padding):
                    match_index = idx
                    break
            if match_index is None:
                next_bounds.append(current)
                continue
            other = merged.pop(match_index)
            merged.append((
                min(current[0], other[0]),
                min(current[1], other[1]),
                max(current[2], other[2]),
                max(current[3], other[3]),
            ))
            changed = True
        merged = next_bounds
    return sorted(merged, key=lambda item: (item[1], item[0], item[3] - item[1], item[2] - item[0]))


def low_signal_runs(values: np.ndarray, threshold: float, min_run: int) -> list[tuple[int, int]]:
    runs = []
    start: int | None = None
    for idx, value in enumerate(values):
        if float(value) <= threshold:
            if start is None:
                start = idx
        elif start is not None:
            if idx - start >= min_run:
                runs.append((start, idx))
            start = None
    if start is not None and len(values) - start >= min_run:
        runs.append((start, len(values)))
    return runs


def split_bounds_once_by_gutter(
    img: Any,
    bounds: tuple[int, int, int, int],
    min_dimension: int,
) -> list[tuple[int, int, int, int]]:
    crop = img.crop(bounds).convert("RGB")
    rgb = np.asarray(crop, dtype=np.float32)
    if rgb.size == 0:
        return [bounds]
    luma = (0.299 * rgb[:, :, 0]) + (0.587 * rgb[:, :, 1]) + (0.114 * rgb[:, :, 2])
    channel_range = np.max(rgb, axis=2) - np.min(rgb, axis=2)
    foreground = (luma < 245.0) | (channel_range >= 35.0)
    col_density = np.mean(foreground, axis=0)
    row_density = np.mean(foreground, axis=1)
    width, height = crop.size
    min_gutter = max(10, min_dimension // 4)
    vertical_runs = [
        run for run in low_signal_runs(col_density, 0.012, min_gutter)
        if run[0] >= min_dimension and width - run[1] >= min_dimension
    ]
    horizontal_runs = [
        run for run in low_signal_runs(row_density, 0.012, min_gutter)
        if run[0] >= min_dimension and height - run[1] >= min_dimension
    ]
    best_vertical = max(vertical_runs, key=lambda item: item[1] - item[0], default=None)
    best_horizontal = max(horizontal_runs, key=lambda item: item[1] - item[0], default=None)
    vertical_width = (best_vertical[1] - best_vertical[0]) if best_vertical else 0
    horizontal_height = (best_horizontal[1] - best_horizontal[0]) if best_horizontal else 0
    if vertical_width <= 0 and horizontal_height <= 0:
        return [bounds]
    if vertical_width >= horizontal_height:
        assert best_vertical is not None
        split_x = bounds[0] + ((best_vertical[0] + best_vertical[1]) // 2)
        return [(bounds[0], bounds[1], split_x, bounds[3]), (split_x, bounds[1], bounds[2], bounds[3])]
    assert best_horizontal is not None
    split_y = bounds[1] + ((best_horizontal[0] + best_horizontal[1]) // 2)
    return [(bounds[0], bounds[1], bounds[2], split_y), (bounds[0], split_y, bounds[2], bounds[3])]


def split_bounds_by_gutters(
    img: Any,
    bounds: tuple[int, int, int, int],
    min_dimension: int,
    max_parts: int = 16,
) -> list[tuple[int, int, int, int]]:
    pending = [bounds]
    changed = True
    while changed and len(pending) < max_parts:
        changed = False
        next_bounds: list[tuple[int, int, int, int]] = []
        for item in pending:
            parts = split_bounds_once_by_gutter(img, item, min_dimension)
            if len(parts) > 1:
                changed = True
            next_bounds.extend(parts)
        pending = next_bounds
    return sorted(pending, key=lambda item: (item[1], item[0]))


def trim_bounds_to_foreground(
    img: Any,
    bounds: tuple[int, int, int, int],
    padding: int,
) -> tuple[int, int, int, int]:
    crop = img.crop(bounds).convert("RGB")
    rgb = np.asarray(crop, dtype=np.float32)
    if rgb.size == 0:
        return bounds
    luma = (0.299 * rgb[:, :, 0]) + (0.587 * rgb[:, :, 1]) + (0.114 * rgb[:, :, 2])
    channel_range = np.max(rgb, axis=2) - np.min(rgb, axis=2)
    foreground = (luma < 245.0) | (channel_range >= 35.0)
    coords = np.argwhere(foreground)
    if coords.size == 0:
        return bounds
    min_y, min_x = coords.min(axis=0)
    max_y, max_x = coords.max(axis=0) + 1
    trimmed = (
        bounds[0] + int(min_x),
        bounds[1] + int(min_y),
        bounds[0] + int(max_x),
        bounds[1] + int(max_y),
    )
    return expand_bounds(trimmed, padding, img.size)


def block_size_for_panel_cut(width: int, height: int) -> int:
    return max(12, min(32, max(1, min(width, height) // 48)))


def cut_image_like_subpanels(
    img: Any,
    tile_size: int,
    max_panels: int = DEFAULT_MAX_COMPOSITE_SUBPANELS,
) -> dict[str, Any]:
    width, height = img.size
    min_dimension = max(64, min(tile_size, min(width, height)))
    whole_ok, whole_reason, whole_profile = region_is_image_like(img, min_dimension)
    block_size = block_size_for_panel_cut(width, height)
    rows = math.ceil(height / block_size)
    cols = math.ceil(width / block_size)
    mask = np.zeros((rows, cols), dtype=bool)
    for row in range(rows):
        for col in range(cols):
            bounds = (
                col * block_size,
                row * block_size,
                min(width, (col + 1) * block_size),
                min(height, (row + 1) * block_size),
            )
            if block_has_image_content(img.crop(bounds)):
                mask[row, col] = True
    mask = dilate_mask(mask, 1)
    component_bounds = []
    for min_col, min_row, max_col, max_row, count in connected_components(mask):
        if count < 2:
            continue
        bounds = (
            min_col * block_size,
            min_row * block_size,
            min(width, max_col * block_size),
            min(height, max_row * block_size),
        )
        component_bounds.append(expand_bounds(bounds, block_size, (width, height)))
    merged_bounds = merge_nearby_bounds(component_bounds, max(4, block_size // 2))
    split_bounds: list[tuple[int, int, int, int]] = []
    for bounds in merged_bounds:
        split_bounds.extend(split_bounds_by_gutters(img, bounds, min_dimension))
    merged_bounds = sorted(split_bounds, key=lambda item: (item[1], item[0]))

    panels: list[dict[str, Any]] = []
    skipped_regions: list[dict[str, Any]] = []
    for bounds in merged_bounds:
        bounds = trim_bounds_to_foreground(img, bounds, max(4, block_size // 2))
        crop = img.crop(bounds)
        ok, reason, profile = region_is_image_like(crop, min_dimension)
        record = {
            "bounds": bounds_to_region(bounds),
            "classification": reason,
            "profile": rounded_profile(profile),
        }
        if ok:
            panels.append({
                **record,
                "image": crop,
                "is_full_image": False,
            })
        else:
            skipped_regions.append(record)

    whole_area = max(1, width * height)
    if len(panels) == 1:
        panel_area = region_area(panels[0]["bounds"])
        if whole_ok and panel_area / whole_area >= 0.72:
            panels = [{
                "bounds": bounds_to_region((0, 0, width, height)),
                "classification": f"whole_figure_{whole_reason}",
                "profile": rounded_profile(whole_profile),
                "image": img.copy(),
                "is_full_image": True,
            }]
    elif not panels and whole_ok:
        panels = [{
            "bounds": bounds_to_region((0, 0, width, height)),
            "classification": f"whole_figure_{whole_reason}",
            "profile": rounded_profile(whole_profile),
            "image": img.copy(),
            "is_full_image": True,
        }]

    truncated = False
    if len(panels) > max_panels:
        truncated = True
        panels = sorted(panels, key=lambda item: region_area(item["bounds"]), reverse=True)[:max_panels]
        panels = sorted(panels, key=lambda item: (item["bounds"]["y"], item["bounds"]["x"]))

    if not panels and not skipped_regions:
        skipped_regions.append({
            "bounds": bounds_to_region((0, 0, width, height)),
            "classification": "no_image_like_regions_detected",
            "profile": rounded_profile(whole_profile),
        })

    serializable_panels = [
        {
            "panel_id": f"panel_{idx:03d}",
            "bounds": panel["bounds"],
            "classification": panel["classification"],
            "profile": panel["profile"],
            "is_full_image": bool(panel.get("is_full_image")),
        }
        for idx, panel in enumerate(panels, start=1)
    ]
    for idx, panel in enumerate(panels, start=1):
        panel["panel_id"] = f"panel_{idx:03d}"

    return {
        "panels": panels,
        "record": {
            "block_size": block_size,
            "image_like_panels": len(panels),
            "presentation_regions_skipped": len(skipped_regions),
            "regions": serializable_panels,
            "skipped_regions": skipped_regions[:20],
            "truncated": truncated,
            "scope": COMPOSITE_PANEL_CUTTER_SCOPE,
        },
    }


def generate_tiles(
    img: Any,
    tile_size: int,
    stride: int,
    hash_size: int,
    min_stddev: float,
    view_name: str = "luma",
    suppress_graphic_tiles: bool = False,
    suppression_stats: dict[str, int] | None = None,
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
            tile_rgb = img.crop(bounds).convert("RGB")
            tile = tile_rgb.convert("L")
            tile_array = luma_array(tile)
            _, stddev = float(np.mean(tile_array)), float(np.std(tile_array))
            if stddev < min_stddev:
                continue
            if suppress_graphic_tiles:
                suppression_reason = chart_text_axis_suppression_reason(tile_rgb, stddev)
                if suppression_reason:
                    if suppression_stats is not None:
                        suppression_stats["total"] = int(suppression_stats.get("total", 0)) + 1
                        suppression_stats[suppression_reason] = (
                            int(suppression_stats.get(suppression_reason, 0)) + 1
                        )
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


def region_in_source_coordinates(item: dict[str, Any], region: dict[str, int]) -> dict[str, int]:
    panel_region = item.get("panel_region") or {}
    return {
        "x": int(region["x"]) + int(panel_region.get("x", 0) or 0),
        "y": int(region["y"]) + int(panel_region.get("y", 0) or 0),
        "width": int(region["width"]),
        "height": int(region["height"]),
    }


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
        "left_provenance_path": provenance_comparison_path(left),
        "right_provenance_path": provenance_comparison_path(right),
        "left_source_file": left.get("source_file"),
        "right_source_file": right.get("source_file"),
        "left_panel_id": left.get("panel_id"),
        "right_panel_id": right.get("panel_id"),
        "left_panel_region": left.get("panel_region"),
        "right_panel_region": right.get("panel_region"),
        "left_panel_classification": left.get("panel_classification"),
        "right_panel_classification": right.get("panel_classification"),
        "similarity_scope": similarity_scope,
        "same_image": same_image,
        "region_a": region_a,
        "region_b": region_b,
        "coordinate_space": "panel_local_pixels" if left.get("panel_id") or right.get("panel_id") else "source_image_pixels",
        "left_source_region": region_in_source_coordinates(left, region_a),
        "right_source_region": region_in_source_coordinates(right, region_b),
        "left_source_dimensions": left.get("source_dimensions"),
        "right_source_dimensions": right.get("source_dimensions"),
        "tile_hit_coordinate_space": "panel_local_pixels",
        "coordinate_note": "region_a/region_b and tile hits are local to the screening unit; *_source_region maps them to the supplied source image.",
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
    images: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    limit_records: list[dict[str, Any]] = []
    comparison_budget = ComparisonBudget(max_total_tile_comparisons)
    panels_excluded_from_deep_scan: list[dict[str, Any]] = []
    modality_conflicts = list(routing.modality_conflicts)
    graphic_tile_suppression_records: list[dict[str, Any]] = []
    graphic_tiles_suppressed = 0
    composite_panel_cut_records: list[dict[str, Any]] = []
    composite_image_like_panels_screened = 0
    composite_presentation_regions_skipped = 0

    def record_graphic_suppression(path_label: str, view: str, stats: dict[str, int]) -> None:
        nonlocal graphic_tiles_suppressed
        suppressed = int(stats.get("total", 0) or 0)
        if suppressed <= 0:
            return
        reasons = {
            key: int(value)
            for key, value in sorted(stats.items())
            if key != "total" and int(value) > 0
        }
        graphic_tiles_suppressed += suppressed
        graphic_tile_suppression_records.append({
            "path": path_label,
            "view": view,
            "suppressed_tiles": suppressed,
            "reasons": reasons,
            "scope": GRAPHIC_TILE_SUPPRESSION_SCOPE,
        })

    for path in image_paths:
        rel_path = str(path.relative_to(root))
        try:
            with Image.open(path) as img:
                for frame_label, base in iter_normalized_frames(img):
                    source_label = f"{rel_path}{frame_label}"
                    suppress_graphic_tiles = rel_path.startswith("figures/")
                    screening_units: list[dict[str, Any]] = []
                    if rel_path.startswith("figures/"):
                        cut_result = cut_image_like_subpanels(base, tile_size)
                        record = {
                            "source_path": source_label,
                            **cut_result["record"],
                        }
                        composite_panel_cut_records.append(record)
                        composite_presentation_regions_skipped += int(record["presentation_regions_skipped"])
                        cut_panels = list(cut_result["panels"])
                        if rel_path in excluded_panel_paths:
                            has_distinct_subpanels = any(not panel.get("is_full_image") for panel in cut_panels)
                            if has_distinct_subpanels:
                                record["modality_exclusion_deferred_to_composite_cutter"] = True
                            else:
                                cut_panels = []
                                panels_excluded_from_deep_scan.extend(
                                    item for item in routing.excluded_panels if item.get("panel") == rel_path
                                )
                        composite_image_like_panels_screened += len(cut_panels)
                        for panel in cut_panels:
                            is_full_image = bool(panel.get("is_full_image"))
                            panel_id = str(panel["panel_id"])
                            screening_units.append({
                                "path": source_label if is_full_image else f"{source_label}::{panel_id}",
                                "provenance_path": rel_path,
                                "source_file": rel_path,
                                "frame_label": frame_label or None,
                                "panel_id": None if is_full_image else panel_id,
                                "panel_region": None if is_full_image else panel["bounds"],
                                "panel_classification": panel["classification"],
                                "source_dimensions": {"width": base.size[0], "height": base.size[1]},
                                "image": panel["image"],
                            })
                    else:
                        screening_units.append({
                            "path": source_label,
                            "provenance_path": source_label,
                            "source_file": rel_path,
                            "frame_label": frame_label or None,
                            "panel_id": None,
                            "panel_region": None,
                            "panel_classification": "full_non_figure_image",
                            "source_dimensions": {"width": base.size[0], "height": base.size[1]},
                            "image": base,
                        })

                    for unit in screening_units:
                        path_label = str(unit["path"])
                        unit_image = unit["image"]
                        luma_suppression_stats: dict[str, int] = {}
                        tiles = generate_tiles(
                            unit_image,
                            tile_size,
                            stride,
                            hash_size,
                            min_stddev,
                            "luma",
                            suppress_graphic_tiles,
                            luma_suppression_stats,
                        )
                        record_graphic_suppression(path_label, "luma", luma_suppression_stats)
                        original_tile_count = len(tiles)
                        tiles, tiles_limited = limit_tiles(tiles, max_tiles_per_image)
                        if tiles_limited:
                            limit_records.append({
                                "path": path_label,
                                "limit_type": "max_tiles_per_image",
                                "view": "luma",
                                "available_tiles": original_tile_count,
                                "screened_tiles": len(tiles),
                                "max_tiles_per_image": max_tiles_per_image,
                            })
                        _, image_stddev = luma_stats(unit_image)
                        low_contrast_tiles = []
                        if image_stddev < low_contrast_stddev_threshold:
                            low_contrast_suppression_stats: dict[str, int] = {}
                            low_contrast_tiles = generate_tiles(
                                contrast_enhanced_luma(unit_image),
                                tile_size,
                                stride,
                                hash_size,
                                low_contrast_min_stddev,
                                "low_contrast_autocontrast",
                                suppress_graphic_tiles,
                                low_contrast_suppression_stats,
                            )
                            record_graphic_suppression(
                                path_label,
                                "low_contrast_autocontrast",
                                low_contrast_suppression_stats,
                            )
                            original_low_contrast_tile_count = len(low_contrast_tiles)
                            low_contrast_tiles, low_contrast_limited = limit_tiles(
                                low_contrast_tiles,
                                max_tiles_per_image,
                            )
                            if low_contrast_limited:
                                limit_records.append({
                                    "path": path_label,
                                    "limit_type": "max_tiles_per_image",
                                    "view": "low_contrast_autocontrast",
                                    "available_tiles": original_low_contrast_tile_count,
                                    "screened_tiles": len(low_contrast_tiles),
                                    "max_tiles_per_image": max_tiles_per_image,
                                })
                        images.append({
                            "path": path_label,
                            "provenance_path": str(unit["provenance_path"]),
                            "source_file": str(unit["source_file"]),
                            "frame_label": unit["frame_label"],
                            "panel_id": unit["panel_id"],
                            "panel_region": unit["panel_region"],
                            "panel_classification": unit["panel_classification"],
                            "source_dimensions": unit["source_dimensions"],
                            "image": unit_image.copy(),
                            "tiles": tiles,
                            "low_contrast_tiles": low_contrast_tiles,
                            "stddev": round(image_stddev, 3),
                        })
        except Exception as exc:  # noqa: BLE001 - unreadable files should not abort an audit.
            errors.append({"path": str(path.relative_to(root)), "error": str(exc)})

    candidates: list[dict[str, Any]] = []
    same_image_candidate_count = 0
    excluded_pair_count = 0
    intra_stack_pairs_skipped = 0
    for i, left in enumerate(images):
        if comparison_budget.exhausted:
            break
        for right in images[i + 1:]:
            if comparison_budget.exhausted:
                break
            if (
                left["source_file"] == right["source_file"]
                and left.get("frame_label")
                and right.get("frame_label")
                and left.get("frame_label") != right.get("frame_label")
            ):
                intra_stack_pairs_skipped += 1
                continue
            if undirected_pair(provenance_comparison_path(left), provenance_comparison_path(right)) in excluded_pairs:
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
        "detector_version": "0.7.0",
        "input": {
            "root": str(root),
            "provenance_graph": str(provenance_path) if provenance_path else None,
            "modality_routing_enabled": True,
            "composite_panel_cutter_enabled": True,
            "composite_panel_cutter_scope": COMPOSITE_PANEL_CUTTER_SCOPE,
            "chart_text_axis_tile_suppression_enabled": True,
            "chart_text_axis_tile_suppression_scope": GRAPHIC_TILE_SUPPRESSION_SCOPE,
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
        "composite_image_like_panels_screened": composite_image_like_panels_screened,
        "composite_presentation_regions_skipped": composite_presentation_regions_skipped,
        "composite_panel_cut_records": composite_panel_cut_records,
        "graphic_tiles_suppressed": graphic_tiles_suppressed,
        "graphic_tile_suppression_records": graphic_tile_suppression_records,
        "candidate_pair_count": len(candidates),
        "same_image_candidate_count": same_image_candidate_count,
        "excluded_expected_traceability_pairs": excluded_pair_count,
        "intra_stack_pairs_skipped": intra_stack_pairs_skipped,
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
        "composite_image_like_panels_screened": result["composite_image_like_panels_screened"],
        "composite_presentation_regions_skipped": result["composite_presentation_regions_skipped"],
        "graphic_tiles_suppressed": result["graphic_tiles_suppressed"],
        "errors": len(result["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
