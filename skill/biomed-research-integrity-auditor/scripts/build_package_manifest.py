#!/usr/bin/env python3
"""Inventory a biomedical manuscript package and classify audit materials."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


CATEGORY_RULES = [
    ("manuscript", ("manuscript", "paper", "article", "maintext"), {".pdf", ".docx", ".doc"}),
    ("supplementary", ("supp", "supplement", "supplementary", "appendix"), None),
    ("source_data", ("source", "sourcedata", "source-data", "data"), {".csv", ".tsv", ".xlsx", ".xls"}),
    ("figures", ("fig", "figure", "panel"), {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".pdf", ".svg"}),
    ("figure_assembly", ("assembly", "figure", "fig"), {".pptx", ".ppt", ".ai", ".psd", ".indd", ".svg"}),
    ("raw_images", ("raw", "original", "uncropped", "unprocessed", "czi", "nd2", "lif"), {
        ".tif", ".tiff", ".czi", ".nd2", ".lif", ".oib", ".oir", ".svs", ".vsi", ".png", ".jpg", ".jpeg"
    }),
    ("protocols", ("protocol", "method", "eln", "notebook", "samplemap", "sample_map", "batch"), {
        ".pdf", ".docx", ".doc", ".txt", ".md", ".csv", ".xlsx", ".xls"
    }),
    ("statistics_code", ("stats", "analysis", "code", "script", "prism", "graphpad"), {
        ".r", ".rmd", ".py", ".ipynb", ".m", ".sas", ".do", ".pzfx", ".csv", ".xlsx"
    }),
    ("ethics_irb", ("ethics", "irb", "iacuc", "approval", "consent"), None),
    ("clinical_registration", ("nct", "clinicaltrials", "chictr", "registry", "registration"), None),
    ("omics_accession", ("geo", "sra", "arrayexpress", "pride", "proteomexchange", "accession"), None),
    ("flow_fcs", ("flow", "fcs", "flowjo", "workspace", "gating"), {".fcs", ".wsp", ".jo", ".pdf", ".png", ".tif", ".tiff"}),
]

BASE_EXPECTED = {
    "internal": ["manuscript", "supplementary", "source_data", "figures"],
    "external": ["manuscript"],
}

DOMAIN_EXPECTED = {
    "wetlab": ["raw_images", "figure_assembly"],
    "animal": ["protocols", "ethics_irb"],
    "cell": ["protocols"],
    "clinical": ["clinical_registration", "ethics_irb", "protocols"],
    "omics": ["omics_accession", "source_data", "statistics_code"],
    "flow": ["flow_fcs", "protocols"],
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(path: Path) -> str:
    lowered = str(path).lower()
    suffix = path.suffix.lower()
    scores: dict[str, int] = {}
    for category, keywords, suffixes in CATEGORY_RULES:
        if suffixes is not None and suffix not in suffixes:
            continue
        score = sum(1 for kw in keywords if kw in lowered)
        if score:
            scores[category] = score
    if scores:
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return "other"


def expected_categories(mode: str, domains: list[str]) -> list[str]:
    expected = list(BASE_EXPECTED.get(mode, BASE_EXPECTED["internal"]))
    for domain in domains:
        expected.extend(DOMAIN_EXPECTED.get(domain.strip().lower(), []))
    return sorted(set(expected))


def build_manifest(root: Path, mode: str, domains: list[str]) -> dict[str, Any]:
    files = []
    category_counts: dict[str, int] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        category = classify(path.relative_to(root))
        category_counts[category] = category_counts.get(category, 0) + 1
        files.append({
            "path": str(path.relative_to(root)),
            "category": category,
            "extension": path.suffix.lower(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    expected = expected_categories(mode, domains)
    missing = [
        {
            "category": category,
            "risk_level": "R1",
            "reason": f"No files classified as {category}.",
        }
        for category in expected
        if category_counts.get(category, 0) == 0
    ]
    return {
        "root": str(root),
        "mode": mode,
        "domains": domains,
        "category_counts": category_counts,
        "expected_categories": expected,
        "missing_materials": missing,
        "files": files,
    }


def markdown_matrix(manifest: dict[str, Any]) -> str:
    rows = ["| Category | Supplied files | Status |", "| --- | ---: | --- |"]
    counts = manifest["category_counts"]
    missing = {item["category"] for item in manifest["missing_materials"]}
    for category in manifest["expected_categories"]:
        count = counts.get(category, 0)
        status = "missing (R1)" if category in missing else "supplied"
        rows.append(f"| {category} | {count} | {status} |")
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Package directory to inventory")
    parser.add_argument("--mode", choices=["internal", "external"], default="internal")
    parser.add_argument("--domains", default="", help="Comma-separated domains: wetlab,animal,cell,clinical,omics,flow")
    parser.add_argument("--output", type=Path, default=Path("manifest.json"))
    parser.add_argument("--markdown", type=Path, help="Optional Markdown missing-materials matrix")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Package directory not found: {root}")

    domains = [d.strip().lower() for d in args.domains.split(",") if d.strip()]
    manifest = build_manifest(root, args.mode, domains)
    args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(markdown_matrix(manifest), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "files": len(manifest["files"]),
        "missing_materials": len(manifest["missing_materials"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
