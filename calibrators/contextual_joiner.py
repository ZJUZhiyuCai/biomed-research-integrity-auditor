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
SOURCE_EXTS = {".csv", ".tsv", ".xlsx"}
RAW_IMAGE_EXTS = {".czi", ".nd2", ".lif", ".oib", ".oir", ".svs", ".vsi", ".tif", ".tiff", ".png", ".jpg", ".jpeg"}
FIGURE_SOURCE_TRACEABILITY_RELATIONS = {
    "declared_derived_from",
    "declared_same_source",
    "same_membrane_reprobe",
}
FIGURE_FIGURE_TRACEABILITY_RELATIONS = {
    "same_field_different_channel",
    "same_membrane_reprobe",
}
PASSTHROUGH_CANDIDATE_TYPES = {
    "audit_coverage_gap",
    "detector_execution_failure",
}
REUSE_DISCLOSURE_PATTERNS = [
    r"\bdisclos\w*\b.{0,80}\breus\w*\b",
    r"\breus\w*\b.{0,80}\bdisclos\w*\b",
    r"\bintentionally reused\b",
    r"\bsame loading control\b",
    r"\bsame gapdh loading control\b",
    r"\bloading control was reused\b",
    r"\bsame membrane\b",
    r"\breprobed\b",
]


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
    reuse_disclosed = contains_any(text, REUSE_DISCLOSURE_PATTERNS)
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
        "package_text": text,
        "reuse_disclosed": reuse_disclosed,
        "loading_control_disclosed": loading_control_disclosed,
        "same_experiment_claimed": same_experiment_claimed,
        "same_membrane_claimed": same_membrane_claimed,
        "source_data_available": source_available,
        "raw_images_available": raw_available,
        "risk_cap_tags": risk_cap_tags,
    }


def path_aliases(path: str) -> set[str]:
    stem = Path(path).stem.lower()
    normalized = stem.replace("_", " ").replace("-", " ")
    aliases = {path.lower(), stem, normalized}
    match = re.search(r"(?:figure|fig)[ _-]*(\d+[a-z]?)", stem, flags=re.I)
    if match:
        panel = match.group(1).lower()
        aliases.update({f"figure {panel}", f"fig {panel}", panel})
    return {alias for alias in aliases if alias}


def text_mentions_path(text: str, path: str) -> bool:
    return any(alias in text for alias in path_aliases(path))


def disclosure_window(text: str, left: str, right: str, radius: int = 500) -> str:
    left_positions = [
        match.start()
        for alias in path_aliases(left)
        for match in re.finditer(re.escape(alias), text)
    ]
    right_positions = [
        match.start()
        for alias in path_aliases(right)
        for match in re.finditer(re.escape(alias), text)
    ]
    if left == right:
        right_positions = left_positions
    for left_pos in left_positions:
        for right_pos in right_positions:
            if abs(left_pos - right_pos) > radius:
                continue
            first = min(left_pos, right_pos)
            last = max(left_pos, right_pos)
            segment_start = text.rfind("\n--- ", 0, first)
            next_segment_start = text.find("\n--- ", first + 1)
            if next_segment_start != -1 and last >= next_segment_start:
                continue
            start_bound = segment_start if segment_start != -1 else 0
            end_bound = next_segment_start if next_segment_start != -1 else len(text)
            start = max(start_bound, first - radius)
            end = min(end_bound, last + radius)
            window = text[start:end]
            if contains_any(window, REUSE_DISCLOSURE_PATTERNS):
                return window
    return ""


def edge_disclosure_tags(edge: dict[str, Any], context: dict[str, Any]) -> list[str]:
    text = str(context.get("package_text", ""))
    left, right = edge_paths(edge)
    if not left or not right:
        return []
    window = disclosure_window(text, left, right)
    if not window:
        return []
    loading_control = "loading control" in window and contains_any(window, [r"\breus\w*\b", r"\bsame\b"])
    same_membrane = contains_any(window, [r"\bsame membrane\b", r"\bshared membrane\b", r"\bmembrane was reprobed\b", r"\breprobed\b"])
    if (
        (loading_control or same_membrane)
        and (context.get("source_data_available") or context.get("raw_images_available"))
    ):
        return ["disclosed_legitimate_reuse"]
    return ["disclosed_unjustified_reuse"]


def is_image_candidate(candidate: dict[str, Any]) -> bool:
    if str(candidate.get("candidate_type", "")) in PASSTHROUGH_CANDIDATE_TYPES:
        return False
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


def is_authoritative_traceability_edge(edge: dict[str, Any], provenance: dict[str, Any]) -> bool:
    if edge.get("risk_effect") != "expected_traceability":
        return False
    source_path = str(edge.get("source_path", ""))
    target_path = str(edge.get("target_path", ""))
    if not source_path or not target_path or source_path == target_path:
        return False
    source_role = role_from_path(source_path, provenance)
    target_role = role_from_path(target_path, provenance)
    roles = {source_role, target_role}
    relation = str(edge.get("relation_type", "")).lower()
    if roles == {"figure_panel", "raw_image"} or roles == {"figure_panel", "source_data"}:
        return relation in FIGURE_SOURCE_TRACEABILITY_RELATIONS
    if source_role == "figure_panel" and target_role == "figure_panel":
        return relation in FIGURE_FIGURE_TRACEABILITY_RELATIONS
    return False


def declared_traceability_pairs(provenance: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    pairs = {}
    for edge in provenance.get("edges", []) or []:
        if is_authoritative_traceability_edge(edge, provenance):
            pairs[undirected_pair(str(edge.get("source_path", "")), str(edge.get("target_path", "")))] = edge
    return pairs


def provenance_edge_for_pair(left: str, right: str, provenance: dict[str, Any]) -> dict[str, Any] | None:
    pair = undirected_pair(left, right)
    for edge in provenance.get("edges", []) or []:
        if undirected_pair(str(edge.get("source_path", "")), str(edge.get("target_path", ""))) == pair:
            return edge
    return None


def edge_paths(edge: dict[str, Any]) -> tuple[str, str]:
    return str(edge.get("left", "")), str(edge.get("right", ""))


def is_same_image_copy_move_edge(edge: dict[str, Any]) -> bool:
    left, right = edge_paths(edge)
    return bool(left and left == right) and (
        edge.get("same_image") is True
        or edge.get("similarity_scope") == "same_image_copy_move"
    )


def classify_similarity_edge(
    edge: dict[str, Any],
    context: dict[str, Any],
    provenance: dict[str, Any],
    declared_pairs: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    left, right = edge_paths(edge)
    left_role = role_from_path(left, provenance)
    right_role = role_from_path(right, provenance)
    classified = dict(edge)
    classified["left_role"] = left_role
    classified["right_role"] = right_role
    is_local_patch = edge.get("similarity_scope") == "local_patch"

    if is_same_image_copy_move_edge(edge):
        classified.update({
            "contextual_tag": "same_image_copy_move",
            "reportable_as_risk": True,
            "positive_evidence": False,
            "risk_suggestion": "R3_possible",
            "required_materials_to_resolve": [
                "original image file",
                "raw acquisition metadata",
                "image-processing or figure-assembly history",
            ],
        })
        return classified

    pair = undirected_pair(left, right)
    provenance_edge = provenance_edge_for_pair(left, right, provenance)
    if pair in declared_pairs:
        declared_edge = declared_pairs[pair]
        figure_figure_declared = left_role == "figure_panel" and right_role == "figure_panel"
        # A declared same-field/same-membrane relationship between two presented
        # panels is plausible for a shared local region, but it cannot be verified
        # from the manifest alone. A whole-image near-duplicate (global scope, not a
        # local patch) contradicts a "different channel" or "reprobed membrane"
        # claim, so an unverifiable manifest line must not silently clear it. Keep it
        # as a manifest_conflict that still requires raw-record review.
        if figure_figure_declared:
            if is_local_patch:
                classified.update({
                    "contextual_tag": "declared_local_patch_requires_verification",
                    "reportable_as_risk": True,
                    "positive_evidence": False,
                    "risk_suggestion": "R1_max",
                    "declared_relation_unverified": True,
                    "provenance_edge": declared_edge,
                    "required_materials_to_resolve": [
                        "raw image files for both declared panels",
                        "per-channel, same-field, lane, or reprobe acquisition metadata",
                        "figure assembly history demonstrating the declared relationship",
                    ],
                })
                return classified
            classified.update({
                "contextual_tag": "manifest_conflict",
                "reportable_as_risk": True,
                "positive_evidence": False,
                "risk_suggestion": "R3_possible",
                "declared_relation_unverified": True,
                "provenance_edge": declared_edge,
                "required_materials_to_resolve": [
                    "raw image files for both declared panels",
                    "per-channel or per-reprobe acquisition metadata",
                    "figure assembly history demonstrating the declared relationship",
                ],
            })
            return classified
        classified.update({
            "contextual_tag": "expected_traceability",
            "reportable_as_risk": False,
            "positive_evidence": True,
            "risk_suggestion": "R0_positive_traceability",
            "provenance_edge": declared_edge,
        })
        return classified
    if provenance_edge:
        classified["provenance_edge"] = provenance_edge
        classified["declared_relation_unverified"] = True

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
        disclosure_tags = edge_disclosure_tags(edge, context)
        if "disclosed_legitimate_reuse" in disclosure_tags:
            tag = "disclosed_legitimate_reuse"
            suggestion = "R2_max"
        elif "disclosed_unjustified_reuse" in disclosure_tags:
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
        "declared_local_patch_requires_verification",
        "manifest_conflict",
        "same_image_copy_move",
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

    if "declared_local_patch_requires_verification" in tags:
        candidate_type = "local_patch_reuse"
        risk_suggestion = "R1_max"
        evidence_strength = "candidate"
    elif "local_patch_cross_context" in tags:
        candidate_type = "local_patch_reuse"
        risk_suggestion = "R3_possible"
        evidence_strength = "candidate"
    elif "same_image_copy_move" in tags:
        candidate_type = "same_image_copy_move"
        risk_suggestion = "R3_possible"
        evidence_strength = "candidate"
    elif "manifest_conflict" in tags:
        candidate_type = "image_reuse_cluster"
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

    public_context = {
        key: value
        for key, value in context.items()
        if key not in {"package_text", "risk_cap_tags"}
    }
    evidence = dict(candidate.get("evidence", {}))
    evidence["context"] = public_context
    evidence["contextual_edges"] = risk_edges
    evidence["positive_traceability_edges"] = positive_edges
    if provenance_path:
        evidence["provenance_graph"] = provenance_path
    item = dict(candidate)
    item.update({
        "candidate_type": candidate_type,
        "locations": locations or candidate.get("locations", []),
        "evidence": evidence,
        "context": public_context,
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
    if "declared_local_patch_requires_verification" in tags:
        item["benign_explanations"] = [
            "the panels may genuinely share a field, lane, membrane, channel set, or reprobe history",
            "the manifest declaration is useful context, but it is not independent verification without raw/source records",
        ]
        item["required_materials"] = [
            "raw image files for both declared panels",
            "per-channel, same-field, lane, or reprobe acquisition metadata",
            "figure assembly history demonstrating the declared relationship",
        ]
        item["recommended_action"] = (
            "Verify the declared same-field/same-membrane relationship against raw images, acquisition metadata, "
            "and figure assembly history before treating this local similarity as resolved."
        )
    if "manifest_conflict" in tags:
        item["benign_explanations"] = [
            "the panels may genuinely share a field or membrane, but the manifest claim cannot be verified from supplied materials",
            "whole-image similarity could come from an export or figure-assembly error rather than reuse",
        ]
        item["required_materials"] = [
            "raw image files for both declared panels",
            "per-channel or per-reprobe acquisition metadata",
            "figure assembly history demonstrating the declared relationship",
        ]
        item["recommended_action"] = (
            "Verify the declared same-field/same-membrane relationship against raw images and acquisition metadata; "
            "a manifest declaration alone does not resolve a whole-image duplication candidate."
        )
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
        "detector_version": "0.3.2",
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
