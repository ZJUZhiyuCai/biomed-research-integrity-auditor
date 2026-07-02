#!/usr/bin/env python3
"""Extract embedded raster images from supplied PDF files.

This is an intake helper, not an integrity detector. The exported images are
presentation-layer PDF objects. They help reviewers see what was inside a PDF
container, but they are not raw records and do not prove figure provenance.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import re
from pathlib import Path
from typing import Any


PDF_EXTS = {".pdf"}
SUPPORTED_OUTPUT_EXTS = {"png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"}


@dataclass(frozen=True)
class ImageBytes:
    data: bytes
    ext: str
    converted_to_png: bool


def safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.replace("\\", "/"))
    return stem.strip("._") or "pdf"


def is_true_pdf(path: Path) -> bool:
    try:
        return path.read_bytes()[:5] == b"%PDF-"
    except OSError:
        return False


def collect_pdf_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in PDF_EXTS)


def normalize_extracted_image(image_payload: dict[str, Any]) -> ImageBytes:
    data = image_payload.get("image")
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("PDF image object did not contain extractable bytes")
    ext = str(image_payload.get("ext") or "png").lower().lstrip(".")
    if ext == "jpeg":
        ext = "jpg"
    if ext in SUPPORTED_OUTPUT_EXTS:
        return ImageBytes(bytes(data), ext, False)

    try:
        from PIL import Image
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"unsupported PDF image format '{ext}' and Pillow is unavailable for conversion") from exc

    with Image.open(BytesIO(bytes(data))) as image:
        converted = BytesIO()
        image.convert("RGB").save(converted, format="PNG")
        return ImageBytes(converted.getvalue(), "png", True)


def rect_payload(rect: Any) -> dict[str, float]:
    return {
        "x0": round(float(rect.x0), 2),
        "y0": round(float(rect.y0), 2),
        "x1": round(float(rect.x1), 2),
        "y1": round(float(rect.y1), 2),
    }


def extract_images_from_pdf(root: Path, path: Path, image_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        import fitz  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise ValueError("PDF embedded-image extraction requires PyMuPDF") from exc

    rel = str(path.relative_to(root))
    images: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with fitz.open(str(path)) as doc:
        page_count = len(doc)
        for page_index, page in enumerate(doc, start=1):
            for image_index, image_info in enumerate(page.get_images(full=True), start=1):
                xref = int(image_info[0])
                try:
                    extracted = normalize_extracted_image(doc.extract_image(xref))
                    output_name = (
                        f"{safe_stem(rel)}_p{page_index:03d}_img{image_index:03d}_"
                        f"xref{xref}.{extracted.ext}"
                    )
                    output_path = image_dir / output_name
                    output_path.write_bytes(extracted.data)
                    rects = [rect_payload(rect) for rect in page.get_image_rects(xref)]
                    images.append({
                        "image_id": f"PDF-IMG-{safe_stem(rel)}-p{page_index:03d}-i{image_index:03d}",
                        "source_pdf": rel,
                        "page": page_index,
                        "xref": xref,
                        "output_path": str(output_path.relative_to(image_dir.parent)),
                        "extension": extracted.ext,
                        "width": int(image_info[2]) if len(image_info) > 2 else None,
                        "height": int(image_info[3]) if len(image_info) > 3 else None,
                        "colorspace": str(image_info[5]) if len(image_info) > 5 else "",
                        "filter": str(image_info[8]) if len(image_info) > 8 else "",
                        "sha256": hashlib.sha256(extracted.data).hexdigest(),
                        "converted_to_png": extracted.converted_to_png,
                        "page_rects": rects,
                        "interpretation": "presentation-layer PDF embedded image; not a raw/source image record",
                    })
                except Exception as exc:  # noqa: BLE001
                    errors.append({
                        "path": rel,
                        "page": page_index,
                        "xref": xref,
                        "stage": "pdf_embedded_image_extraction",
                        "error": str(exc),
                    })

    return {
        "path": rel,
        "is_true_pdf": True,
        "page_count": page_count,
        "embedded_image_count": len(images),
        "errors": errors,
    }, images, errors


def scan(root: Path, image_dir: Path) -> dict[str, Any]:
    image_dir.mkdir(parents=True, exist_ok=True)
    pdfs: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for path in collect_pdf_files(root):
        rel = str(path.relative_to(root))
        if not is_true_pdf(path):
            pdfs.append({
                "path": rel,
                "is_true_pdf": False,
                "page_count": 0,
                "embedded_image_count": 0,
                "errors": [],
            })
            continue
        try:
            pdf_payload, pdf_images, pdf_errors = extract_images_from_pdf(root, path, image_dir)
            pdfs.append(pdf_payload)
            images.extend(pdf_images)
            errors.extend(pdf_errors)
        except Exception as exc:  # noqa: BLE001 - keep PDF intake best-effort.
            error = {
                "path": rel,
                "stage": "pdf_embedded_image_extraction",
                "error": str(exc),
            }
            pdfs.append({
                "path": rel,
                "is_true_pdf": True,
                "page_count": 0,
                "embedded_image_count": 0,
                "errors": [error],
            })
            errors.append(error)

    return {
        "schema_version": "0.1.0",
        "extractor": "scripts.pdf_embedded_image_extract",
        "scope_note": (
            "Best-effort export of raster images embedded in supplied PDFs. Exported files are "
            "presentation-layer intake artifacts, not raw records, and do not establish provenance "
            "or image authenticity."
        ),
        "input": {
            "package": str(root),
            "pdf_files": len(pdfs),
            "image_dir": str(image_dir),
        },
        "pdfs": pdfs,
        "images": images,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("pdf_embedded_images.json"))
    parser.add_argument("--image-dir", type=Path)
    args = parser.parse_args()

    root = args.package_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Package directory not found: {root}")
    output = args.output.expanduser().resolve()
    image_dir = args.image_dir.expanduser().resolve() if args.image_dir else output.parent / "pdf_embedded_images"
    payload = scan(root, image_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "pdf_files": payload["input"]["pdf_files"],
        "images": len(payload["images"]),
        "errors": len(payload["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
