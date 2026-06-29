#!/usr/bin/env python3
"""Generate an image-only scanned-PDF benchmark package for OCR intake."""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OCR_LINES = [
    "Synthetic Scanned PDF Benchmark",
    "Results",
    (
        "The scanned benchmark treatment group showed an OCR only nuclear signal increase "
        "after forty eight hours with matched replicate annotations and blinded field scoring."
    ),
    (
        "Quantification from independent biological replicates preserved the same direction "
        "of effect after sample maps, acquisition dates, and image-only scan records were reviewed."
    ),
]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def draw_scanned_page(lines: list[str]) -> Image.Image:
    image = Image.new("RGB", (1700, 2200), "white")
    draw = ImageDraw.Draw(image)
    title_font = load_font(54)
    body_font = load_font(42)
    y = 150
    for idx, line in enumerate(lines):
        font = title_font if idx == 0 else body_font
        wrapped = textwrap.wrap(line, width=58)
        for part in wrapped:
            draw.text((150, y), part, fill=(20, 20, 20), font=font)
            y += 72 if idx == 0 else 64
        y += 22
    return image


def write_scanned_pdf(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    draw_scanned_page(lines).save(path, "PDF", resolution=220.0)


def write_package(root: Path) -> dict:
    package = root / "scanned_pdf_001"
    package.mkdir(parents=True, exist_ok=True)
    write_scanned_pdf(package / "manuscript.pdf", OCR_LINES)
    (package / "PACKAGE_NOTE.txt").write_text(
        "Image-only scanned PDF benchmark package. The manuscript PDF requires OCR for text screening.\n",
        encoding="utf-8",
    )
    prior_text = "Results\n\n" + " ".join(OCR_LINES[2:4]) + "\n"
    (package / "lab_previous_papers").mkdir(exist_ok=True)
    (package / "lab_previous_papers/prior_text.txt").write_text(prior_text, encoding="utf-8")

    expected = {
        "benchmark_id": "scanned_pdf_001",
        "package": str(package),
        "pdf": "manuscript.pdf",
        "expected_markers": OCR_LINES[2:4],
        "expected_status": "ocr_pdf_text_extraction_available",
        "success_condition": (
            "The text detector should OCR manuscript.pdf and create a package-internal text-overlap "
            "candidate against lab_previous_papers/prior_text.txt."
        ),
    }
    (package / "expected_ocr_intake.json").write_text(
        json.dumps(expected, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/scanned_pdf_benchmark/cases"))
    args = parser.parse_args()

    expected = write_package(args.output_dir.expanduser().resolve())
    print(json.dumps(expected, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
