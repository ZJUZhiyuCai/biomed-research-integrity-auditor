#!/usr/bin/env python3
"""Extract conservative paragraph, caption, and table structure from DOCX files.

This is an intake helper, not an integrity detector. It reads Word OpenXML
document bodies and records manuscript structure so captions and tables can be
used for package preparation and claim-manifest drafting. It does not interpret
the scientific content, verify provenance, or read comments/track changes. It
does record whether those review layers appear to be present so users know the
body/caption/table extraction did not cover the whole Word package.
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


DOCX_EXTS = {".docx"}
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CAPTION_START_RE = re.compile(
    r"^\s*((?:supplementary\s+|extended\s+data\s+)?(?:fig(?:ure)?\.?|table)\s+[A-Za-z0-9][A-Za-z0-9.\-]*)"
    r"\s*[:.)-]?\s*(.*)$",
    re.I,
)
SECTION_HEADING_RE = re.compile(
    r"^\s*(abstract|introduction|methods?|materials and methods|results|discussion|conclusions?|references)\s*$",
    re.I,
)
TRACKED_CHANGE_TAGS = {
    f"{WORD_NS}ins",
    f"{WORD_NS}del",
    f"{WORD_NS}moveFrom",
    f"{WORD_NS}moveTo",
}


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def word_text(element: ET.Element) -> str:
    parts: list[str] = []
    for node in element.iter():
        if node.tag == f"{WORD_NS}t" and node.text:
            parts.append(node.text)
        elif node.tag == f"{WORD_NS}tab":
            parts.append("\t")
        elif node.tag in {f"{WORD_NS}br", f"{WORD_NS}cr"}:
            parts.append("\n")
    return normalize_space("".join(parts))


def word_paragraph_style(paragraph: ET.Element) -> str:
    style = paragraph.find(f"{WORD_NS}pPr/{WORD_NS}pStyle")
    if style is None:
        return ""
    return str(style.attrib.get(f"{WORD_NS}val", "")).strip()


def style_kind(style: str) -> str:
    lowered = style.lower()
    if lowered == "caption" or "caption" in lowered:
        return "caption"
    if lowered.startswith("heading") or lowered.startswith("title"):
        return "heading"
    return "paragraph"


def caption_kind(label: str) -> str:
    return "table" if "table" in label.lower() else "figure"


def collect_docx_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if not path.is_symlink() and path.is_file() and path.suffix.lower() in DOCX_EXTS
    )


def read_document_body(path: Path) -> ET.Element:
    try:
        with zipfile.ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")
    except Exception as exc:  # noqa: BLE001 - callers record a best-effort intake error.
        raise ValueError(f"DOCX structure extraction failed: {exc}") from exc

    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError as exc:
        raise ValueError(f"DOCX document.xml parse failed: {exc}") from exc

    body = root.find(f".//{WORD_NS}body")
    if body is None:
        raise ValueError("DOCX document.xml does not contain a Word body")
    return body


def docx_review_layer_items(path: Path, rel: str) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Return counts for DOCX layers this extractor does not parse.

    The counts are deliberately structural only. We do not copy comment text,
    revision text, embedded object contents, or media payloads into the audit
    artifact.
    """
    counts = {
        "comment_count": 0,
        "tracked_change_count": 0,
        "embedded_object_count": 0,
        "embedded_media_count": 0,
    }
    warnings: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "word/comments.xml" in names:
                try:
                    comments_root = ET.fromstring(archive.read("word/comments.xml"))
                    counts["comment_count"] = sum(
                        1 for node in comments_root.iter() if node.tag == f"{WORD_NS}comment"
                    )
                except Exception:  # noqa: BLE001 - presence is enough for a coverage warning.
                    counts["comment_count"] = 1
            try:
                document_root = ET.fromstring(archive.read("word/document.xml"))
                counts["tracked_change_count"] = sum(
                    1 for node in document_root.iter() if node.tag in TRACKED_CHANGE_TAGS
                )
            except Exception:  # noqa: BLE001 - normal extraction records parse errors separately.
                counts["tracked_change_count"] = 0
            counts["embedded_object_count"] = sum(
                1
                for name in names
                if name.startswith("word/embeddings/") and not name.endswith("/")
            )
            counts["embedded_media_count"] = sum(
                1
                for name in names
                if name.startswith("word/media/") and not name.endswith("/")
            )
    except Exception as exc:  # noqa: BLE001 - extraction errors are handled elsewhere.
        warnings.append({
            "path": rel,
            "warning_type": "docx_review_layer_scan_failed",
            "message": f"DOCX review-layer scan failed: {exc.__class__.__name__}",
        })
        return counts, warnings

    if counts["comment_count"]:
        warnings.append({
            "path": rel,
            "warning_type": "docx_comments_present",
            "count": counts["comment_count"],
            "message": (
                "DOCX contains Word comments. Body/caption/table extraction does not read comment text; "
                "review the comments manually or export an accepted/comment-resolved version for audit."
            ),
        })
    if counts["tracked_change_count"]:
        warnings.append({
            "path": rel,
            "warning_type": "docx_tracked_changes_present",
            "count": counts["tracked_change_count"],
            "message": (
                "DOCX contains tracked revisions. Body/caption/table extraction reads visible document text "
                "only and does not resolve revision history; review or accept/reject changes before relying on intake."
            ),
        })
    if counts["embedded_object_count"] or counts["embedded_media_count"]:
        warnings.append({
            "path": rel,
            "warning_type": "docx_embedded_objects_present",
            "embedded_object_count": counts["embedded_object_count"],
            "embedded_media_count": counts["embedded_media_count"],
            "message": (
                "DOCX contains embedded objects or media. These are not raw/source records or figure provenance; "
                "export figure panels, raw records, and source tables separately."
            ),
        })
    return counts, warnings


def extract_docx_blocks(path: Path, rel: str, start: dict[str, int]) -> dict[str, Any]:
    body = read_document_body(path)
    review_counts, warnings = docx_review_layer_items(path, rel)
    paragraphs: list[dict[str, Any]] = []
    captions: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    block_index = 0

    for child in list(body):
        if child.tag == f"{WORD_NS}p":
            text = word_text(child)
            if not text:
                continue
            block_index += 1
            style = word_paragraph_style(child)
            kind = style_kind(style)
            if SECTION_HEADING_RE.match(text):
                kind = "heading"
            paragraph_id = f"DOCX-PARA-{start['paragraph'] + len(paragraphs):04d}"
            paragraphs.append({
                "paragraph_id": paragraph_id,
                "path": rel,
                "block_index": block_index,
                "style": style,
                "kind": kind,
                "text": text,
            })
            match = CAPTION_START_RE.match(text)
            if match or kind == "caption":
                label = normalize_space(match.group(1)).rstrip(".:-)") if match else ""
                captions.append({
                    "caption_id": f"DOCX-CAP-{start['caption'] + len(captions):04d}",
                    "path": rel,
                    "block_index": block_index,
                    "kind": caption_kind(label) if label else "caption",
                    "label": label,
                    "style": style,
                    "text": text,
                })
        elif child.tag == f"{WORD_NS}tbl":
            block_index += 1
            rows: list[list[str]] = []
            for row in child.findall(f"{WORD_NS}tr"):
                cells = []
                for cell in row.findall(f"{WORD_NS}tc"):
                    cell_text = " ".join(
                        item
                        for item in (word_text(paragraph) for paragraph in cell.findall(f"{WORD_NS}p"))
                        if item
                    )
                    cells.append(cell_text)
                if any(cells):
                    rows.append(cells)
            if rows:
                tables.append({
                    "block_id": f"DOCX-TABLE-{start['table'] + len(tables):04d}",
                    "path": rel,
                    "block_index": block_index,
                    "row_count": len(rows),
                    "column_count_estimate": max(len(row) for row in rows),
                    "rows": rows[:20],
                })

    return {
        "paragraphs": paragraphs,
        "captions": captions,
        "table_like_blocks": tables,
        "block_count": block_index,
        "review_layer_counts": review_counts,
        "warnings": warnings,
    }


def scan(root: Path) -> dict[str, Any]:
    docx_files = []
    paragraphs: list[dict[str, Any]] = []
    captions: list[dict[str, Any]] = []
    table_like_blocks: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for path in collect_docx_files(root):
        rel = str(path.relative_to(root))
        try:
            extracted = extract_docx_blocks(
                path,
                rel,
                {
                    "paragraph": len(paragraphs) + 1,
                    "caption": len(captions) + 1,
                    "table": len(table_like_blocks) + 1,
                },
            )
        except Exception as exc:  # noqa: BLE001 - keep DOCX intake best-effort.
            errors.append({
                "path": rel,
                "stage": "docx_structure_extraction",
                "error": str(exc),
            })
            docx_files.append({
                "path": rel,
                "extraction_method": "error",
                "paragraph_count": 0,
                "caption_count": 0,
                "table_like_block_count": 0,
                "errors": [str(exc)],
            })
            continue

        paragraphs.extend(extracted["paragraphs"])
        captions.extend(extracted["captions"])
        table_like_blocks.extend(extracted["table_like_blocks"])
        warnings.extend(extracted.get("warnings", []) or [])
        review_counts = extracted.get("review_layer_counts", {}) or {}
        docx_files.append({
            "path": rel,
            "extraction_method": "word_openxml_document_body",
            "block_count": extracted["block_count"],
            "paragraph_count": len(extracted["paragraphs"]),
            "caption_count": len(extracted["captions"]),
            "table_like_block_count": len(extracted["table_like_blocks"]),
            "comment_count": int(review_counts.get("comment_count", 0) or 0),
            "tracked_change_count": int(review_counts.get("tracked_change_count", 0) or 0),
            "embedded_object_count": int(review_counts.get("embedded_object_count", 0) or 0),
            "embedded_media_count": int(review_counts.get("embedded_media_count", 0) or 0),
            "warnings": extracted.get("warnings", []) or [],
            "errors": [],
        })

    return {
        "schema_version": "0.2.0",
        "extractor": "scripts.docx_structure_extract",
        "scope_note": (
            "Best-effort extraction of DOCX body paragraphs, caption-like paragraphs, and Word tables. "
            "This artifact supports material preparation and claim-manifest drafting; it does not read "
            "comment text, resolve tracked changes, extract embedded object contents, or prove figure/source provenance. "
            "When those review layers are present, they are recorded as intake warnings."
        ),
        "input": {
            "package": str(root),
            "docx_files": len(docx_files),
        },
        "docx_files": docx_files,
        "paragraphs": paragraphs,
        "captions": captions,
        "table_like_blocks": table_like_blocks,
        "warnings": warnings,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("docx_structure.json"))
    args = parser.parse_args()

    root = args.package_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Package directory not found: {root}")
    payload = scan(root)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "docx_files": payload["input"]["docx_files"],
        "paragraphs": len(payload["paragraphs"]),
        "captions": len(payload["captions"]),
        "table_like_blocks": len(payload["table_like_blocks"]),
        "warnings": len(payload["warnings"]),
        "errors": len(payload["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
