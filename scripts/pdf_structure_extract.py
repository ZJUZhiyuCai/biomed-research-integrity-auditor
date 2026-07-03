#!/usr/bin/env python3
"""Extract conservative figure/table structure from supplied PDF files.

This is an intake helper, not an integrity detector. It reads machine-extractable
PDF text and records caption-like and table-like text blocks so users can see
what the pipeline could inspect. It does not extract embedded PDF images or
screen pixels; `scripts/pdf_embedded_image_extract.py` handles presentation-layer
PDF image export separately.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PDF_EXTS = {".pdf"}
CAPTION_START_RE = re.compile(
    r"^\s*((?:supplementary\s+|extended\s+data\s+)?(?:fig(?:ure)?\.?|table)\s+[A-Za-z0-9][A-Za-z0-9.\-]*)"
    r"\s*[:.)-]?\s*(.*)$",
    re.I,
)
SECTION_HEADING_RE = re.compile(
    r"^\s*(abstract|introduction|methods?|materials and methods|results|discussion|conclusions?|references)\s*$",
    re.I,
)
NUMERIC_TOKEN_RE = re.compile(r"^[<>~]?-?\d+(?:\.\d+)?(?:%|e-?\d+)?$", re.I)
TABLE_HEADER_TOKENS = {
    "group",
    "condition",
    "sample",
    "mean",
    "median",
    "sd",
    "sem",
    "se",
    "n",
    "p",
    "p-value",
    "value",
    "fold",
    "change",
    "control",
    "treatment",
}


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_true_pdf(path: Path) -> bool:
    try:
        return path.read_bytes()[:5] == b"%PDF-"
    except OSError:
        return False


def extract_true_pdf_pages(path: Path) -> tuple[list[dict[str, Any]], str]:
    try:
        import fitz  # type: ignore
    except Exception:
        fitz = None  # type: ignore

    if fitz is not None:
        with fitz.open(str(path)) as doc:
            pages = []
            for page_idx, page in enumerate(doc, start=1):
                pages.append({
                    "page": page_idx,
                    "text": page.get_text("text", sort=True) or "",
                    "extraction_method": "pymupdf_text",
                })
            return pages, "pymupdf_text"

    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise ValueError("PDF structure extraction requires PyMuPDF or pypdf") from exc

    reader = PdfReader(str(path))
    pages = []
    for page_idx, page in enumerate(reader.pages, start=1):
        pages.append({
            "page": page_idx,
            "text": page.extract_text() or "",
            "extraction_method": "pypdf_text",
        })
    return pages, "pypdf_text"


def extract_pdf_pages(path: Path) -> tuple[list[dict[str, Any]], str, bool]:
    if is_true_pdf(path):
        pages, method = extract_true_pdf_pages(path)
        return pages, method, True
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [{"page": 1, "text": text, "extraction_method": "plain_text_pdf_suffix"}], "plain_text_pdf_suffix", False


def page_lines(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\r", "\n").split("\n")]


def caption_kind(label: str) -> str:
    return "table" if "table" in label.lower() else "figure"


def parse_table_line(line: str) -> list[str] | None:
    stripped = line.strip().strip("|")
    if not stripped:
        return None
    if "\t" in stripped:
        cells = [normalize_space(cell) for cell in stripped.split("\t")]
    elif "|" in stripped:
        cells = [normalize_space(cell) for cell in stripped.split("|")]
    elif re.search(r"\S\s{2,}\S", stripped):
        cells = [normalize_space(cell) for cell in re.split(r"\s{2,}", stripped)]
    elif stripped.count(",") >= 2 and len(stripped) <= 220:
        cells = [normalize_space(cell) for cell in stripped.split(",")]
    else:
        cells = [normalize_space(cell) for cell in stripped.split()]
        numeric_count = sum(1 for cell in cells if NUMERIC_TOKEN_RE.match(cell))
        header_count = sum(1 for cell in cells if cell.lower() in TABLE_HEADER_TOKENS)
        if len(cells) < 2 or len(cells) > 10 or len(stripped) > 160:
            return None
        if numeric_count == 0 and header_count < 2:
            return None
    cells = [cell for cell in cells if cell]
    if len(cells) < 2 or len(cells) > 16:
        return None
    if sum(len(cell) for cell in cells) < 4:
        return None
    return cells


def extract_captions(path: str, page: int, text: str, start_index: int) -> list[dict[str, Any]]:
    lines = page_lines(text)
    captions: list[dict[str, Any]] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        match = CAPTION_START_RE.match(line)
        if not match:
            idx += 1
            continue
        label = normalize_space(match.group(1)).rstrip(".:-)")
        parts = [normalize_space(line)]
        lookahead = idx + 1
        while lookahead < len(lines) and len(" ".join(parts)) < 900 and len(parts) < 6:
            nxt = lines[lookahead].strip()
            if not nxt:
                break
            if CAPTION_START_RE.match(nxt) or SECTION_HEADING_RE.match(nxt):
                break
            if parse_table_line(nxt):
                break
            parts.append(normalize_space(nxt))
            lookahead += 1
        text_value = normalize_space(" ".join(parts))
        captions.append({
            "caption_id": f"PDF-CAP-{start_index + len(captions):04d}",
            "path": path,
            "page": page,
            "kind": caption_kind(label),
            "label": label,
            "text": text_value,
        })
        idx = max(lookahead, idx + 1)
    return captions


def extract_table_like_blocks(path: str, page: int, text: str, start_index: int) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current: list[list[str]] = []

    def flush() -> None:
        nonlocal current
        if len(current) >= 2:
            blocks.append({
                "block_id": f"PDF-TABLE-{start_index + len(blocks):04d}",
                "path": path,
                "page": page,
                "row_count": len(current),
                "column_count_estimate": max(len(row) for row in current),
                "rows": current[:20],
            })
        current = []

    for line in page_lines(text):
        row = parse_table_line(line)
        if row:
            current.append(row)
        else:
            flush()
    flush()
    return blocks


def collect_pdf_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if not path.is_symlink() and path.is_file() and path.suffix.lower() in PDF_EXTS
    )


def scan(root: Path) -> dict[str, Any]:
    pdfs = []
    captions: list[dict[str, Any]] = []
    table_like_blocks: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for path in collect_pdf_files(root):
        rel = str(path.relative_to(root))
        try:
            pages, method, true_pdf = extract_pdf_pages(path)
        except Exception as exc:  # noqa: BLE001 - keep structure extraction best-effort.
            errors.append({
                "path": rel,
                "stage": "pdf_structure_extraction",
                "error": str(exc),
            })
            pdfs.append({
                "path": rel,
                "is_true_pdf": is_true_pdf(path),
                "extraction_method": "error",
                "page_count": 0,
                "caption_count": 0,
                "table_like_block_count": 0,
                "errors": [str(exc)],
            })
            continue

        pdf_caption_count = 0
        pdf_table_count = 0
        page_summaries = []
        for page_payload in pages:
            page = int(page_payload.get("page", len(page_summaries) + 1))
            text = str(page_payload.get("text", ""))
            page_captions = extract_captions(rel, page, text, len(captions) + 1)
            captions.extend(page_captions)
            page_tables = extract_table_like_blocks(rel, page, text, len(table_like_blocks) + 1)
            table_like_blocks.extend(page_tables)
            pdf_caption_count += len(page_captions)
            pdf_table_count += len(page_tables)
            page_summaries.append({
                "page": page,
                "text_length": len(text),
                "caption_count": len(page_captions),
                "table_like_block_count": len(page_tables),
                "extraction_method": str(page_payload.get("extraction_method", method)),
            })

        pdfs.append({
            "path": rel,
            "is_true_pdf": true_pdf,
            "extraction_method": method,
            "page_count": len(page_summaries),
            "caption_count": pdf_caption_count,
            "table_like_block_count": pdf_table_count,
            "pages": page_summaries,
            "errors": [],
        })

    return {
        "schema_version": "0.1.0",
        "extractor": "scripts.pdf_structure_extract",
        "scope_note": (
            "Best-effort extraction of machine-readable PDF text into caption-like and table-like blocks. "
            "Embedded PDF images are exported, when possible, by pdf_embedded_images.json rather than this artifact."
        ),
        "input": {
            "package": str(root),
            "pdf_files": len(pdfs),
        },
        "pdfs": pdfs,
        "captions": captions,
        "table_like_blocks": table_like_blocks,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("pdf_structure.json"))
    args = parser.parse_args()

    root = args.package_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Package directory not found: {root}")
    payload = scan(root)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "pdf_files": payload["input"]["pdf_files"],
        "captions": len(payload["captions"]),
        "table_like_blocks": len(payload["table_like_blocks"]),
        "errors": len(payload["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
