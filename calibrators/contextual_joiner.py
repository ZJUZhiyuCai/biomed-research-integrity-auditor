#!/usr/bin/env python3
"""Join detector candidates with package context before risk calibration."""

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


DETECTOR_SCHEMA = ROOT / "schemas" / "detector_output.schema.json"
TEXT_EXTS = {".txt", ".md", ".pdf", ".csv", ".tsv", ".json", ".yaml", ".yml"}
SOURCE_EXTS = {".csv", ".tsv", ".xlsx", ".xls"}
RAW_IMAGE_EXTS = {".czi", ".nd2", ".lif", ".oib", ".oir", ".svs", ".vsi", ".tif", ".tiff", ".png", ".jpg", ".jpeg"}


def read_package_text(package: Path) -> str:
    chunks = []
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001 - context extraction should be best effort.
            continue
        if text.strip():
            chunks.append(f"\n--- {path.relative_to(package)} ---\n{text}")
    return "\n".join(chunks).lower()


def has_source_data(package: Path) -> bool:
    source_dir = package / "source_data"
    return source_dir.exists() and any(path.is_file() and path.suffix.lower() in SOURCE_EXTS for path in source_dir.rglob("*"))


def has_raw_images(package: Path) -> bool:
    raw_dir = package / "raw_images"
    return raw_dir.exists() and any(path.is_file() and path.suffix.lower() in RAW_IMAGE_EXTS for path in raw_dir.rglob("*"))


def contains_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def package_context(package: Path) -> dict[str, Any]:
    text = read_package_text(package)
    reuse_disclosed = contains_any(text, [
        r"\bdisclos\w*\b.{0,80}\breus\w*\b",
        r"\breus\w*\b.{0,80}\bdisclos\w*\b",
        r"\bintentionally reused\b",
        r"\bsame loading control\b",
        r"\bsame gapdh loading control\b",
        r"\bloading control was reused\b",
        r"\bsame membrane\b",
        r"\breprobed\b",
    ])
    loading_control_disclosed = "loading control" in text and contains_any(text, [r"\breus\w*\b", r"\bsame\b"])
    negated_same_membrane = contains_any(text, [
        r"does not state.{0,80}same membrane",
        r"not state.{0,80}same membrane",
        r"no shared membrane",
        r"no same membrane",
        r"without.{0,80}same membrane",
    ])
    same_membrane_claimed = not negated_same_membrane and contains_any(text, [
        r"\bsame membrane\b",
        r"\bshared membrane\b",
        r"\bmembrane was reprobed\b",
        r"\breprobed\b",
    ])
    same_experiment_claimed = not negated_same_membrane and contains_any(text, [
        r"\bsame experiment\b",
        r"\bsame membrane\b",
        r"\bshared membrane\b",
        r"\breprobed\b",
    ])
    source_available = has_source_data(package)
    raw_available = has_raw_images(package)
    risk_cap_tags = []
    if reuse_disclosed and loading_control_disclosed and (same_membrane_claimed or same_experiment_claimed) and (source_available or raw_available):
        risk_cap_tags.append("disclosed_legitimate_reuse")
    elif reuse_disclosed:
        risk_cap_tags.append("disclosed_unjustified_reuse")

    return {
        "reuse_disclosed": reuse_disclosed,
        "loading_control_disclosed": loading_control_disclosed,
        "same_experiment_claimed": same_experiment_claimed,
        "same_membrane_claimed": same_membrane_claimed,
        "source_data_available": source_available,
        "raw_images_available": raw_available,
        "risk_cap_tags": risk_cap_tags,
    }


def is_image_candidate(candidate: dict[str, Any]) -> bool:
    joined = " ".join(str(candidate.get(key, "")) for key in ("detector", "candidate_type"))
    return "image" in joined


def load_provenance(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"nodes": [], "edges": []}
    return json.loads(path.read_text(encoding="utf-8"))


def role_from_path(path: str, provenance: dict[str, Any]) -> str:
    for node in provenance.get("nodes", []) or []:
        if node.get("path") == path:
            return str(node.get("role", "resource"))
    if path.startswith("figures/"):
        return "figure_panel"
    if path.startswith("raw_images/"):
        return "raw_image"
    if path.startswith("source_data/"):
        return "source_data"
    return "resource"


def undirected_pair(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))


def declared_traceability_pairs(provenance: dict[str, Any]) -> set[tuple[str, str]]:
    pairs = set()
    for edge in provenance.get("edges", []) or []:
        if edge.get("risk_effect") == "expected_traceability":
            pairs.add(undirected_pair(str(edge.get("source_path", "")), str(edge.get("target_path", ""))))
    return pairs


def provenance_edge_for_pair(left: str, right: str, provenance: dict[str, Any]) -> dict[str, Any] | None:
    pair = undirected_pair(left, right)
    for edge in provenance.get("edges", []) or []:
        if undirected_pair(str(edge.get("source_path", "")), str(edge.get("target_path", ""))) == pair:
            return edge
    return None


def edge_paths(edge: dict[str, Any]) -> tuple[str, str]:
    return str(edge.get("left", "")), str(edge.get("right", ""))


def classify_similarity_edge(
    edge: dict[str, Any],
    context: dict[str, Any],
    provenance: dict[str, Any],
    declared_pairs: set[tuple[str, str]],
) -> dict[str, Any]:
    left, right = edge_paths(edge)
    left_role = role_from_path(left, provenance)
    right_role = role_from_path(right, provenance)
    classified = dict(edge)
    classified["left_role"] = left_role
    classified["right_role"] = right_role
    is_local_patch = edge.get("similarity_scope") == "local_patch"

    if undirected_pair(left, right) in declared_pairs:
        classified.update({
            "contextual_tag": "expected_traceability",
            "reportable_as_risk": False,
            "positive_evidence": True,
            "risk_suggestion": "R0_positive_traceability",
            "provenance_edge": provenance_edge_for_pair(left, right, provenance),
        })
        return classified

    roles = {left_role, right_role}
    if roles == {"figure_panel", "raw_image"}:
        classified.update({
            "contextual_tag": "unresolved_fig_raw_similarity",
            "reportable_as_risk": True,
            "positive_evidence": False,
            "risk_suggestion": "R1_max",
            "required_materials_to_resolve": [
                "figure-source map",
                "assembly manifest",
                "raw image metadata",
            ],
        })
        return classified

    if left_role == "figure_panel" and right_role == "figure_panel":
        if "disclosed_legitimate_reuse" in context.get("risk_cap_tags", []):
            tag = "disclosed_legitimate_reuse"
            suggestion = "R2_max"
        elif "disclosed_unjustified_reuse" in context.get("risk_cap_tags", []):
            tag = "disclosed_unjustified_reuse"
            suggestion = "R3_possible"
        else:
            tag = "local_patch_cross_context" if is_local_patch else "cross_context_reuse_candidate"
            suggestion = "R3_possible"
        classified.update({
            "contextual_tag": tag,
            "reportable_as_risk": True,
            "positive_evidence": False,
            "risk_suggestion": suggestion,
        })
        return classified

    classified.update({
        "contextual_tag": "unresolved_similarity",
        "reportable_as_risk": True,
        "positive_evidence": False,
        "risk_suggestion": "R2_or_R3_pending_context",
    })
    return classified


def risk_edges_for_cluster(classified_edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reuse_tags = {
        "cross_context_reuse_candidate",
        "local_patch_cross_context",
        "disclosed_legitimate_reuse",
        "disclosed_unjustified_reuse",
        "manifest_conflict",
    }
    reuse_edges = [edge for edge in classified_edges if edge.get("contextual_tag") in reuse_tags]
    if reuse_edges:
        return reuse_edges
    return [edge for edge in classified_edges if edge.get("reportable_as_risk")]


def candidate_from_edges(candidate: dict[str, Any], risk_edges: list[dict[str, Any]], positive_edges: list[dict[str, Any]], context: dict[str, Any], provenance_path: str | None) -> dict[str, Any] | None:
    if not risk_edges:
        return None
    tags = {str(edge.get("contextual_tag", "")) for edge in risk_edges if edge.get("contextual_tag")}
    original_tags = set(str(tag) for tag in candidate.get("risk_cap_tags", []) or [])
    locations = sorted({path for edge in risk_edges for path in edge_paths(edge) if path})
    source_candidate_type = str(candidate.get("candidate_type", ""))

    if "local_patch_cross_context" in tags:
        candidate_type = "local_patch_reuse"
        risk_suggestion = "R3_possible"
        evidence_strength = "candidate"
    elif "cross_context_reuse_candidate" in tags:
        candidate_type = "local_patch_reuse" if source_candidate_type == "local_patch_reuse" else "image_reuse_cluster"
        risk_suggestion = "R3_possible"
        evidence_strength = "candidate"
    elif "disclosed_unjustified_reuse" in tags:
        candidate_type = "local_patch_reuse" if source_candidate_type == "local_patch_reuse" else "image_reuse_cluster"
        risk_suggestion = "R3_possible"
        evidence_strength = "candidate"
    elif "disclosed_legitimate_reuse" in tags:
        candidate_type = "local_patch_reuse" if source_candidate_type == "local_patch_reuse" else "image_reuse_cluster"
        risk_suggestion = "R3_possible_pending_context"
        evidence_strength = "candidate"
    elif "unresolved_fig_raw_similarity" in tags:
        candidate_type = "unresolved_fig_raw_similarity"
        risk_suggestion = "R1_max"
        evidence_strength = "candidate"
    else:
        candidate_type = candidate.get("candidate_type", "image_similarity_candidate")
        risk_suggestion = candidate.get("risk_suggestion", "R2_or_R3_pending_context")
        evidence_strength = candidate.get("evidence_strength", "candidate")

    evidence = dict(candidate.get("evidence", {}))
    evidence["context"] = context
    evidence["contextual_edges"] = risk_edges
    evidence["positive_traceability_edges"] = positive_edges
    if provenance_path:
        evidence["provenance_graph"] = provenance_path
    item = dict(candidate)
    item.update({
        "candidate_type": candidate_type,
        "locations": locations or candidate.get("locations", []),
        "evidence": evidence,
        "context": context,
        "evidence_strength": evidence_strength,
        "risk_suggestion": risk_suggestion,
        "risk_cap_tags": sorted(original_tags | tags),
    })
    if candidate_type == "unresolved_fig_raw_similarity":
        item["benign_explanations"] = [
            "figure panel may be a direct export or crop from the raw/source image",
            "source relationship may exist but was not supplied in a machine-readable manifest",
        ]
        item["required_materials"] = [
            "figure-source map",
            "assembly manifest",
            "raw image metadata",
        ]
        item["recommended_action"] = "Document the figure-to-raw/source relationship before treating the image similarity as a reuse concern."
    return item


def enrich_candidates(payload: dict[str, Any], package: Path, provenance_path: Path | None = None) -> dict[str, Any]:
    validate_instance(payload, DETECTOR_SCHEMA, "detector output before contextual join")
    context = package_context(package)
    provenance = load_provenance(provenance_path)
    declared_pairs = declared_traceability_pairs(provenance)
    enriched = []
    positive_evidence = []
    for candidate in payload.get("candidates", []):
        item = dict(candidate)
        if is_image_candidate(item):
            raw_edges = item.get("evidence", {}).get("edges", [])
            classified_edges = [
                classify_similarity_edge(edge, context, provenance, declared_pairs)
                for edge in raw_edges
            ]
            positive_edges = [edge for edge in classified_edges if edge.get("positive_evidence")]
            if positive_edges:
                positive_evidence.append({
                    "candidate_id": item.get("candidate_id", ""),
                    "candidate_type": "expected_traceability",
                    "edges": positive_edges,
                    "members": sorted({path for edge in positive_edges for path in edge_paths(edge) if path}),
                })
            reportable_edges = risk_edges_for_cluster(classified_edges)
            item = candidate_from_edges(
                item,
                reportable_edges,
                positive_edges,
                context,
                str(provenance_path) if provenance_path else None,
            )
            if item is None:
                continue
        enriched.append(item)

    result = {
        "detector_name": "contextual_joiner",
        "detector_version": "0.3.1",
        "input": {
            "source_detector": payload.get("detector_name", ""),
            "package": str(package),
            "provenance_graph": str(provenance_path) if provenance_path else None,
        },
        "candidates": enriched,
        "positive_evidence": positive_evidence,
        "errors": [],
    }
    validate_instance(result, DETECTOR_SCHEMA, "contextually enriched candidates")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--output", type=Path, default=Path("contextual_candidates.json"))
    args = parser.parse_args()

    payload = json.loads(args.input.expanduser().resolve().read_text(encoding="utf-8"))
    result = enrich_candidates(
        payload,
        args.package.expanduser().resolve(),
        args.provenance.expanduser().resolve() if args.provenance else None,
    )
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "candidates": len(result["candidates"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
