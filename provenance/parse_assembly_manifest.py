#!/usr/bin/env python3
"""Extract declared figure-to-source links from assembly manifest text."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


IMAGE_OR_DATA_RE = re.compile(
    r"(?:(?:figures|raw_images|source_data)/)?[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:png|jpg|jpeg|tif|tiff|csv|tsv|xlsx|xls)",
    re.I,
)


def package_files(package: Path) -> dict[str, list[str]]:
    files: dict[str, list[str]] = {}
    for path in sorted(package.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(package))
        files.setdefault(path.name.lower(), []).append(rel)
        files.setdefault(rel.lower(), []).append(rel)
    return files


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


def manifest_files(package: Path) -> list[Path]:
    assembly_dir = package / "figure_assembly"
    if not assembly_dir.exists():
        return []
    return [
        path for path in sorted(assembly_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".txt", ".md", ".csv", ".tsv"}
    ]


def extract_line_links(line: str, files: dict[str, list[str]], evidence_source: str) -> list[dict[str, Any]]:
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
                "confidence": 0.95,
                "risk_effect": "expected_traceability",
                "extraction_method": "same_line_explicit_paths",
            })
    return links


def infer_ordered_links(text: str, package: Path, files: dict[str, list[str]], evidence_source: str) -> list[dict[str, Any]]:
    lower = text.lower()
    if "figure panels map to" not in lower and "figures map to" not in lower:
        return []
    raw_refs = []
    for match in IMAGE_OR_DATA_RE.finditer(text):
        resolved = resolve_token(match.group(0), files)
        if resolved and role(resolved) in {"raw_image", "source_data"} and resolved not in raw_refs:
            raw_refs.append(resolved)
    figure_paths = [
        str(path.relative_to(package))
        for path in sorted((package / "figures").rglob("*"))
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
    ] if (package / "figures").exists() else []
    if len(figure_paths) != len(raw_refs) or not figure_paths:
        return []
    links = []
    for figure, source in zip(figure_paths, raw_refs):
        links.append({
            "source_path": figure,
            "target_path": source,
            "relation_type": "declared_derived_from",
            "evidence_source": evidence_source,
            "confidence": 0.75,
            "risk_effect": "expected_traceability",
            "extraction_method": "ordered_figure_panels_map_to_list",
        })
    return links


def parse_package(package: Path) -> dict[str, Any]:
    files = package_files(package)
    links: list[dict[str, Any]] = []
    parsed_files = []
    warnings = []
    for manifest in manifest_files(package):
        rel = str(manifest.relative_to(package))
        parsed_files.append(rel)
        text = manifest.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            links.extend(extract_line_links(line, files, rel))
        links.extend(infer_ordered_links(text, package, files, rel))

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
        "parser_version": "0.3.1",
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
