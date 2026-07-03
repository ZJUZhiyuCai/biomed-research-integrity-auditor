#!/usr/bin/env python3
"""Extract embedded raster images from supplied PPTX figure-assembly files.

This is an intake helper, not an integrity detector. The exported images are
presentation-layer PowerPoint media objects. They help reviewers see what was
inside figure assembly files, but they are not raw records and do not prove
figure provenance.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import posixpath
from pathlib import Path, PurePosixPath
import re
from typing import Any
import xml.etree.ElementTree as ET
import zipfile


PPTX_EXTS = {".pptx"}
RASTER_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
REL_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
IMAGE_REL_TYPE_SUFFIX = "/image"


@dataclass(frozen=True)
class MediaInfo:
    path: str
    referenced_slides: tuple[int, ...]


def safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.replace("\\", "/"))
    return stem.strip("._") or "pptx"


def collect_pptx_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if not path.is_symlink() and path.is_file() and path.suffix.lower() in PPTX_EXTS
    )


def slide_number_from_rels(name: str) -> int | None:
    match = re.search(r"ppt/slides/_rels/slide(\d+)\.xml\.rels$", name)
    return int(match.group(1)) if match else None


def slide_base_from_rels(name: str) -> str:
    # ppt/slides/_rels/slide1.xml.rels relationships are resolved relative to ppt/slides/.
    return str(PurePosixPath(name).parent.parent)


def resolve_target(base: str, target: str) -> str:
    resolved = posixpath.normpath(posixpath.join(base, target))
    return resolved.lstrip("/")


def image_dimensions(data: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return None, None
    try:
        with Image.open(BytesIO(data)) as image:
            return int(image.width), int(image.height)
    except Exception:  # noqa: BLE001
        return None, None


def relationship_targets(archive: zipfile.ZipFile) -> dict[str, MediaInfo]:
    refs: dict[str, set[int]] = {}
    for rel_name in sorted(archive.namelist()):
        slide_number = slide_number_from_rels(rel_name)
        if slide_number is None:
            continue
        try:
            root = ET.fromstring(archive.read(rel_name))
        except Exception:  # noqa: BLE001 - relationship parsing stays best-effort.
            continue
        base = slide_base_from_rels(rel_name)
        for rel in root.findall("rel:Relationship", REL_NS):
            rel_type = str(rel.attrib.get("Type", ""))
            target = str(rel.attrib.get("Target", ""))
            target_mode = str(rel.attrib.get("TargetMode", ""))
            if target_mode.lower() == "external" or not rel_type.endswith(IMAGE_REL_TYPE_SUFFIX) or not target:
                continue
            media_path = resolve_target(base, target)
            if PurePosixPath(media_path).suffix.lower() in RASTER_IMAGE_EXTS:
                refs.setdefault(media_path, set()).add(slide_number)
    return {
        path: MediaInfo(path=path, referenced_slides=tuple(sorted(slides)))
        for path, slides in refs.items()
    }


def fallback_media_entries(archive: zipfile.ZipFile) -> dict[str, MediaInfo]:
    result: dict[str, MediaInfo] = {}
    for name in sorted(archive.namelist()):
        if not name.startswith("ppt/media/"):
            continue
        if PurePosixPath(name).suffix.lower() not in RASTER_IMAGE_EXTS:
            continue
        result[name] = MediaInfo(path=name, referenced_slides=())
    return result


def extract_images_from_pptx(root: Path, path: Path, image_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    rel = str(path.relative_to(root))
    images: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        media_entries = fallback_media_entries(archive)
        media_entries.update(relationship_targets(archive))
        for media_path, media_info in sorted(media_entries.items()):
            try:
                data = archive.read(media_path)
                ext = PurePosixPath(media_path).suffix.lower().lstrip(".") or "bin"
                output_name = f"{safe_stem(rel)}_{safe_stem(media_path)}.{ext}"
                output_path = image_dir / output_name
                output_path.write_bytes(data)
                width, height = image_dimensions(data)
                images.append({
                    "image_id": f"PPTX-IMG-{safe_stem(rel)}-{safe_stem(media_path)}",
                    "source_pptx": rel,
                    "media_path": media_path,
                    "referenced_slides": list(media_info.referenced_slides),
                    "output_path": str(output_path.relative_to(image_dir.parent)),
                    "extension": ext,
                    "width": width,
                    "height": height,
                    "size_bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "interpretation": "presentation-layer PPTX embedded image; not a raw/source image record",
                })
            except Exception as exc:  # noqa: BLE001
                errors.append({
                    "path": rel,
                    "media_path": media_path,
                    "stage": "pptx_embedded_image_extraction",
                    "error": str(exc),
                })
    return {
        "path": rel,
        "embedded_image_count": len(images),
        "errors": errors,
    }, images, errors


def scan(root: Path, image_dir: Path) -> dict[str, Any]:
    image_dir.mkdir(parents=True, exist_ok=True)
    pptx_files: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for path in collect_pptx_files(root):
        rel = str(path.relative_to(root))
        if not zipfile.is_zipfile(path):
            error = {
                "path": rel,
                "stage": "pptx_embedded_image_extraction",
                "error": "file is not a valid PPTX zip container",
            }
            pptx_files.append({
                "path": rel,
                "embedded_image_count": 0,
                "errors": [error],
            })
            errors.append(error)
            continue
        try:
            pptx_payload, pptx_images, pptx_errors = extract_images_from_pptx(root, path, image_dir)
            pptx_files.append(pptx_payload)
            images.extend(pptx_images)
            errors.extend(pptx_errors)
        except Exception as exc:  # noqa: BLE001 - keep PPTX intake best-effort.
            error = {
                "path": rel,
                "stage": "pptx_embedded_image_extraction",
                "error": str(exc),
            }
            pptx_files.append({
                "path": rel,
                "embedded_image_count": 0,
                "errors": [error],
            })
            errors.append(error)

    return {
        "schema_version": "0.1.0",
        "extractor": "scripts.pptx_embedded_image_extract",
        "scope_note": (
            "Best-effort export of raster images embedded in supplied PPTX files. Exported files are "
            "presentation-layer figure-assembly artifacts, not raw records, and do not establish "
            "provenance or image authenticity."
        ),
        "input": {
            "package": str(root),
            "pptx_files": len(pptx_files),
            "image_dir": str(image_dir),
        },
        "pptx_files": pptx_files,
        "images": images,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("pptx_embedded_images.json"))
    parser.add_argument("--image-dir", type=Path)
    args = parser.parse_args()

    root = args.package_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Package directory not found: {root}")
    output = args.output.expanduser().resolve()
    image_dir = args.image_dir.expanduser().resolve() if args.image_dir else output.parent / "pptx_embedded_images"
    payload = scan(root, image_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "pptx_files": payload["input"]["pptx_files"],
        "images": len(payload["images"]),
        "errors": len(payload["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
