#!/usr/bin/env python3
"""Normalize figure-panel modality labels and derive deep-scan routing rules."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

CANONICAL_MODALITIES = (
    "microscopy",
    "western_blot",
    "chart",
    "schematic",
    "other",
)

MODALITY_ALIASES: dict[str, str] = {
    "blot": "western_blot",
    "gel": "western_blot",
    "western blot": "western_blot",
    "wb": "western_blot",
    "image": "other",
    "photo": "other",
    "table": "chart",
    "graph": "chart",
    "plot": "chart",
    "bar chart": "chart",
    "line chart": "chart",
    "diagram": "schematic",
    "flowchart": "schematic",
    "flow chart": "schematic",
    "icon": "schematic",
}

DEEP_SCAN_EXCLUDED_MODALITIES = {"schematic", "chart"}

DEEP_SCAN_EXCLUSION_REASON = (
    "local patch / same-image copy-move deep screening skipped for schematic and chart panels"
)

MODALITY_CONFLICT_REASON = (
    "Mixed experimental and schematic/chart modality declarations on authoritative manifest edges; "
    "local patch / same-image copy-move deep screening retained"
)

FIGURE_SOURCE_TRACEABILITY_RELATIONS = {
    "declared_derived_from",
    "declared_same_source",
    "same_membrane_reprobe",
}

FIGURE_FIGURE_TRACEABILITY_RELATIONS = {
    "same_field_different_channel",
    "same_membrane_reprobe",
}


def normalize_modality(raw: str | None) -> str:
    token = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in token:
        token = token.replace("__", "_")
    if not token:
        return "other"
    if token in CANONICAL_MODALITIES:
        return token
    compact = token.replace("_", " ")
    if compact in MODALITY_ALIASES:
        return MODALITY_ALIASES[compact]
    if token in MODALITY_ALIASES:
        return MODALITY_ALIASES[token]
    return "other"


def deep_scan_excluded_modality(modality: str) -> bool:
    return normalize_modality(modality) in DEEP_SCAN_EXCLUDED_MODALITIES


def role_from_path(path: str) -> str:
    if path.startswith("figures/"):
        return "figure_panel"
    if path.startswith("raw_images/"):
        return "raw_image"
    if path.startswith("source_data/"):
        return "source_data"
    return "resource"


def is_routing_eligible_edge(edge: dict[str, Any]) -> bool:
    """Only authoritative expected-traceability edges may control deep-scan routing."""
    if edge.get("risk_effect") != "expected_traceability":
        return False
    source_path = str(edge.get("source_path", "") or "")
    target_path = str(edge.get("target_path", "") or "")
    if not source_path or not target_path or source_path == target_path:
        return False
    source_role = role_from_path(source_path)
    target_role = role_from_path(target_path)
    roles = {source_role, target_role}
    relation = str(edge.get("relation_type", "") or "").lower()
    if roles == {"figure_panel", "raw_image"} or roles == {"figure_panel", "source_data"}:
        return relation in FIGURE_SOURCE_TRACEABILITY_RELATIONS
    if source_role == "figure_panel" and target_role == "figure_panel":
        return relation in FIGURE_FIGURE_TRACEABILITY_RELATIONS
    return False


@dataclass(frozen=True)
class PanelModalityRouting:
    excluded_panels: list[dict[str, str]]
    modality_conflicts: list[dict[str, Any]]


def resolve_panel_modality_routing(provenance: dict[str, Any]) -> PanelModalityRouting:
    """Resolve which figure panels may skip deep image screening."""
    grouped: dict[str, set[str]] = defaultdict(set)
    for edge in provenance.get("edges", []) or []:
        if not is_routing_eligible_edge(edge):
            continue
        source_path = str(edge.get("source_path", "") or "")
        if not source_path.startswith("figures/"):
            continue
        grouped[source_path].add(normalize_modality(str(edge.get("modality", "") or "")))

    excluded_panels: list[dict[str, str]] = []
    modality_conflicts: list[dict[str, Any]] = []
    for panel, modalities in grouped.items():
        if not modalities:
            continue
        experimental = modalities - DEEP_SCAN_EXCLUDED_MODALITIES
        excluded_types = modalities & DEEP_SCAN_EXCLUDED_MODALITIES
        if experimental and excluded_types:
            modality_conflicts.append({
                "panel": panel,
                "modalities": sorted(modalities),
                "reason": MODALITY_CONFLICT_REASON,
            })
            continue
        if modalities <= DEEP_SCAN_EXCLUDED_MODALITIES:
            primary = "schematic" if "schematic" in modalities else "chart"
            excluded_panels.append(excluded_panel_record(panel, primary))
    return PanelModalityRouting(
        excluded_panels=excluded_panels,
        modality_conflicts=modality_conflicts,
    )


def excluded_panel_record(panel: str, modality: str) -> dict[str, str]:
    return {
        "panel": panel,
        "modality": normalize_modality(modality),
        "reason": DEEP_SCAN_EXCLUSION_REASON,
    }
