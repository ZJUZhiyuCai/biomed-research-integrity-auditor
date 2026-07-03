#!/usr/bin/env python3
"""Export flattened preview images from supplied PSD figure-assembly files.

This is an intake helper, not an integrity detector. When Pillow can decode a
PSD-like file, the script exports a flattened RGB preview so reviewers can see
the presentation-layer assembly artifact. It does not parse layers, masks,
adjustment history, or figure-to-source provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

from detectors.image.image_io import normalized_rgb


PSD_EXTS = {".psd"}


def safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.replace("\\", "/"))
    return stem.strip("._") or "psd"


def collect_psd_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if not path.is_symlink() and path.is_file() and path.suffix.lower() in PSD_EXTS
    )


def export_preview(root: Path, path: Path, image_dir: Path) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    rel = str(path.relative_to(root))
    try:
        from PIL import Image
    except Exception as exc:  # noqa: BLE001
        error = {
            "path": rel,
            "stage": "psd_preview_extraction",
            "error": f"Pillow is unavailable: {exc}",
        }
        return {"path": rel, "status": "preview_unavailable", "errors": [error]}, None, error

    try:
        with Image.open(path) as image:
            source_format = str(image.format or "unknown")
            source_mode = str(image.mode)
            source_size = (int(image.width), int(image.height))
            preview = normalized_rgb(image)
            output_name = f"{safe_stem(rel)}_flattened_preview.png"
            output_path = image_dir / output_name
            preview.save(output_path, format="PNG")
    except Exception as exc:  # noqa: BLE001 - PSD preview intake stays best-effort.
        error = {
            "path": rel,
            "stage": "psd_preview_extraction",
            "error": str(exc),
        }
        return {"path": rel, "status": "preview_unavailable", "errors": [error]}, None, error

    data = output_path.read_bytes()
    record = {
        "image_id": f"PSD-PREVIEW-{safe_stem(rel)}",
        "source_psd": rel,
        "output_path": str(output_path.relative_to(image_dir.parent)),
        "width": source_size[0],
        "height": source_size[1],
        "source_mode": source_mode,
        "source_format": source_format,
        "extension": "png",
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "interpretation": (
            "flattened presentation-layer PSD preview; not a raw/source image record, "
            "layer provenance record, or authenticity finding"
        ),
    }
    return {
        "path": rel,
        "status": "preview_exported",
        "preview_count": 1,
        "errors": [],
    }, record, None


def scan(root: Path, image_dir: Path) -> dict[str, Any]:
    image_dir.mkdir(parents=True, exist_ok=True)
    psd_files: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for path in collect_psd_files(root):
        file_payload, image_record, error = export_preview(root, path, image_dir)
        psd_files.append(file_payload)
        if image_record is not None:
            images.append(image_record)
        if error is not None:
            errors.append(error)

    return {
        "schema_version": "0.1.0",
        "extractor": "scripts.psd_preview_extract",
        "scope_note": (
            "Best-effort export of flattened previews from supplied PSD figure-assembly files. "
            "Exported previews are presentation-layer intake artifacts, not raw records, layer "
            "provenance records, or image-authenticity evidence. PSD layers, masks, adjustment "
            "history, and source-to-figure links still require manual review or explicit exports."
        ),
        "input": {
            "package": str(root),
            "psd_files": len(psd_files),
            "image_dir": str(image_dir),
        },
        "psd_files": psd_files,
        "images": images,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("psd_preview_images.json"))
    parser.add_argument("--image-dir", type=Path)
    args = parser.parse_args()

    root = args.package_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Package directory not found: {root}")
    output = args.output.expanduser().resolve()
    image_dir = args.image_dir.expanduser().resolve() if args.image_dir else output.parent / "psd_preview_images"
    payload = scan(root, image_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "psd_files": payload["input"]["psd_files"],
        "images": len(payload["images"]),
        "errors": len(payload["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
