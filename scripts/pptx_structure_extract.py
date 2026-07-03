#!/usr/bin/env python3
"""Extract conservative slide text and explicit path structure from PPTX files.

This is an intake helper, not an integrity detector. It records slide text,
speaker notes, shape alt text, package-relative path mentions, and explicit
figure/source path pairs that can help prepare assembly manifests. It does not
inspect PowerPoint geometry, layers, masks, or prove figure-source provenance.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import zipfile


ROOT = Path(__file__).resolve().parents[1]

from provenance.parse_assembly_manifest import (
    IMAGE_OR_DATA_RE,
    extract_line_links,
    package_files,
    pptx_alt_texts,
    pptx_notes_for_slide,
    pptx_slide_paragraphs,
    pptx_slide_sort_key,
    resolve_token,
    role,
)


PPTX_EXTS = {".pptx"}


def collect_pptx_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if not path.is_symlink() and path.is_file() and path.suffix.lower() in PPTX_EXTS
    )


def path_mentions(text: str, files: dict[str, list[str]]) -> list[dict[str, str]]:
    mentions: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in IMAGE_OR_DATA_RE.finditer(text):
        token = match.group(0)
        resolved = resolve_token(token, files)
        if not resolved:
            continue
        key = (token, resolved)
        if key in seen:
            continue
        seen.add(key)
        mentions.append({
            "token": token,
            "resolved_path": resolved,
            "role": role(resolved),
        })
    return mentions


def unique_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for link in links:
        key = (
            str(link.get("source_path", "")),
            str(link.get("target_path", "")),
            str(link.get("relation_type", "")),
            str(link.get("evidence_source", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(link)
    return result


def scan_pptx(root: Path, path: Path, files: dict[str, list[str]]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rel = str(path.relative_to(root))
    pptx_links: list[dict[str, Any]] = []
    slide_payloads: list[dict[str, Any]] = []
    mention_payloads: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        slide_names = sorted(
            [
                name for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml") and "/_rels/" not in name
            ],
            key=pptx_slide_sort_key,
        )
        for index, slide_name in enumerate(slide_names, start=1):
            slide_xml = archive.read(slide_name)
            paragraphs = pptx_slide_paragraphs(slide_xml)
            alt_texts = pptx_alt_texts(slide_xml)
            notes_name = pptx_notes_for_slide(archive, slide_name)
            notes_paragraphs = pptx_slide_paragraphs(archive.read(notes_name)) if notes_name else []
            slide_text = "\n".join(paragraphs)
            evidence_source = f"{rel}#slide{index}"
            paragraph_links: list[dict[str, Any]] = []
            text_sources = [
                ("slide_text", evidence_source, paragraphs, "pptx_slide_explicit_paths", 0.85),
                ("alt_text", f"{rel}#slide{index}:alt_text", alt_texts, "pptx_alt_text_explicit_paths", 0.75),
                ("speaker_notes", f"{rel}#slide{index}:speaker_notes", notes_paragraphs, "pptx_notes_explicit_paths", 0.80),
            ]
            for source_type, source_evidence, source_paragraphs, extraction_method, confidence in text_sources:
                for paragraph_index, paragraph in enumerate(source_paragraphs, start=1):
                    mentions = path_mentions(paragraph, files)
                    for mention in mentions:
                        mention_payloads.append({
                            "source_pptx": rel,
                            "slide": index,
                            "source_type": source_type,
                            "paragraph": paragraph_index,
                            "evidence_source": source_evidence,
                            **mention,
                        })
                    paragraph_links.extend(
                        extract_line_links(
                            paragraph,
                            files,
                            source_evidence,
                            extraction_method=extraction_method,
                            confidence=confidence,
                        )
                    )
                combined_text = "\n".join(source_paragraphs)
                if combined_text:
                    paragraph_links.extend(
                        extract_line_links(
                            combined_text,
                            files,
                            source_evidence,
                            extraction_method=extraction_method,
                            confidence=confidence,
                        )
                    )
            slide_links = extract_line_links(
                slide_text,
                files,
                evidence_source,
                extraction_method="pptx_slide_explicit_paths",
                confidence=0.85,
            )
            links = unique_links([*paragraph_links, *slide_links])
            pptx_links.extend(links)
            slide_payloads.append({
                "source_pptx": rel,
                "slide": index,
                "slide_xml": slide_name,
                "notes_xml": notes_name or "",
                "paragraph_count": len(paragraphs),
                "alt_text_count": len(alt_texts),
                "speaker_note_paragraph_count": len(notes_paragraphs),
                "text_length": len(slide_text),
                "alt_text_length": len("\n".join(alt_texts)),
                "speaker_note_text_length": len("\n".join(notes_paragraphs)),
                "paragraphs": paragraphs,
                "alt_texts": alt_texts,
                "speaker_notes": notes_paragraphs,
                "path_mention_count": sum(1 for item in mention_payloads if item["source_pptx"] == rel and item["slide"] == index),
                "explicit_path_pair_count": len(links),
            })
    if not slide_payloads:
        warnings.append({
            "path": rel,
            "stage": "pptx_structure_extraction",
            "warning": "PPTX contained no readable slide text paragraphs",
        })
    return (
        {
            "path": rel,
            "slide_count": len(slide_payloads),
            "text_paragraph_count": sum(int(slide.get("paragraph_count", 0) or 0) for slide in slide_payloads),
            "alt_text_count": sum(int(slide.get("alt_text_count", 0) or 0) for slide in slide_payloads),
            "speaker_note_paragraph_count": sum(int(slide.get("speaker_note_paragraph_count", 0) or 0) for slide in slide_payloads),
            "path_mention_count": len([item for item in mention_payloads if item["source_pptx"] == rel]),
            "explicit_path_pair_count": len(pptx_links),
            "errors": [],
            "warnings": warnings,
        },
        slide_payloads,
        unique_links(pptx_links),
        mention_payloads,
    )


def scan(root: Path) -> dict[str, Any]:
    files, file_index_warnings = package_files(root)
    pptx_files: list[dict[str, Any]] = []
    slides: list[dict[str, Any]] = []
    explicit_path_pairs: list[dict[str, Any]] = []
    explicit_path_mentions: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = [
        {"stage": "package_file_index", "warning": warning}
        for warning in file_index_warnings
    ]

    for path in collect_pptx_files(root):
        rel = str(path.relative_to(root))
        if not zipfile.is_zipfile(path):
            error = {
                "path": rel,
                "stage": "pptx_structure_extraction",
                "error": "file is not a valid PPTX zip container",
            }
            pptx_files.append({
                "path": rel,
                "slide_count": 0,
                "text_paragraph_count": 0,
                "path_mention_count": 0,
                "explicit_path_pair_count": 0,
                "errors": [error],
                "warnings": [],
            })
            errors.append(error)
            continue
        try:
            pptx_payload, pptx_slides, pptx_links, pptx_mentions = scan_pptx(root, path, files)
            pptx_files.append(pptx_payload)
            slides.extend(pptx_slides)
            explicit_path_pairs.extend(pptx_links)
            explicit_path_mentions.extend(pptx_mentions)
            warnings.extend(pptx_payload.get("warnings", []) or [])
        except Exception as exc:  # noqa: BLE001 - keep PPTX intake best-effort.
            error = {
                "path": rel,
                "stage": "pptx_structure_extraction",
                "error": str(exc),
            }
            pptx_files.append({
                "path": rel,
                "slide_count": 0,
                "text_paragraph_count": 0,
                "path_mention_count": 0,
                "explicit_path_pair_count": 0,
                "errors": [error],
                "warnings": [],
            })
            errors.append(error)

    return {
        "schema_version": "0.2.0",
        "extractor": "scripts.pptx_structure_extract",
        "scope_note": (
            "Best-effort extraction of PPTX slide text, speaker notes, shape alt text, package-relative "
            "path mentions, and explicit figure/source path pairs for assembly-manifest preparation. "
            "This does not inspect slide geometry, embedded-object placement, PowerPoint edit history, "
            "or prove provenance."
        ),
        "input": {
            "package": str(root),
            "pptx_files": len(pptx_files),
        },
        "pptx_files": pptx_files,
        "slides": slides,
        "explicit_path_mentions": explicit_path_mentions,
        "explicit_path_pairs": unique_links(explicit_path_pairs),
        "warnings": warnings,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("pptx_structure.json"))
    args = parser.parse_args()

    root = args.package_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Package directory not found: {root}")
    payload = scan(root)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "pptx_files": payload["input"]["pptx_files"],
        "slides": len(payload["slides"]),
        "speaker_note_paragraphs": sum(int(item.get("speaker_note_paragraph_count", 0) or 0) for item in payload["slides"]),
        "alt_text_entries": sum(int(item.get("alt_text_count", 0) or 0) for item in payload["slides"]),
        "explicit_path_pairs": len(payload["explicit_path_pairs"]),
        "errors": len(payload["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
