#!/usr/bin/env python3
"""Generate a tiny true-PDF benchmark package with compressed text streams."""

from __future__ import annotations

import argparse
import json
import zlib
from pathlib import Path


PDF_LINES = [
    "Synthetic True PDF Benchmark",
    "Results",
    "The benchmark treatment group showed a compressed pdf only nuclear signal increase after twenty four hours.",
    "Quantification from independent biological replicates showed the same direction of effect in all fields.",
    "Figure 1. Representative microscopy field and matched source-data summary are described in the caption.",
]


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_content_stream(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 12 Tf", "72 720 Td"]
    for idx, line in enumerate(lines):
        if idx:
            commands.append("0 -22 Td")
        commands.append(f"({pdf_escape(line)}) Tj")
    commands.append("ET")
    return "\n".join(commands).encode("ascii")


def write_pdf(path: Path, lines: list[str]) -> None:
    compressed = zlib.compress(make_content_stream(lines))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (
            f"<< /Length {len(compressed)} /Filter /FlateDecode >>\nstream\n".encode("ascii")
            + compressed
            + b"\nendstream"
        ),
    ]

    chunks = [b"%PDF-1.4\n%\xE2\xE3\xCF\xD3\n"]
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(sum(len(chunk) for chunk in chunks))
        chunks.append(f"{idx} 0 obj\n".encode("ascii"))
        chunks.append(obj)
        chunks.append(b"\nendobj\n")

    xref_offset = sum(len(chunk) for chunk in chunks)
    chunks.append(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    chunks.append(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        chunks.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    chunks.append(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(chunks))


def write_package(root: Path) -> dict:
    package = root / "true_pdf_001"
    package.mkdir(parents=True, exist_ok=True)
    write_pdf(package / "manuscript.pdf", PDF_LINES)
    (package / "PACKAGE_NOTE.txt").write_text(
        "True binary PDF benchmark package. The manuscript PDF has a compressed content stream.\n",
        encoding="utf-8",
    )
    prior_text = (
        "Results\n\n"
        "The benchmark treatment group showed a compressed pdf only nuclear signal increase after twenty four hours. "
        "Quantification from independent biological replicates showed the same direction of effect in all fields. "
        "This lab previous paper is supplied so a future PDF text extractor can create a text-overlap candidate.\n"
    )
    (package / "lab_previous_papers").mkdir(exist_ok=True)
    (package / "lab_previous_papers/prior_text.txt").write_text(prior_text, encoding="utf-8")

    expected = {
        "benchmark_id": "true_pdf_001",
        "package": str(package),
        "pdf": "manuscript.pdf",
        "expected_markers": PDF_LINES[2:4],
        "current_expected_status": "known_gap_pdf_text_extraction_unavailable",
        "future_success_condition": (
            "A PDF extraction stage should recover the expected markers from manuscript.pdf "
            "and enable comparison against lab_previous_papers/prior_text.txt."
        ),
    }
    (package / "expected_pdf_intake.json").write_text(
        json.dumps(expected, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/true_pdf_benchmark/cases"))
    args = parser.parse_args()

    expected = write_package(args.output_dir.expanduser().resolve())
    print(json.dumps(expected, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
