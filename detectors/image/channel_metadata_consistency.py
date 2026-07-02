#!/usr/bin/env python3
"""Check same-field/different-channel declarations against image metadata intake.

This detector is intentionally conservative. It does not clear a declared
same-field relationship and does not decide authenticity. It only records when
the supplied package lacks machine-readable acquisition/channel metadata needed
to verify a same-field/different-channel explanation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DETECTOR_NAME = "image.channel_metadata_consistency"
DETECTOR_VERSION = "0.1.0"
RELATIONS_REQUIRING_METADATA = {"same_field_different_channel"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def is_image_path(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def metadata_indexes(payload: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    records = {
        str(item.get("path", "")): item
        for item in payload.get("images", []) or []
        if isinstance(item, dict) and item.get("path")
    }
    errors = {
        str(item.get("path", "")): item
        for item in payload.get("errors", []) or []
        if isinstance(item, dict) and item.get("path")
    }
    return records, errors


def channel_support(record: dict[str, Any] | None) -> str:
    if not record:
        return ""
    channel_count = record.get("channel_count")
    has_ome = bool(record.get("has_ome_xml"))
    try:
        channel_count_int = int(channel_count) if channel_count is not None else 0
    except (TypeError, ValueError):
        channel_count_int = 0
    if has_ome and channel_count_int > 1:
        return "ome_multichannel_metadata"
    if channel_count_int > 1:
        return "multichannel_metadata"
    if has_ome:
        return "ome_single_channel_or_export_metadata"
    return ""


def compact_record(record: dict[str, Any] | None, error: dict[str, Any] | None) -> dict[str, Any]:
    if record:
        return {
            "path": str(record.get("path", "")),
            "metadata_status": str(record.get("metadata_status", "")),
            "format": str(record.get("format", "")),
            "mode": str(record.get("mode", "")),
            "n_frames": record.get("n_frames"),
            "channel_count": record.get("channel_count"),
            "z_stack_count": record.get("z_stack_count"),
            "timepoint_count": record.get("timepoint_count"),
            "has_ome_xml": bool(record.get("has_ome_xml")),
            "support_status": channel_support(record),
            "manual_review_note": str(record.get("manual_review_note", "")),
        }
    if error:
        return {
            "path": str(error.get("path", "")),
            "metadata_status": "metadata_unreadable",
            "error": str(error.get("error", "")),
            "support_status": "",
        }
    return {
        "metadata_status": "metadata_not_found",
        "support_status": "",
    }


def relation_records(
    edge: dict[str, Any],
    records: dict[str, dict[str, Any]],
    errors: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_path = str(edge.get("source_path", ""))
    target_path = str(edge.get("target_path", ""))
    return (
        compact_record(records.get(source_path), errors.get(source_path)),
        compact_record(records.get(target_path), errors.get(target_path)),
    )


def has_verifiable_channel_context(source_meta: dict[str, Any], target_meta: dict[str, Any]) -> bool:
    return any(
        item.get("support_status") in {"ome_multichannel_metadata", "multichannel_metadata"}
        for item in (source_meta, target_meta)
    )


def candidate_for_gap(edge: dict[str, Any], source_meta: dict[str, Any], target_meta: dict[str, Any], index: int) -> dict[str, Any]:
    source_path = str(edge.get("source_path", ""))
    target_path = str(edge.get("target_path", ""))
    evidence_source = str(edge.get("evidence_source", ""))
    return {
        "candidate_id": f"IMG-CHANNEL-META-{index:04d}",
        "detector": DETECTOR_NAME,
        "candidate_type": "channel_metadata_verification_gap",
        "locations": [value for value in (source_path, target_path) if value],
        "evidence": {
            "relation_type": str(edge.get("relation_type", "")),
            "risk_effect": str(edge.get("risk_effect", "")),
            "evidence_source": evidence_source,
            "source_path": source_path,
            "target_path": target_path,
            "source_metadata": source_meta,
            "target_metadata": target_meta,
            "metadata_support": "insufficient_machine_readable_channel_metadata",
            "declared_relation_unverified": True,
            "interpretation": (
                "A same-field/different-channel declaration was supplied, but the package did not "
                "include machine-readable multichannel acquisition metadata for this declared relation."
            ),
        },
        "evidence_strength": "weak_signal",
        "risk_suggestion": "R1",
        "risk_cap_tags": [
            "channel_metadata_verification_gap",
            "completeness_gap",
        ],
        "benign_explanations": [
            "The panels may be legitimate single-channel exports from a multichannel acquisition whose raw metadata was not supplied.",
            "The channel map may be documented in an acquisition log, microscope export, OME-TIFF, or lab notebook not included in the package.",
        ],
        "required_materials": [
            "original multichannel acquisition file or OME-TIFF with channel metadata",
            "channel map or acquisition metadata linking the declared panels to the same field",
            "figure assembly record showing how each channel export was generated",
        ],
        "recommended_action": (
            "Provide acquisition/channel metadata for the declared same-field/different-channel relation, "
            "or revise the manifest/legend if the relation was entered incorrectly."
        ),
        "requires_contextual_calibration": True,
    }


def build_payload(package: Path, provenance: Path, metadata: Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    try:
        graph = read_json(provenance)
    except Exception as exc:  # noqa: BLE001 - surfaced as detector error.
        graph = {"edges": []}
        errors.append({"path": str(provenance), "error": f"{type(exc).__name__}: {exc}"})
    try:
        metadata_payload = read_json(metadata)
    except Exception as exc:  # noqa: BLE001 - surfaced as detector error.
        metadata_payload = {"images": [], "errors": []}
        errors.append({"path": str(metadata), "error": f"{type(exc).__name__}: {exc}"})

    records, metadata_errors = metadata_indexes(metadata_payload)
    candidates: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    supported = 0

    for edge in graph.get("edges", []) or []:
        if not isinstance(edge, dict):
            continue
        relation = str(edge.get("relation_type", "")).lower()
        if relation not in RELATIONS_REQUIRING_METADATA:
            continue
        if str(edge.get("risk_effect", "")) != "expected_traceability":
            continue
        source_path = str(edge.get("source_path", ""))
        target_path = str(edge.get("target_path", ""))
        if not (is_image_path(source_path) or is_image_path(target_path)):
            continue

        source_meta, target_meta = relation_records(edge, records, metadata_errors)
        support = has_verifiable_channel_context(source_meta, target_meta)
        if support:
            supported += 1
        checked.append({
            "source_path": source_path,
            "target_path": target_path,
            "relation_type": relation,
            "evidence_source": str(edge.get("evidence_source", "")),
            "metadata_support": (
                "machine_readable_multichannel_context_present"
                if support
                else "insufficient_machine_readable_channel_metadata"
            ),
            "source_metadata_status": source_meta.get("metadata_status"),
            "target_metadata_status": target_meta.get("metadata_status"),
        })
        if not support:
            candidates.append(candidate_for_gap(edge, source_meta, target_meta, len(candidates) + 1))

    return {
        "detector_name": DETECTOR_NAME,
        "detector_version": DETECTOR_VERSION,
        "input": {
            "package": str(package),
            "provenance_graph": str(provenance),
            "image_metadata": str(metadata),
            "relations_checked": sorted(RELATIONS_REQUIRING_METADATA),
        },
        "declarations_checked": len(checked),
        "supported_declarations": supported,
        "verification_gaps": len(candidates),
        "checked_relations": checked,
        "scope_note": (
            "This detector checks whether declared same-field/different-channel relationships have "
            "machine-readable multichannel metadata support. It does not clear image similarity candidates."
        ),
        "candidates": candidates,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("channel_metadata_candidates.json"))
    args = parser.parse_args()

    package = args.package.expanduser().resolve()
    output = args.output.expanduser().resolve()
    payload = build_payload(
        package,
        args.provenance.expanduser().resolve(),
        args.metadata.expanduser().resolve(),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "declarations_checked": payload["declarations_checked"],
        "verification_gaps": payload["verification_gaps"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
