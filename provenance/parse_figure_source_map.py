#!/usr/bin/env python3
"""Standardize figure_source_map.py output into provenance links."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def item_paths(items: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("path", "")) for item in items if item.get("path")]


def standardize(mapping: dict[str, Any], evidence_source: str) -> dict[str, Any]:
    links = []
    for candidate in mapping.get("candidate_maps", []) or []:
        figures = item_paths(candidate.get("figures", []) or [])
        sources = item_paths(candidate.get("raw_images", []) or []) + item_paths(candidate.get("source_data", []) or [])
        for figure in figures:
            for source in sources:
                links.append({
                    "source_path": figure,
                    "target_path": source,
                    "relation_type": "filename_candidate_derived_from",
                    "evidence_source": evidence_source,
                    "confidence": 0.55,
                    "risk_effect": "candidate_traceability",
                    "figure_key": candidate.get("figure_key", ""),
                })
    return {
        "parser": "provenance.parse_figure_source_map",
        "parser_version": "0.3.1",
        "links": links,
        "warnings": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("figure_source_map", type=Path)
    parser.add_argument("--output", type=Path, default=Path("figure_source_links.json"))
    args = parser.parse_args()

    mapping_path = args.figure_source_map.expanduser().resolve()
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    result = standardize(mapping, str(mapping_path))
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "links": len(result["links"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
