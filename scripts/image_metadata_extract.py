#!/usr/bin/env python3
"""Extract image frame/channel/Z-stack metadata for intake coverage.

This is an intake helper, not an image-integrity detector. It records whether
supplied image files expose OME/TIFF-style metadata that can support manual
review of channel, frame, or Z-stack relationships.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Any


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
TIFF_TAGS = {
    270: "image_description",
    305: "software",
    306: "date_time",
    315: "artist",
    33432: "copyright",
}


def relpath(package: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(package.resolve()).as_posix()
    except ValueError:
        return path.name


def image_files(package: Path) -> list[Path]:
    return sorted(
        path
        for path in package.rglob("*")
        if not path.is_symlink() and path.is_file() and path.suffix.lower() in IMAGE_EXTS
    )


def clean_text(value: Any, limit: int = 4000) -> str:
    text = str(value or "").replace("\x00", "").strip()
    if len(text) > limit:
        return text[:limit] + "...[truncated]"
    return text


def tiff_tags(img: Any) -> dict[str, str]:
    tags: dict[str, str] = {}
    tag_source = getattr(img, "tag_v2", None) or getattr(img, "tag", None)
    if not tag_source:
        return tags
    for tag_id, name in TIFF_TAGS.items():
        try:
            value = tag_source.get(tag_id)
        except Exception:  # noqa: BLE001 - Pillow tag readers vary by format.
            value = None
        if value is not None:
            tags[name] = clean_text(value)
    return tags


def parse_ome_xml(description: str) -> dict[str, Any]:
    if not description or "<OME" not in description:
        return {}
    try:
        root = ET.fromstring(description)
    except ET.ParseError as exc:
        return {"parse_error": str(exc)}

    def local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    pixels = None
    for element in root.iter():
        if local_name(element.tag) == "Pixels":
            pixels = element
            break
    if pixels is None:
        return {"parse_error": "OME XML did not contain a Pixels element"}

    attrs = pixels.attrib
    channels = []
    for element in pixels:
        if local_name(element.tag) != "Channel":
            continue
        channels.append({
            "id": element.attrib.get("ID", ""),
            "name": element.attrib.get("Name", ""),
            "fluor": element.attrib.get("Fluor", ""),
            "emission_wavelength": element.attrib.get("EmissionWavelength", ""),
        })

    def int_attr(name: str) -> int | None:
        value = attrs.get(name)
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    return {
        "dimension_order": attrs.get("DimensionOrder", ""),
        "pixel_type": attrs.get("Type", ""),
        "size_x": int_attr("SizeX"),
        "size_y": int_attr("SizeY"),
        "size_c": int_attr("SizeC"),
        "size_z": int_attr("SizeZ"),
        "size_t": int_attr("SizeT"),
        "physical_size_x": attrs.get("PhysicalSizeX", ""),
        "physical_size_y": attrs.get("PhysicalSizeY", ""),
        "channels": channels,
    }


def metadata_for_image(package: Path, path: Path) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    try:
        from PIL import Image

        with Image.open(path) as img:
            n_frames = int(getattr(img, "n_frames", 1) or 1)
            tags = tiff_tags(img)
            description = tags.get("image_description", "")
            ome = parse_ome_xml(description)
            size_c = ome.get("size_c") if isinstance(ome, dict) else None
            size_z = ome.get("size_z") if isinstance(ome, dict) else None
            size_t = ome.get("size_t") if isinstance(ome, dict) else None
            channels = ome.get("channels", []) if isinstance(ome, dict) else []
            has_ome = bool(ome) and "parse_error" not in ome
            channel_count = size_c if isinstance(size_c, int) else (len(channels) if channels else None)
            z_count = size_z if isinstance(size_z, int) else None
            metadata_review = bool(n_frames > 1 and not has_ome)
            record = {
                "path": relpath(package, path),
                "format": str(getattr(img, "format", "") or ""),
                "mode": str(getattr(img, "mode", "") or ""),
                "width": int(img.width),
                "height": int(img.height),
                "n_frames": n_frames,
                "is_multiframe": n_frames > 1,
                "metadata_status": "ome_metadata_detected" if has_ome else "generic_image_metadata_only",
                "channel_count": channel_count,
                "z_stack_count": z_count,
                "timepoint_count": size_t if isinstance(size_t, int) else None,
                "has_ome_xml": has_ome,
                "ome_metadata": ome,
                "tiff_tags": tags,
                "microscopy_hints": {
                    "possible_multichannel": bool((channel_count or 0) > 1),
                    "possible_z_stack": bool((z_count or 0) > 1),
                    "possible_time_series": bool((size_t or 0) > 1),
                    "multiframe_without_structured_metadata": metadata_review,
                },
                "manual_review_note": (
                    "Multi-frame image lacks parseable OME channel/Z/T metadata; review acquisition metadata manually."
                    if metadata_review
                    else ""
                ),
            }
            if isinstance(ome, dict) and ome.get("parse_error"):
                record["metadata_status"] = "ome_metadata_parse_error"
                record["manual_review_note"] = "OME-like metadata could not be parsed; review acquisition metadata manually."
            return record, None
    except Exception as exc:  # noqa: BLE001 - intake must surface unreadable files.
        return None, {
            "path": relpath(package, path),
            "error": f"{type(exc).__name__}: {exc}",
        }


def build_payload(package: Path) -> dict[str, Any]:
    files = image_files(package)
    images = []
    errors = []
    for path in files:
        record, error = metadata_for_image(package, path)
        if record is not None:
            images.append(record)
        if error is not None:
            errors.append(error)

    totals = {
        "image_files": len(files),
        "readable_images": len(images),
        "unreadable_images": len(errors),
        "multiframe_images": sum(1 for item in images if item.get("is_multiframe")),
        "ome_metadata_files": sum(1 for item in images if item.get("has_ome_xml")),
        "channel_metadata_files": sum(1 for item in images if item.get("channel_count")),
        "z_stack_metadata_files": sum(1 for item in images if int(item.get("z_stack_count") or 0) > 1),
        "manual_metadata_review_files": sum(
            1
            for item in images
            if (item.get("microscopy_hints") or {}).get("multiframe_without_structured_metadata")
            or item.get("metadata_status") == "ome_metadata_parse_error"
        ),
    }
    return {
        "schema_version": "0.1.0",
        "extractor": "scripts.image_metadata_extract",
        "scope_note": (
            "Image metadata intake records frame/channel/Z/T metadata when available. "
            "It is not an authenticity check and does not determine whether same-field or same-channel explanations are valid."
        ),
        "input": {
            "image_files": len(files),
        },
        "totals": totals,
        "images": images,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path, default=Path("image_metadata.json"))
    args = parser.parse_args()
    package = args.package.expanduser().resolve()
    output = args.output.expanduser().resolve()
    payload = build_payload(package)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "image_files": payload["totals"]["image_files"],
        "ome_metadata_files": payload["totals"]["ome_metadata_files"],
        "multiframe_images": payload["totals"]["multiframe_images"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
