#!/usr/bin/env python3
"""Create candidate figure-source relationships from a package manifest."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


FIG_RE = re.compile(r"(?:fig(?:ure)?|supp(?:lementary)?|s)[_\-\s\.]*(\d+|[ivx]+)([a-z])?", re.IGNORECASE)


def figure_key(path: str) -> str | None:
    match = FIG_RE.search(Path(path).stem)
    if not match:
        return None
    number = match.group(1).lower()
    panel = (match.group(2) or "").lower()
    return f"fig{number}{panel}"


def build_map(manifest: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, dict[str, list[dict[str, Any]]]] = {}
    unmapped = []
    for item in manifest.get("files", []):
        key = figure_key(item["path"])
        if not key:
            if item["category"] in {"figures", "source_data", "raw_images", "figure_assembly"}:
                unmapped.append(item)
            continue
        groups.setdefault(key, {}).setdefault(item["category"], []).append(item)

    candidates = []
    for key, by_category in sorted(groups.items()):
        candidates.append({
            "figure_key": key,
            "figures": by_category.get("figures", []),
            "source_data": by_category.get("source_data", []),
            "raw_images": by_category.get("raw_images", []),
            "figure_assembly": by_category.get("figure_assembly", []),
            "status": "candidate_mapping",
            "notes": "Filename-based mapping only; manually verify panel labels and source-data rows.",
        })
    return {"candidate_maps": candidates, "unmapped_relevant_files": unmapped}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, default=Path("figure_source_map.json"))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = build_map(manifest)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "candidate_maps": len(result["candidate_maps"]),
        "unmapped_relevant_files": len(result["unmapped_relevant_files"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
