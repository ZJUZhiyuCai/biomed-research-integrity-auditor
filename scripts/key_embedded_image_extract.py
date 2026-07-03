#!/usr/bin/env python3
"""Extract embedded raster images from supplied Keynote .key files.

This is an intake helper, not an integrity detector. Modern Keynote files are
usually zip containers; this script exports raster media objects when possible.
The exported images are presentation-layer assembly artifacts, not raw records
or provenance proof.
"""

from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any
import zipfile


KEY_EXTS = {".key"}
RASTER_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
IGNORED_PREFIXES = ("__MACOSX/",)


def safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.replace("\\", "/"))
    return stem.strip("._") or "key"


def collect_key_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if not path.is_symlink() and path.is_file() and path.suffix.lower() in KEY_EXTS
    )


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


def image_members(archive: zipfile.ZipFile) -> list[str]:
    members = []
    for name in sorted(archive.namelist()):
        if name.endswith("/") or name.startswith(IGNORED_PREFIXES):
            continue
        if PurePosixPath(name).suffix.lower() in RASTER_IMAGE_EXTS:
            members.append(name)
    return members


def extract_images_from_key(root: Path, path: Path, image_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    rel = str(path.relative_to(root))
    images: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        for member in image_members(archive):
            try:
                data = archive.read(member)
                ext = PurePosixPath(member).suffix.lower().lstrip(".") or "bin"
                output_name = f"{safe_stem(rel)}_{safe_stem(member)}.{ext}"
                output_path = image_dir / output_name
                output_path.write_bytes(data)
                width, height = image_dimensions(data)
                images.append({
                    "image_id": f"KEY-IMG-{safe_stem(rel)}-{safe_stem(member)}",
                    "source_key": rel,
                    "internal_path": member,
                    "output_path": str(output_path.relative_to(image_dir.parent)),
                    "extension": ext,
                    "width": width,
                    "height": height,
                    "size_bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "interpretation": "presentation-layer Keynote embedded image; not a raw/source image record",
                })
            except Exception as exc:  # noqa: BLE001
                errors.append({
                    "path": rel,
                    "internal_path": member,
                    "stage": "key_embedded_image_extraction",
                    "error": str(exc),
                })
    return {
        "path": rel,
        "embedded_image_count": len(images),
        "errors": errors,
    }, images, errors


def scan(root: Path, image_dir: Path) -> dict[str, Any]:
    image_dir.mkdir(parents=True, exist_ok=True)
    key_files: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for path in collect_key_files(root):
        rel = str(path.relative_to(root))
        if not zipfile.is_zipfile(path):
            error = {
                "path": rel,
                "stage": "key_embedded_image_extraction",
                "error": "file is not a zip-based Keynote container; export figures manually from Keynote",
            }
            key_files.append({
                "path": rel,
                "embedded_image_count": 0,
                "errors": [error],
            })
            errors.append(error)
            continue
        try:
            key_payload, key_images, key_errors = extract_images_from_key(root, path, image_dir)
            key_files.append(key_payload)
            images.extend(key_images)
            errors.extend(key_errors)
        except Exception as exc:  # noqa: BLE001 - keep Keynote intake best-effort.
            error = {
                "path": rel,
                "stage": "key_embedded_image_extraction",
                "error": str(exc),
            }
            key_files.append({
                "path": rel,
                "embedded_image_count": 0,
                "errors": [error],
            })
            errors.append(error)

    return {
        "schema_version": "0.1.0",
        "extractor": "scripts.key_embedded_image_extract",
        "scope_note": (
            "Best-effort export of raster images embedded in zip-based Keynote files. Exported files "
            "are presentation-layer figure-assembly artifacts, not raw records, and do not establish "
            "provenance or image authenticity."
        ),
        "input": {
            "package": str(root),
            "key_files": len(key_files),
            "image_dir": str(image_dir),
        },
        "key_files": key_files,
        "images": images,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("key_embedded_images.json"))
    parser.add_argument("--image-dir", type=Path)
    args = parser.parse_args()

    root = args.package_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Package directory not found: {root}")
    output = args.output.expanduser().resolve()
    image_dir = args.image_dir.expanduser().resolve() if args.image_dir else output.parent / "key_embedded_images"
    payload = scan(root, image_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "key_files": payload["input"]["key_files"],
        "images": len(payload["images"]),
        "errors": len(payload["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
