#!/usr/bin/env python3
"""Build a package-level provenance graph from manifest and extracted links."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from calibrators.contract_validation import validate_instance  # noqa: E402


GRAPH_SCHEMA = ROOT / "schemas" / "provenance_graph.schema.json"


ROLE_BY_CATEGORY = {
    "figures": "figure_panel",
    "raw_images": "raw_image",
    "source_data": "source_data",
    "figure_assembly": "assembly_file",
    "manuscript": "manuscript",
    "supplementary": "supplementary",
    "protocols": "protocol",
    "statistics_code": "analysis_code",
}


def resource_id(path: str, idx: int) -> str:
    stem = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_").lower()
    return f"res_{idx:04d}_{stem[:48]}"


def build_nodes(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    nodes = []
    path_to_id = {}
    for idx, item in enumerate(manifest.get("files", []) or [], start=1):
        path = str(item.get("path", ""))
        if not path:
            continue
        rid = resource_id(path, idx)
        path_to_id[path] = rid
        nodes.append({
            "resource_id": rid,
            "path": path,
            "role": ROLE_BY_CATEGORY.get(item.get("category", ""), item.get("category", "resource")),
            "category": item.get("category", ""),
            "extension": item.get("extension", ""),
            "sha256": item.get("sha256", ""),
            "size_bytes": int(item.get("size_bytes", 0)),
        })
    return nodes, path_to_id


def load_links(paths: list[Path]) -> list[dict[str, Any]]:
    links = []
    for path in paths:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        links.extend(payload.get("links", []) or [])
    return links


def build_edges(links: list[dict[str, Any]], path_to_id: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    edges = []
    warnings = []
    seen = set()
    for link in links:
        source_path = str(link.get("source_path", ""))
        target_path = str(link.get("target_path", ""))
        source_id = path_to_id.get(source_path)
        target_id = path_to_id.get(target_path)
        if not source_id or not target_id:
            warnings.append(f"Link references a file outside the manifest: {source_path} -> {target_path}")
            continue
        key = (source_path, target_path, link.get("relation_type", ""))
        if key in seen:
            continue
        seen.add(key)
        edge = {
            "edge_id": f"edge_{len(edges) + 1:04d}",
            "source": source_id,
            "target": target_id,
            "source_path": source_path,
            "target_path": target_path,
            "relation_type": str(link.get("relation_type", "declared_derived_from")),
            "evidence_source": str(link.get("evidence_source", "")),
            "confidence": float(link.get("confidence", 0.5)),
            "risk_effect": str(link.get("risk_effect", "candidate_traceability")),
        }
        modality = str(link.get("modality", "") or "").strip()
        if modality:
            edge["modality"] = modality
        edges.append(edge)
    return edges, warnings


def build_graph(manifest: dict[str, Any], link_paths: list[Path]) -> dict[str, Any]:
    nodes, path_to_id = build_nodes(manifest)
    edges, warnings = build_edges(load_links(link_paths), path_to_id)
    graph = {
        "graph_version": "0.3.2",
        "package_root": str(manifest.get("root", "")),
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
    }
    validate_instance(graph, GRAPH_SCHEMA, "provenance graph")
    return graph


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--links", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, default=Path("provenance_graph.json"))
    args = parser.parse_args()

    manifest = json.loads(args.manifest.expanduser().resolve().read_text(encoding="utf-8"))
    graph = build_graph(manifest, [path.expanduser().resolve() for path in args.links])
    args.output.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "nodes": len(graph["nodes"]), "edges": len(graph["edges"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
