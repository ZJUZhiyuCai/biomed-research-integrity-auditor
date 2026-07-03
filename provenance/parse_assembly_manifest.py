#!/usr/bin/env python3
"""Extract declared figure-to-source links from assembly manifests."""

from __future__ import annotations

import argparse
import csv
import json
import posixpath
import re
import zipfile
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[1]

from provenance.panel_modality import normalize_modality


IMAGE_OR_DATA_RE = re.compile(
    r"(?:(?:figures|raw_images|source_data)/)?[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:png|jpg|jpeg|tif|tiff|csv|tsv|xlsx|xls)",
    re.I,
)
STRUCTURED_SUFFIXES = {".csv", ".tsv", ".yaml", ".yml"}
TEXT_SUFFIXES = {".txt", ".md"}
PPTX_SUFFIXES = {".pptx"}
A_TEXT = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
A_PARAGRAPH = "{http://schemas.openxmlformats.org/drawingml/2006/main}p"
P_CNVPR = "{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr"
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
SOURCE_ROLES = {"raw_image", "source_data"}
PACKAGE_FILE_SCAN_LIMIT = 10000
PACKAGE_FILE_MAX_DEPTH = 12
EXPECTED_RELATION_TYPES = {
    "declared_derived_from",
    "same_field_different_channel",
    "same_membrane_reprobe",
    "declared_same_source",
}
FIGURE_FIGURE_TRACEABILITY_RELATIONS = {
    "same_field_different_channel",
    "same_membrane_reprobe",
}


def bounded_files(
    root: Path,
    package: Path,
    max_files: int = PACKAGE_FILE_SCAN_LIMIT,
    max_depth: int = PACKAGE_FILE_MAX_DEPTH,
) -> tuple[list[Path], list[str], bool]:
    files: list[Path] = []
    warnings: list[str] = []
    pending: list[tuple[Path, int]] = [(root, 0)]
    while pending:
        directory, depth = pending.pop(0)
        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name.lower())
        except OSError as exc:
            rel = directory.relative_to(package).as_posix() if directory != package else "."
            warnings.append(f"Could not read {rel}: {exc.__class__.__name__}")
            continue
        for entry in entries:
            rel = entry.relative_to(package).as_posix()
            if entry.is_symlink():
                warnings.append(f"Skipped symlink: {rel}")
                continue
            if entry.is_dir():
                if depth >= max_depth:
                    warnings.append(f"Skipped directory beyond max depth {max_depth}: {rel}")
                    continue
                pending.append((entry, depth + 1))
                continue
            if not entry.is_file():
                continue
            files.append(entry)
            if len(files) >= max_files:
                warnings.append(
                    f"Package file index stopped after {max_files} files; choose a narrower package directory."
                )
                return files, warnings, True
    return files, warnings, False


def package_files(package: Path) -> tuple[dict[str, list[str]], list[str]]:
    files: dict[str, list[str]] = {}
    paths, warnings, _ = bounded_files(package, package)
    for path in paths:
        rel = str(path.relative_to(package))
        files.setdefault(path.name.lower(), []).append(rel)
        files.setdefault(rel.lower(), []).append(rel)
    return files, warnings


def resolve_token(token: str, files: dict[str, list[str]]) -> str | None:
    token = token.strip().strip(".,;:()[]{}\"'").replace("\\", "/")
    matches = files.get(token.lower())
    if matches:
        return matches[0]
    matches = files.get(Path(token).name.lower())
    if matches:
        return matches[0]
    return token if "/" in token else None


def role(path: str) -> str:
    if path.startswith("figures/"):
        return "figure_panel"
    if path.startswith("raw_images/"):
        return "raw_image"
    if path.startswith("source_data/"):
        return "source_data"
    return "resource"


def manifest_files(package: Path, suffixes: set[str], files: dict[str, list[str]]) -> list[Path]:
    assembly_dir = package / "figure_assembly"
    if not assembly_dir.exists():
        return []
    return [
        package / rel
        for rel in sorted({
            rel
            for matches in files.values()
            for rel in matches
            if rel.startswith("figure_assembly/") and Path(rel).suffix.lower() in suffixes
        })
    ]


def structured_link_from_row(
    row: dict[str, Any],
    files: dict[str, list[str]],
    evidence_source: str,
    extraction_method: str,
    row_number: int | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    figure = resolve_token(str(row.get("figure_panel", "") or ""), files)
    source = resolve_token(str(row.get("source_record", "") or ""), files)
    if not figure or not source:
        return None, None
    relation_type = str(row.get("relation_type", "") or "declared_derived_from").strip() or "declared_derived_from"
    relation_key = relation_type.lower()
    if relation_key not in EXPECTED_RELATION_TYPES:
        row_label = f" row {row_number}" if row_number is not None else ""
        allowed = ", ".join(sorted(EXPECTED_RELATION_TYPES))
        return (
            None,
            (
                f"{evidence_source}{row_label} uses unsupported relation_type; "
                f"expected one of: {allowed}. The row was ignored for traceability calibration."
            ),
        )
    target_role = role(source)
    if role(figure) != "figure_panel":
        return None, None
    if target_role not in SOURCE_ROLES and not (target_role == "figure_panel" and relation_key in EXPECTED_RELATION_TYPES):
        return None, None
    if target_role in SOURCE_ROLES:
        risk_effect = "expected_traceability"
        confidence = 0.98
    elif target_role == "figure_panel" and relation_key in FIGURE_FIGURE_TRACEABILITY_RELATIONS:
        risk_effect = "expected_traceability"
        confidence = 0.98
    else:
        risk_effect = "candidate_traceability"
        confidence = 0.5
    link = {
        "source_path": figure,
        "target_path": source,
        "relation_type": relation_key,
        "evidence_source": evidence_source,
        "confidence": confidence,
        "risk_effect": risk_effect,
        "extraction_method": extraction_method,
    }
    link["modality"] = normalize_modality(str(row.get("modality", "") or ""))
    return link, None


def parse_structured_csv(path: Path, package: Path, files: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[str]]:
    rel = str(path.relative_to(package))
    warnings: list[str] = []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    text = path.read_text(encoding="utf-8", errors="ignore")
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    fieldnames = set(reader.fieldnames or [])
    required = {"figure_panel", "source_record"}
    if not required.issubset(fieldnames):
        warnings.append(f"{rel} missing required structured manifest columns: figure_panel, source_record")
        return [], warnings
    row_warning_start = len(warnings)
    links = []
    for index, row in enumerate(reader, start=2):
        link, warning = structured_link_from_row(row, files, rel, "structured_csv_manifest", index)
        if warning:
            warnings.append(warning)
        if link:
            links.append(link)
    if not links and len(warnings) == row_warning_start:
        warnings.append(f"{rel} did not contain parseable structured figure-source rows.")
    return links, warnings


def yaml_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("links", "mappings", "figure_links", "assembly_links"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def parse_structured_yaml(path: Path, package: Path, files: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[str]]:
    rel = str(path.relative_to(package))
    warnings: list[str] = []
    payload = yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore")) or []
    records = yaml_records(payload)
    if not records:
        warnings.append(f"{rel} did not contain a list of structured figure-source rows.")
        return [], warnings
    row_warning_start = len(warnings)
    links = []
    for index, row in enumerate(records, start=1):
        link, warning = structured_link_from_row(row, files, rel, "structured_yaml_manifest", index)
        if warning:
            warnings.append(warning)
        if link:
            links.append(link)
    if not links and len(warnings) == row_warning_start:
        warnings.append(f"{rel} did not contain parseable structured figure-source rows.")
    return links, warnings


def parse_structured_manifest(path: Path, package: Path, files: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[str]]:
    if path.suffix.lower() in {".csv", ".tsv"}:
        return parse_structured_csv(path, package, files)
    return parse_structured_yaml(path, package, files)


def extract_line_links(
    line: str,
    files: dict[str, list[str]],
    evidence_source: str,
    extraction_method: str = "same_line_explicit_paths",
    confidence: float = 0.95,
) -> list[dict[str, Any]]:
    tokens = [resolve_token(match.group(0), files) for match in IMAGE_OR_DATA_RE.finditer(line)]
    paths = [token for token in tokens if token]
    figures = [path for path in paths if role(path) == "figure_panel"]
    sources = [path for path in paths if role(path) in {"raw_image", "source_data"}]
    links = []
    for figure in figures:
        for source in sources:
            links.append({
                "source_path": figure,
                "target_path": source,
                "relation_type": "declared_derived_from",
                "evidence_source": evidence_source,
                "confidence": confidence,
                "risk_effect": "expected_traceability",
                "extraction_method": extraction_method,
            })
    return links


def pptx_slide_sort_key(name: str) -> tuple[int, str]:
    match = re.search(r"slide(\d+)\.xml$", name)
    return (int(match.group(1)) if match else 0, name)


def pptx_slide_paragraphs(xml_bytes: bytes) -> list[str]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    paragraphs: list[str] = []
    for paragraph in root.iter(A_PARAGRAPH):
        text = " ".join(
            node.text.strip()
            for node in paragraph.iter(A_TEXT)
            if node.text and node.text.strip()
        ).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def pptx_alt_texts(xml_bytes: bytes) -> list[str]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    texts: list[str] = []
    seen: set[str] = set()
    for node in root.iter(P_CNVPR):
        for attr in ("descr", "title"):
            text = str(node.attrib.get(attr, "") or "").strip()
            if text and text not in seen:
                seen.add(text)
                texts.append(text)
    return texts


def pptx_notes_for_slide(archive: zipfile.ZipFile, slide_name: str) -> str | None:
    rels_name = posixpath.join(
        posixpath.dirname(slide_name),
        "_rels",
        posixpath.basename(slide_name) + ".rels",
    )
    names = set(archive.namelist())
    if rels_name in names:
        try:
            root = ET.fromstring(archive.read(rels_name))
            for rel in root.iter(f"{REL_NS}Relationship"):
                rel_type = str(rel.attrib.get("Type", "") or "")
                if rel_type.endswith("/notesSlide"):
                    target = str(rel.attrib.get("Target", "") or "")
                    if target:
                        notes_name = posixpath.normpath(posixpath.join(posixpath.dirname(slide_name), target))
                        if notes_name in names:
                            return notes_name
        except ET.ParseError:
            return None
    match = re.search(r"slide(\d+)\.xml$", slide_name)
    if match:
        fallback = f"ppt/notesSlides/notesSlide{match.group(1)}.xml"
        if fallback in names:
            return fallback
    return None


def pptx_text_sources_for_slide(
    archive: zipfile.ZipFile,
    slide_name: str,
    rel: str,
    index: int,
) -> list[tuple[str, list[str], str, float]]:
    slide_xml = archive.read(slide_name)
    sources: list[tuple[str, list[str], str, float]] = [
        (
            f"{rel}#slide{index}",
            pptx_slide_paragraphs(slide_xml),
            "pptx_slide_explicit_paths",
            0.85,
        )
    ]
    alt_texts = pptx_alt_texts(slide_xml)
    if alt_texts:
        sources.append((
            f"{rel}#slide{index}:alt_text",
            alt_texts,
            "pptx_alt_text_explicit_paths",
            0.75,
        ))
    notes_name = pptx_notes_for_slide(archive, slide_name)
    if notes_name:
        notes_paragraphs = pptx_slide_paragraphs(archive.read(notes_name))
        if notes_paragraphs:
            sources.append((
                f"{rel}#slide{index}:speaker_notes",
                notes_paragraphs,
                "pptx_notes_explicit_paths",
                0.80,
            ))
    return sources


def parse_pptx_manifest(path: Path, package: Path, files: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[str]]:
    rel = str(path.relative_to(package))
    warnings: list[str] = []
    links: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path) as archive:
            slide_names = sorted(
                [
                    name for name in archive.namelist()
                    if re.match(r"ppt/slides/slide\d+\.xml$", name)
                ],
                key=pptx_slide_sort_key,
            )
            for index, slide_name in enumerate(slide_names, start=1):
                for evidence_source, paragraphs, extraction_method, confidence in pptx_text_sources_for_slide(
                    archive,
                    slide_name,
                    rel,
                    index,
                ):
                    if not paragraphs:
                        continue
                    for paragraph in paragraphs:
                        links.extend(
                            extract_line_links(
                                paragraph,
                                files,
                                evidence_source,
                                extraction_method=extraction_method,
                                confidence=confidence,
                            )
                        )
                    combined_text = "\n".join(paragraphs)
                    links.extend(
                        extract_line_links(
                            combined_text,
                            files,
                            evidence_source,
                            extraction_method=extraction_method,
                            confidence=confidence,
                        )
                    )
    except Exception as exc:  # noqa: BLE001 - parser warnings should not abort the audit.
        warnings.append(f"{rel} could not be parsed as PPTX assembly text: {exc.__class__.__name__}")
        return [], warnings
    if not links:
        warnings.append(f"{rel} did not contain explicit figure-to-source path pairs in slide text, alt text, or speaker notes.")
    return links, warnings


def ordered_mapping_warning(text: str, evidence_source: str) -> str | None:
    lower = text.lower()
    if "figure panels map to" not in lower and "figures map to" not in lower:
        return None
    return (
        f"{evidence_source} contains an ordered prose mapping phrase. Ordered figure-to-source "
        "lists are ignored for traceability calibration; use structured CSV/YAML rows with "
        "figure_panel, source_record, and relation_type columns."
    )


def parse_package(package: Path) -> dict[str, Any]:
    files, file_index_warnings = package_files(package)
    links: list[dict[str, Any]] = []
    parsed_files = []
    warnings = list(file_index_warnings)
    structured_files = manifest_files(package, STRUCTURED_SUFFIXES, files)
    text_files = [] if structured_files else manifest_files(package, TEXT_SUFFIXES, files)
    pptx_files = [] if structured_files else manifest_files(package, PPTX_SUFFIXES, files)

    for manifest in structured_files:
        rel = str(manifest.relative_to(package))
        parsed_files.append(rel)
        extracted, structured_warnings = parse_structured_manifest(manifest, package, files)
        links.extend(extracted)
        warnings.extend(structured_warnings)

    for manifest in text_files:
        rel = str(manifest.relative_to(package))
        parsed_files.append(rel)
        text = manifest.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            links.extend(extract_line_links(line, files, rel))
        warning = ordered_mapping_warning(text, rel)
        if warning:
            warnings.append(warning)

    for manifest in pptx_files:
        rel = str(manifest.relative_to(package))
        parsed_files.append(rel)
        extracted, pptx_warnings = parse_pptx_manifest(manifest, package, files)
        links.extend(extracted)
        warnings.extend(pptx_warnings)

    seen = set()
    unique_links = []
    for link in links:
        key = (link["source_path"], link["target_path"], link["relation_type"], link["evidence_source"])
        if key in seen:
            continue
        seen.add(key)
        unique_links.append(link)
    if not parsed_files:
        warnings.append("No figure_assembly manifest files were supplied.")
    return {
        "parser": "provenance.parse_assembly_manifest",
        "parser_version": "0.5.0",
        "package": str(package),
        "parsed_files": parsed_files,
        "links": unique_links,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path, default=Path("assembly_links.json"))
    args = parser.parse_args()

    package = args.package.expanduser().resolve()
    result = parse_package(package)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "links": len(result["links"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
