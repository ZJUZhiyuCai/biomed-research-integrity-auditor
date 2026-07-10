#!/usr/bin/env python3
"""Build submission-QC artifacts from an audit run.

These helpers deliberately produce traceability and readiness artifacts, not
misconduct determinations. They are used by scripts/audit_package.py and can
also be imported by tests or a web UI export endpoint.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import html
import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

import yaml

try:
    from scripts.csv_safety import csv_safe_cell, csv_safe_row
except ImportError:  # pragma: no cover - supports direct script execution.
    from csv_safety import csv_safe_cell, csv_safe_row


ACTION_FIELDNAMES = [
    "action_id",
    "action_category",
    "risk_level",
    "action_type",
    "source_finding_id",
    "location",
    "required_action",
    "owner",
    "status",
    "human_note",
    "accepted_with_reason",
    "attachment_reference",
    "neutral_inquiry_template",
    "material_request_template",
    "source",
]

CORRECTION_PLAN_FIELDNAMES = [
    "finding_id",
    "risk",
    "required_correction",
    "owner",
    "evidence_after_correction",
    "attachment_reference",
    "status",
    "source_action_id",
]


CLAIM_MANIFEST_CANDIDATES = (
    "claim_manifest.csv",
    "submission_readiness/claim_manifest.csv",
)
CLAIM_COLUMNS = [
    "claim_id",
    "claim_text",
    "manuscript_location",
    "figure_or_table",
    "source_data",
    "raw_record",
    "analysis_code",
    "protocol",
    "owner",
    "status",
]
CLAIM_PATH_FIELDS = {
    "source_data": "source data",
    "raw_record": "raw record",
    "analysis_code": "analysis code",
    "protocol": "protocol",
}
READY_STATUSES = {"ready", "complete", "resolved"}
EMPTY_TOKENS = {"", "na", "n/a", "none", "not_applicable", "not applicable", "-"}
RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}
IMAGE_REVIEW_FINDING_TYPES = {
    "image_reuse_cluster",
    "keypoint_geometric_match",
    "local_patch_reuse",
    "same_image_copy_move",
    "splice_forensics_triage_signal",
    "unresolved_fig_raw_similarity",
    "channel_metadata_verification_gap",
}
IMAGE_REVIEW_ARTIFACTS = (
    "global_image_candidates.json",
    "contextual_image_candidates.json",
    "keypoint_image_candidates.json",
    "keypoint_contextual_candidates.json",
    "channel_metadata_candidates.json",
    "splice_forensics_candidates.json",
    "local_patch_candidates.json",
    "local_patch_contextual_candidates.json",
)
IMAGE_FILE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
IMAGE_REVIEW_CSV_FIELDS = [
    "finding_id",
    "risk_level",
    "finding_type",
    "location",
    "left",
    "right",
    "similarity_scope",
    "best_transform",
    "score_or_ratio",
    "key_metric",
    "evidence_files",
    "recommended_action",
]
IMAGE_FILE_CSV_FIELDS = [
    "path",
    "role",
    "sha256",
    "size_bytes",
    "candidate_referenced",
]
IMAGE_REVIEW_TRACKER_FIELDS = [
    "review_item_id",
    "source_finding_id",
    "finding_type",
    "risk_level",
    "location",
    "candidate_files",
    "recommended_external_review",
    "review_owner",
    "review_status",
    "external_tool_or_method",
    "review_result_note",
    "attachment_reference",
]
IMAGE_TOOL_HANDOFF_FIELDS = [
    "handoff_item_id",
    "source_finding_id",
    "priority",
    "finding_type",
    "risk_level",
    "candidate_files",
    "evidence_files",
    "recommended_tool_route",
    "review_question",
    "supporting_context",
    "data_governance_note",
    "review_status",
    "reviewer",
    "external_result_reference",
]
AUDIENCE_EXPORT_FILES = {
    "pi_brief": "PI_BRIEF.md",
    "coauthor_actions": "COAUTHOR_ACTIONS.md",
    "journal_response_draft": "JOURNAL_RESPONSE_DRAFT.md",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def pyproject_version(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return "unknown"
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), flags=re.M)
    return match.group(1) if match else "unknown"


def package_root_hash(files: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for item in sorted(files, key=lambda row: str(row.get("path", ""))):
        h.update(str(item.get("path", "")).encode("utf-8"))
        h.update(b"\0")
        h.update(str(item.get("sha256", "")).encode("utf-8"))
        h.update(b"\0")
        h.update(str(item.get("size_bytes", "")).encode("utf-8"))
        h.update(b"\0")
        h.update(str(item.get("category", "")).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def build_audit_snapshot(
    manifest: dict[str, Any],
    audit_id: str,
    tool_version: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    files = [
        {
            "path": item.get("path", ""),
            "role": item.get("category", "other"),
            "sha256": item.get("sha256", ""),
            "size_bytes": item.get("size_bytes", 0),
            "extension": item.get("extension", ""),
        }
        for item in manifest.get("files", [])
        if item.get("path")
    ]
    root_hash = package_root_hash(manifest.get("files", []))
    return {
        "schema_version": "0.1.0",
        "audit_id": audit_id,
        "created_at": created_at or utc_now(),
        "tool_version": tool_version,
        "package_root": manifest.get("root", ""),
        "package_root_hash": root_hash,
        "file_count": len(files),
        "files": files,
        "scope_note": (
            "This snapshot records the supplied files and hashes at audit time. "
            "It is a version-control artifact, not a correctness verdict."
        ),
    }


def build_file_hash_manifest(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "audit_id": snapshot.get("audit_id"),
        "created_at": snapshot.get("created_at"),
        "package_root": snapshot.get("package_root"),
        "package_root_hash": snapshot.get("package_root_hash"),
        "files": [
            {
                "path": item.get("path"),
                "sha256": item.get("sha256"),
                "size_bytes": item.get("size_bytes"),
                "role": item.get("role"),
            }
            for item in snapshot.get("files", [])
        ],
    }


def find_claim_manifest(package: Path, explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if not candidate.is_file():
            raise FileNotFoundError(f"claim manifest not found: {candidate}")
        return candidate
    for rel in CLAIM_MANIFEST_CANDIDATES:
        candidate = package / rel
        if candidate.is_file():
            return candidate
    return None


def split_refs(value: str) -> list[str]:
    refs = []
    for item in str(value or "").replace("|", ";").split(";"):
        item = item.strip()
        if item.lower() in EMPTY_TOKENS:
            continue
        refs.append(item)
    return refs


def path_status(package: Path, value: str) -> tuple[str, list[str]]:
    refs = split_refs(value)
    if not refs:
        return "missing", []
    missing = [ref for ref in refs if not (package / ref).exists()]
    if missing:
        return "unresolved", missing
    return "linked", []


def relative_to_package(package: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(package.resolve()).as_posix()
    except ValueError:
        return str(path)


def empty_claim_coverage(package: Path, manifest_path: Path | None, warning: str) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "claim_manifest": relative_to_package(package, manifest_path),
        "supplied": False,
        "claims_declared": 0,
        "claims_with_source_data": 0,
        "claims_with_raw_records": 0,
        "claims_with_analysis_code": 0,
        "claims_with_protocol_link": 0,
        "claims_with_unresolved_evidence_gap": 0,
        "unresolved_claims": [],
        "warnings": [warning],
        "scope_note": (
            "Claim coverage is a claim-to-evidence completeness check. "
            "It does not determine whether claims are true."
        ),
    }


def build_claim_coverage(package: Path, manifest_path: Path | None) -> dict[str, Any]:
    if manifest_path is None:
        return empty_claim_coverage(package, None, "No claim_manifest.csv was supplied.")

    with manifest_path.open(newline="", encoding="utf-8", errors="ignore") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = set(reader.fieldnames or [])

    warnings: list[str] = []
    missing_columns = [col for col in ("claim_id", "claim_text") if col not in fieldnames]
    if missing_columns:
        warnings.append(f"claim manifest missing required columns: {', '.join(missing_columns)}")

    unresolved_claims = []
    field_counts = {field: 0 for field in CLAIM_PATH_FIELDS}
    for idx, row in enumerate(rows, start=1):
        claim_id = str(row.get("claim_id") or f"CLAIM-{idx:04d}")
        path_field_status: dict[str, str] = {}
        missing_paths: list[str] = []
        gap_reasons: list[str] = []

        for field, label in CLAIM_PATH_FIELDS.items():
            status, missing = path_status(package, str(row.get(field, "") or ""))
            path_field_status[field] = status
            missing_paths.extend(missing)
            if status == "linked":
                field_counts[field] += 1
            elif status == "missing":
                gap_reasons.append(f"missing {label} link")
            else:
                gap_reasons.append(f"{label} path not found")

        status = str(row.get("status") or "").strip().lower()
        if status and status not in READY_STATUSES:
            gap_reasons.append(f"claim status is {status}")

        if gap_reasons or missing_columns:
            unresolved_claims.append({
                "claim_id": claim_id,
                "claim_text": str(row.get("claim_text") or ""),
                "manuscript_location": str(row.get("manuscript_location") or ""),
                "figure_or_table": str(row.get("figure_or_table") or ""),
                "owner": str(row.get("owner") or ""),
                "status": str(row.get("status") or ""),
                "field_status": path_field_status,
                "gap_reasons": sorted(set(gap_reasons + missing_columns)),
                "missing_paths": sorted(set(missing_paths)),
            })

    return {
        "schema_version": "0.1.0",
        "claim_manifest": relative_to_package(package, manifest_path),
        "supplied": True,
        "claims_declared": len(rows),
        "claims_with_source_data": field_counts["source_data"],
        "claims_with_raw_records": field_counts["raw_record"],
        "claims_with_analysis_code": field_counts["analysis_code"],
        "claims_with_protocol_link": field_counts["protocol"],
        "claims_with_unresolved_evidence_gap": len(unresolved_claims),
        "unresolved_claims": unresolved_claims,
        "warnings": warnings,
        "scope_note": (
            "Claim coverage is a claim-to-evidence completeness check. "
            "It does not determine whether claims are true."
        ),
    }


def write_claim_coverage_csv(path: Path, coverage: dict[str, Any]) -> None:
    fieldnames = [
        "claim_id",
        "status",
        "manuscript_location",
        "figure_or_table",
        "source_data_status",
        "raw_record_status",
        "analysis_code_status",
        "protocol_status",
        "gap_reasons",
        "missing_paths",
    ]
    rows = []
    for item in coverage.get("unresolved_claims", []) or []:
        field_status = item.get("field_status", {}) or {}
        rows.append({
            "claim_id": item.get("claim_id", ""),
            "status": item.get("status", ""),
            "manuscript_location": item.get("manuscript_location", ""),
            "figure_or_table": item.get("figure_or_table", ""),
            "source_data_status": field_status.get("source_data", ""),
            "raw_record_status": field_status.get("raw_record", ""),
            "analysis_code_status": field_status.get("analysis_code", ""),
            "protocol_status": field_status.get("protocol", ""),
            "gap_reasons": "; ".join(item.get("gap_reasons", []) or []),
            "missing_paths": "; ".join(item.get("missing_paths", []) or []),
        })
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_safe_row(row, fieldnames) for row in rows)


def write_missing_materials_csv(path: Path, manifest: dict[str, Any]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["category", "risk_level", "reason"])
        writer.writeheader()
        for item in manifest.get("missing_materials", []) or []:
            writer.writerow({
                "category": csv_safe_cell(item.get("category", "")),
                "risk_level": csv_safe_cell(item.get("risk_level", "R1")),
                "reason": csv_safe_cell(item.get("reason", "")),
            })


def write_verified_traceability_csv(path: Path, audit_summary: dict[str, Any]) -> None:
    fieldnames = ["provenance_id", "relation_type", "figure_panel", "source_record", "evidence_source", "risk_effect"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in audit_summary.get("positive_provenance", []) or []:
            writer.writerow(csv_safe_row(item, fieldnames))


def unresolved_action_rows(
    manifest: dict[str, Any],
    audit_summary: dict[str, Any],
    claim_coverage: dict[str, Any],
) -> list[dict[str, str]]:
    action_queue = audit_summary.get("action_queue") or {}
    categories = action_queue.get("categories") or {}
    if categories:
        rows = []
        for category_rows in categories.values():
            for row in category_rows or []:
                rows.append({key: str(row.get(key, "")) for key in ACTION_FIELDNAMES})
        return rows

    rows: list[dict[str, str]] = []

    def owner_for(action_type: str, location: str, action: str) -> str:
        text = " ".join([action_type, location, action]).lower()
        if any(token in text for token in ("stat", "p-value", "sem", "sd", "mean", "n consistency")):
            return "statistician"
        if any(token in text for token in ("image", "figure", "raw", "blot", "gel", "microscopy", "traceability")):
            return "figure_preparer"
        if any(token in text for token in ("source", "data", "claim", "manifest")):
            return "data_owner"
        if any(token in text for token in ("ethics", "irb", "consent", "registry", "protocol")):
            return "corresponding_author"
        return "first_author"

    def category_for(action_type: str, risk_level: str, location: str, action: str) -> str:
        text = " ".join([action_type, location, action]).lower()
        if risk_level in {"R3", "R4"}:
            return "must_resolve"
        if any(token in text for token in ("missing", "source", "raw", "traceability", "coverage", "provide", "upload")):
            return "provide_materials"
        if risk_level == "R2" or any(token in text for token in ("clarify", "disclose", "explain")):
            return "clarify_or_disclose"
        return "low_priority_checks"

    def neutral_templates(action_type: str, location: str, action: str) -> tuple[str, str]:
        location_label = location or "the listed item"
        action_text = action or "resolve or document this item"
        text = " ".join([action_type, location, action]).lower()
        if any(token in text for token in ("image", "figure", "raw", "blot", "gel", "microscopy", "traceability")):
            inquiry = (
                f"Could the figure/data owner clarify the source and assembly history for `{location_label}`, "
                "including whether the observation is expected from the supplied raw/source records? "
                f"中文：请图像/数据负责人说明 `{location_label}` 的来源和组图记录，并确认该观察是否可由已提供的 raw/source records 解释。"
            )
            request = (
                f"Please add or link the raw/source image records, assembly notes, and acquisition context needed for `{location_label}`: {action_text}. "
                f"中文：请补充或链接 `{location_label}` 所需的原始/来源图像、组图说明和采集背景：{action_text}。"
            )
        elif any(token in text for token in ("stat", "p-value", "sem", "sd", "mean", "n consistency", "data")):
            inquiry = (
                f"Could the data/statistics owner verify how `{location_label}` was derived, including n, experimental unit, rounding, exclusions, and transformations? "
                f"中文：请数据/统计负责人核对 `{location_label}` 的来源，包括 n、实验单位、舍入、排除项和转换。"
            )
            request = (
                f"Please add or link the source table, analysis code, and calculation notes needed for `{location_label}`: {action_text}. "
                f"中文：请补充或链接 `{location_label}` 所需的 source table、分析代码和计算说明：{action_text}。"
            )
        elif any(token in text for token in ("claim", "manifest", "coverage", "missing", "unsupported")):
            inquiry = (
                f"Could the responsible owner confirm whether the materials or corrected manifest information for `{location_label}` can be supplied? "
                f"中文：请责任人确认 `{location_label}` 所需材料或修正后的 manifest 信息是否可以提供。"
            )
            request = (
                f"Please add the missing or corrected materials needed for `{location_label}`: {action_text}. "
                f"中文：请补充 `{location_label}` 所需的缺失材料或修正文件：{action_text}。"
            )
        else:
            inquiry = (
                f"Could the responsible owner review `{location_label}` and clarify the source records or context needed to interpret this item? "
                f"中文：请责任人复核 `{location_label}`，并说明解释该项目所需的 source records 或背景。"
            )
            request = (
                f"Please add or link the materials needed to resolve `{location_label}`: {action_text}. "
                f"中文：请补充或链接用于解决 `{location_label}` 的材料：{action_text}。"
            )
        inquiry += (
            " This is a documentation request, not a conclusion about intent or responsibility. "
            "中文：这是资料核对请求，不是对意图或责任的结论。"
        )
        return inquiry, request

    def append(
        action_type: str,
        risk_level: str,
        location: str,
        action: str,
        source: str,
        source_finding_id: str = "",
    ) -> None:
        category = category_for(action_type, risk_level, location, action)
        inquiry, request = neutral_templates(action_type, location, action)
        rows.append({
            "action_id": f"ACT-{len(rows) + 1:04d}",
            "action_category": category,
            "risk_level": risk_level,
            "action_type": action_type,
            "source_finding_id": source_finding_id,
            "location": location,
            "required_action": action,
            "owner": owner_for(action_type, location, action),
            "status": "unresolved",
            "human_note": "",
            "accepted_with_reason": "",
            "attachment_reference": "",
            "neutral_inquiry_template": inquiry,
            "material_request_template": request,
            "source": source,
        })

    for item in manifest.get("missing_materials", []) or []:
        append(
            "missing_material",
            item.get("risk_level", "R1"),
            item.get("category", ""),
            item.get("reason", "Add or explain missing materials."),
            "manifest",
        )
    for item in audit_summary.get("traceability_gaps", []) or []:
        append(
            "traceability_gap",
            item.get("risk_level", "R1"),
            item.get("location", ""),
            "; ".join(item.get("required_materials_to_resolve", []) or ["Provide source/raw records."]),
            "AUDIT_JSON_SUMMARY.traceability_gaps",
        )
    for item in audit_summary.get("findings", []) or []:
        append(
            item.get("finding_type", "finding"),
            item.get("risk_level", "R1"),
            item.get("location", ""),
            item.get("recommended_action", "Resolve or document this finding."),
            "AUDIT_JSON_SUMMARY.findings",
            str(item.get("finding_id", "")),
        )
    if not claim_coverage.get("supplied"):
        append(
            "claim_manifest_missing",
            "R1",
            "claim_manifest.csv",
            "Add a claim_manifest.csv before using this as a complete submission QC packet.",
            "claim_coverage",
        )
    for item in claim_coverage.get("unresolved_claims", []) or []:
        append(
            "claim_evidence_gap",
            "R1",
            item.get("manuscript_location") or item.get("figure_or_table") or item.get("claim_id", ""),
            "; ".join(item.get("gap_reasons", []) or ["Resolve claim-to-evidence gap."]),
            "claim_coverage",
        )
    return rows


def write_unresolved_actions_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ACTION_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_safe_row(row, ACTION_FIELDNAMES))


def correction_plan_rows(action_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for action in action_rows:
        rows.append({
            "finding_id": action.get("action_id", ""),
            "risk": action.get("risk_level", ""),
            "required_correction": action.get("required_action", ""),
            "owner": action.get("owner", ""),
            "evidence_after_correction": action.get("human_note", ""),
            "attachment_reference": action.get("attachment_reference", ""),
            "status": action.get("status", "unresolved"),
            "source_action_id": action.get("action_id", ""),
        })
    return rows


def write_correction_plan_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CORRECTION_PLAN_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_safe_row(row, CORRECTION_PLAN_FIELDNAMES))


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def write_correction_plan_markdown(path: Path, rows: list[dict[str, str]]) -> None:
    lines = [
        "# Pre-submission Correction Plan",
        "",
        "| Finding ID | Risk | Required correction | Owner | Evidence after correction | Attachment/reference | Status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    if rows:
        for row in rows:
            lines.append(
                "| "
                + " | ".join([
                    markdown_cell(row.get("finding_id", "")),
                    markdown_cell(row.get("risk", "")),
                    markdown_cell(row.get("required_correction", "")),
                    markdown_cell(row.get("owner", "")),
                    markdown_cell(row.get("evidence_after_correction", "")),
                    markdown_cell(row.get("attachment_reference", "")),
                    markdown_cell(row.get("status", "")),
                ])
                + " |"
            )
    else:
        lines.append("|  |  | No unresolved correction currently listed within this audit scope. |  |  |  |  |")
    lines += [
        "",
        "## Before Submission",
        "",
        "- Resolve all R4 findings.",
        "- Resolve or explicitly document all R3 findings.",
        "- Add source data and uncropped/raw records for figures that depend on images or quantitative summaries.",
        "- Update figure legends for cropping, splicing, reuse, normalization, and statistical definitions.",
        "- Update methods for randomization, blinding, sample size, exclusions, reagents, software, and repository accessions.",
        "",
        "> This is a team-tracking worksheet derived from calibrated audit actions. It is not an approval certificate.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_empty_action_tracker_csv(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ACTION_FIELDNAMES)
        writer.writeheader()


def author_signoff_template(audit_id: str) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "audit_id": audit_id,
        "scope_note": "Sign-offs document review responsibility; they are not a misconduct or correctness verdict.",
        "signoffs": {
            "figure_preparer": {
                "name": "",
                "date": "",
                "confirms": [
                    "displayed figures trace to supplied raw/source records where available",
                    "image-processing steps and figure assembly decisions are documented",
                    "unresolved R3/R4 image concerns have been resolved or escalated before submission",
                ],
            },
            "data_or_statistical_owner": {
                "name": "",
                "date": "",
                "confirms": [
                    "source data reproduce reported summary statistics where checked",
                    "n and experimental units are correctly defined",
                    "exclusions and outlier decisions are documented",
                ],
            },
            "corresponding_author": {
                "name": "",
                "date": "",
                "confirms": [
                    "unresolved R3/R4 concerns are resolved before submission",
                    "data, code, materials, and ethics statements match supplied records",
                    "authors reviewed the final submission QC packet",
                ],
            },
            "all_authors": [],
        },
    }


def human_report_markdown(markdown_text: str) -> str:
    """Remove the machine JSON appendix from human-facing derivatives."""
    kept: list[str] = []
    skipping_summary = False
    for line in markdown_text.splitlines():
        if line.strip().startswith("```json AUDIT_JSON_SUMMARY"):
            skipping_summary = True
            kept.extend([
                "> Machine-readable details are stored separately in `AUDIT_JSON_SUMMARY.json`.",
                "> 机器可读明细已单独保存于 `AUDIT_JSON_SUMMARY.json`。",
            ])
            continue
        if skipping_summary:
            if line.strip() == "```":
                skipping_summary = False
            continue
        kept.append(line)
    return "\n".join(kept).rstrip() + "\n"


def inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def markdown_table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_markdown_table_separator(line: str) -> bool:
    cells = markdown_table_cells(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def markdown_to_basic_html(markdown_text: str, title: str) -> str:
    lines = human_report_markdown(markdown_text).splitlines()
    body_lines: list[str] = []
    in_code = False
    in_list = False
    idx = 0
    while idx < len(lines):
        line = lines[idx].rstrip()
        if line.startswith("```"):
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            body_lines.append("</code></pre>" if in_code else "<pre><code>")
            in_code = not in_code
            idx += 1
            continue
        if in_code:
            body_lines.append(html.escape(line))
            idx += 1
            continue
        if idx + 1 < len(lines) and "|" in line and is_markdown_table_separator(lines[idx + 1]):
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            headers = markdown_table_cells(line)
            body_lines.append("<table><thead><tr>" + "".join(f"<th>{inline_markdown(cell)}</th>" for cell in headers) + "</tr></thead><tbody>")
            idx += 2
            while idx < len(lines) and "|" in lines[idx] and lines[idx].strip():
                cells = markdown_table_cells(lines[idx])
                body_lines.append("<tr>" + "".join(f"<td>{inline_markdown(cell)}</td>" for cell in cells) + "</tr>")
                idx += 1
            body_lines.append("</tbody></table>")
            continue
        if line.startswith("- "):
            if not in_list:
                body_lines.append("<ul>")
                in_list = True
            body_lines.append(f"<li>{inline_markdown(line[2:].strip())}</li>")
            idx += 1
            continue
        if in_list:
            body_lines.append("</ul>")
            in_list = False
        stripped = line.strip()
        if stripped in {"<details>", "</details>"}:
            body_lines.append(stripped)
        elif stripped.startswith("<summary>") and stripped.endswith("</summary>"):
            summary = stripped[len("<summary>"):-len("</summary>")]
            body_lines.append(f"<summary>{inline_markdown(summary)}</summary>")
        elif line.startswith("# "):
            body_lines.append(f"<h1>{inline_markdown(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            body_lines.append(f"<h2>{inline_markdown(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            body_lines.append(f"<h3>{inline_markdown(line[4:].strip())}</h3>")
        elif line.startswith("> "):
            body_lines.append(f"<blockquote>{inline_markdown(line[2:].strip())}</blockquote>")
        elif re.fullmatch(r"\s*---+\s*", line):
            body_lines.append("<hr>")
        elif line:
            body_lines.append(f"<p>{inline_markdown(line)}</p>")
        idx += 1
    if in_list:
        body_lines.append("</ul>")
    return "\n".join([
        "<!doctype html>",
        "<html lang=\"en\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        f"<title>{html.escape(title)}</title>",
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',sans-serif;max-width:980px;margin:40px auto;padding:0 20px;line-height:1.55;color:#1f2937}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f8fafc;padding:16px;border:1px solid #e5e7eb}code{font-family:ui-monospace,SFMono-Regular,monospace}blockquote{border-left:4px solid #0f766e;padding-left:12px;color:#475569}table{width:100%;border-collapse:collapse;margin:16px 0;font-size:.94rem}td,th{border:1px solid #cbd5e1;padding:6px 8px;text-align:left;vertical-align:top}th{background:#f1f5f9}details{border:1px solid #e2e8f0;padding:10px 12px;margin:12px 0}@media print{body{max-width:none;margin:0}details{display:block}details>*{display:block!important}}</style>",
        "</head>",
        "<body>",
        *body_lines,
        "</body>",
        "</html>",
    ])


def markdown_to_pdf_text(markdown_text: str) -> str:
    lines: list[str] = []
    in_code = False
    for raw in human_report_markdown(markdown_text).splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if line in {"<details>", "</details>"}:
            continue
        line = re.sub(r"^<summary>(.*?)</summary>$", r"\1", line)
        if not in_code:
            line = re.sub(r"^#{1,6}\s+", "", line)
            line = re.sub(r"^>\s?", "", line)
            line = re.sub(r"^[-*]\s+", "• ", line)
            line = line.replace("**", "").replace("`", "")
            if is_markdown_table_separator(line):
                continue
        lines.append(line)
    return "\n".join(lines)


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in text)


def wrap_display_text(text: str, width: int = 88) -> list[str]:
    if not text:
        return [""]
    wrapped: list[str] = []
    current = ""
    last_space = -1
    for char in text:
        candidate = current + char
        if display_width(candidate) <= width:
            current = candidate
            if char.isspace():
                last_space = len(current) - 1
            continue
        if last_space > 0:
            wrapped.append(current[:last_space].rstrip())
            current = current[last_space + 1:] + char
        else:
            wrapped.append(current.rstrip())
            current = char
        last_space = current.rfind(" ")
    if current or not wrapped:
        wrapped.append(current.rstrip())
    return wrapped


def write_basic_pdf(path: Path, text: str) -> bool:
    try:
        import fitz  # type: ignore
    except Exception:
        return False
    try:
        doc = fitz.open()

        def new_page():
            created = doc.new_page(width=595, height=842)
            created.insert_font(fontname="china-s")
            return created

        page = new_page()
        y = 50.0
        for paragraph in markdown_to_pdf_text(text).splitlines():
            for line in wrap_display_text(paragraph):
                if y > 800:
                    page = new_page()
                    y = 50.0
                page.insert_text((50, y), line, fontsize=9, fontname="china-s")
                y += 12.5
        doc.set_metadata({"title": "Biomedical submission QC report", "subject": "Human-readable research integrity audit output"})
        doc.save(path)
        doc.close()
        return True
    except Exception:  # noqa: BLE001 - PDF is an optional derivative; Markdown/HTML remain authoritative.
        path.unlink(missing_ok=True)
        return False


def risk_label(summary: dict[str, Any]) -> str:
    risk = str(summary.get("overall_risk") or "R1")
    labels = {
        "R0": "R0 - no specific issue found within supplied scope",
        "R1": "R1 - completeness or audit-coverage gap",
        "R2": "R2 - minor reporting concern",
        "R3": "R3 - integrity concern requiring explanation",
        "R4": "R4 - high-risk inconsistency in supplied materials",
    }
    return labels.get(risk, risk)


def flattened_action_rows(audit_summary: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    categories = (audit_summary.get("action_queue") or {}).get("categories") or {}
    for category_rows in categories.values():
        for row in category_rows or []:
            if isinstance(row, dict):
                rows.append({key: str(row.get(key, "")) for key in ACTION_FIELDNAMES})
    return rows


def action_rows_by_owner(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        owner = row.get("owner") or "unassigned"
        grouped.setdefault(owner, []).append(row)
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def count_by_risk(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {risk: 0 for risk in RISK_ORDER}
    for item in findings:
        risk = str(item.get("risk_level") or item.get("calibrated_risk_level") or "")
        if risk in counts:
            counts[risk] += 1
    return counts


def top_locations(rows: list[dict[str, str]], limit: int = 8) -> list[str]:
    locations = []
    seen = set()
    for row in rows:
        location = str(row.get("location", "")).strip()
        if not location or location in seen:
            continue
        seen.add(location)
        locations.append(location)
        if len(locations) >= limit:
            break
    return locations


def write_pi_brief(
    path: Path,
    audit_summary: dict[str, Any],
    coverage: dict[str, Any],
    action_rows: list[dict[str, str]],
    claim_coverage: dict[str, Any],
) -> None:
    findings = audit_summary.get("findings", []) or []
    risk_counts_map = count_by_risk(findings)
    must_resolve = [row for row in action_rows if row.get("action_category") == "must_resolve"]
    provide_materials = [row for row in action_rows if row.get("action_category") == "provide_materials"]
    modules_not_run = coverage.get("modules_not_executed") or []
    lines = [
        "# PI Brief / PI 快速版",
        "",
        "> Internal quality-control brief. This is not a clean-submission certificate and does not determine misconduct, intent, or author responsibility.",
        "> 内部质控简报；不是投稿放行证明，也不判断学术不端、意图或作者责任。",
        "",
        "## Quick Read",
        "",
        f"- Overall audit level: {risk_label(audit_summary)}.",
        f"- Candidate findings: {len(findings)}.",
        f"- Open actions: {len(action_rows)} total; {len(must_resolve)} must-resolve; {len(provide_materials)} material-request items.",
        f"- Claim manifest supplied: {'yes' if claim_coverage.get('supplied') else 'no'}.",
        f"- Image panels screened: {coverage.get('image_panels_screened', 0)}; unreadable images: {coverage.get('image_files_unreadable', 0)}.",
        "",
        "## Finding Counts",
        "",
        "| Level | Count |",
        "| --- | ---: |",
    ]
    for risk in RISK_ORDER:
        lines.append(f"| {risk} | {risk_counts_map.get(risk, 0)} |")
    lines += [
        "",
        "## Must Resolve First",
        "",
    ]
    if must_resolve:
        for row in must_resolve[:10]:
            lines.append(
                f"- `{row.get('risk_level', '')}` {row.get('location', '')}: {row.get('required_action', '')} "
                f"(owner suggestion: {row.get('owner', 'unassigned')})"
            )
        if len(must_resolve) > 10:
            lines.append(f"- ... {len(must_resolve) - 10} more in `unresolved_actions.csv`.")
    else:
        lines.append("- No must-resolve action is currently listed within the supplied scope.")
    lines += [
        "",
        "## Materials Needed",
        "",
    ]
    if provide_materials:
        for row in provide_materials[:10]:
            lines.append(f"- {row.get('location', '')}: {row.get('required_action', '')}")
        if len(provide_materials) > 10:
            lines.append(f"- ... {len(provide_materials) - 10} more in `unresolved_actions.csv`.")
    else:
        lines.append("- No material-request action is currently listed, but scope limits may still apply.")
    lines += [
        "",
        "## Scope Limits To Read Before Submission",
        "",
    ]
    if modules_not_run:
        for module in modules_not_run[:10]:
            lines.append(f"- {module}")
    else:
        lines.append("- No module-level scope limit was recorded in the supplied coverage block.")
    lines += [
        "",
        "## Suggested Next Step",
        "",
        "Assign the open rows in `unresolved_actions.csv`, then re-run the audit and compare the new output with this packet.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_coauthor_actions(path: Path, action_rows: list[dict[str, str]]) -> None:
    lines = [
        "# Co-author Action Requests / 共同作者行动清单",
        "",
        "> Copy from this file into internal messages. Each item is framed as documentation follow-up, not an accusation.",
        "> 可将以下文字复制到内部沟通中；每项都是资料核对请求，不是指控。",
        "",
    ]
    if not action_rows:
        lines += [
            "No open action row is currently listed within this audit scope.",
            "",
        ]
    for owner, rows in action_rows_by_owner(action_rows).items():
        lines += [f"## Owner suggestion: {owner}", ""]
        for row in rows:
            lines += [
                f"### {row.get('action_id', '')} - {row.get('location', '')}",
                "",
                f"- Category: {row.get('action_category', '')}",
                f"- Risk level: {row.get('risk_level', '')}",
                f"- Requested action: {row.get('required_action', '')}",
                "",
                "**Message to send / 可发送文字**",
                "",
                row.get("neutral_inquiry_template")
                or f"Could you review `{row.get('location', '')}` and clarify the source records needed to resolve this item?",
                "",
                "**Materials requested / 需补材料**",
                "",
                row.get("material_request_template")
                or f"Please add or link the materials needed to resolve `{row.get('location', '')}`.",
                "",
            ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_journal_response_draft(
    path: Path,
    audit_summary: dict[str, Any],
    action_rows: list[dict[str, str]],
) -> None:
    findings = audit_summary.get("findings", []) or []
    must_resolve = [row for row in action_rows if row.get("action_category") == "must_resolve"]
    material_locations = top_locations(
        [row for row in action_rows if row.get("action_category") == "provide_materials"],
        limit=10,
    )
    lines = [
        "# Journal / Reviewer Response Draft",
        "",
        "> Drafting aid only. Do not submit unchanged. Replace bracketed text with study-specific facts and attach the relevant source records before sending externally.",
        "> 仅为起草辅助；不要原样提交。外发前请替换方括号内容，并附上相应 source/raw records。",
        "",
        "Dear [Editor/Reviewer],",
        "",
        "Thank you for raising these points. We reviewed the supplied manuscript package, source records, and audit outputs. The observations below are treated as documentation and traceability questions, not conclusions about intent or responsibility.",
        "",
        "## Summary Position",
        "",
        f"- Current audit level within supplied materials: {risk_label(audit_summary)}.",
        f"- Candidate findings reviewed: {len(findings)}.",
        f"- Must-resolve internal actions still open: {len(must_resolve)}.",
        "",
        "We are resolving the items by checking the underlying source data, raw image records, figure assembly history, and analysis notes. Where a record is missing or unavailable, we will state that limitation explicitly rather than treating the item as cleared.",
        "",
        "## Point-by-point Draft",
        "",
    ]
    if findings:
        for item in findings[:12]:
            lines += [
                f"### {item.get('finding_id', '')}: {item.get('location', '')}",
                "",
                f"- Audit observation: {item.get('finding_type', '')} ({item.get('risk_level', '')}).",
                f"- Materials being checked: {'; '.join(item.get('required_materials_to_resolve', []) or ['source/raw records and supporting documentation'])}.",
                f"- Planned response: We will verify this item against the source records and provide the relevant documentation or correction as appropriate.",
                "",
            ]
        if len(findings) > 12:
            lines.append(f"_Additional findings are tracked internally in `unresolved_actions.csv` ({len(findings) - 12} more)._")
            lines.append("")
    else:
        lines += [
            "No specific finding card is currently listed within the supplied scope. We will still document audit coverage and any missing materials before treating the response as complete.",
            "",
        ]
    lines += [
        "## Materials Being Added Or Checked",
        "",
    ]
    if material_locations:
        for location in material_locations:
            lines.append(f"- {location}")
    else:
        lines.append("- [List source data, raw images, analysis files, protocols, or figure assembly records to attach.]")
    lines += [
        "",
        "Sincerely,",
        "",
        "[Corresponding author / study team]",
        "",
        "Boundary note: this draft avoids misconduct or intent language. It should be finalized only after the responsible authors review the source records.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_audience_exports(
    packet_dir: Path,
    audit_summary: dict[str, Any],
    coverage: dict[str, Any],
    action_rows: list[dict[str, str]],
    claim_coverage: dict[str, Any],
) -> dict[str, str]:
    export_dir = packet_dir / "audience_exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    write_pi_brief(export_dir / AUDIENCE_EXPORT_FILES["pi_brief"], audit_summary, coverage, action_rows, claim_coverage)
    write_coauthor_actions(export_dir / AUDIENCE_EXPORT_FILES["coauthor_actions"], action_rows)
    write_journal_response_draft(export_dir / AUDIENCE_EXPORT_FILES["journal_response_draft"], audit_summary, action_rows)
    readme_lines = [
        "# Audience Exports",
        "",
        "These are copy/edit starting points for different readers. They do not replace the full audit report.",
        "",
        "- `PI_BRIEF.md` — short internal brief for the PI/corresponding author.",
        "- `COAUTHOR_ACTIONS.md` — owner-grouped internal follow-up requests with neutral wording.",
        "- `JOURNAL_RESPONSE_DRAFT.md` — external response draft scaffold; do not submit unchanged.",
        "",
        "Boundary: these files are not pass/fail decisions and do not determine misconduct, intent, or author responsibility.",
        "中文提示：这些文件是沟通草稿，不是投稿放行证明，也不判断作者意图或责任。",
    ]
    (export_dir / "README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
    return {
        key: f"audience_exports/{filename}"
        for key, filename in AUDIENCE_EXPORT_FILES.items()
    }


def copy_if_exists(source: Path, target: Path) -> bool:
    if not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def copy_tree_if_exists(source: Path, target: Path) -> bool:
    if not source.is_dir():
        return False
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return True


def image_file_base(path: str) -> str:
    return str(path or "").split("#", 1)[0]


def is_image_snapshot_file(item: dict[str, Any]) -> bool:
    path = str(item.get("path", ""))
    role = str(item.get("role", "")).lower()
    return Path(path).suffix.lower() in IMAGE_FILE_EXTS or role in {"figures", "raw_images"}


def edge_for_image_finding(finding: dict[str, Any]) -> dict[str, Any]:
    evidence = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
    representative = evidence.get("representative_edge")
    if isinstance(representative, dict):
        return representative
    for key in ("contextual_edges", "edges"):
        edges = evidence.get(key)
        if isinstance(edges, list) and edges and isinstance(edges[0], dict):
            return edges[0]
    return {}


def is_image_review_finding(finding: dict[str, Any]) -> bool:
    finding_type = str(finding.get("finding_type", ""))
    if finding_type in IMAGE_REVIEW_FINDING_TYPES:
        return True
    text = " ".join(
        str(finding.get(key, ""))
        for key in ("module", "finding_type", "evidence_type", "location")
    ).lower()
    return "image" in text or "figure" in text or "raw_image" in text


def evidence_crop_paths(edge: dict[str, Any]) -> list[str]:
    crops = edge.get("evidence_crops")
    if not isinstance(crops, dict):
        return []
    return [str(path) for path in crops.values() if str(path).strip()]


def copy_review_evidence_file(source_value: str, output_dir: Path, packet_dir: Path) -> str:
    source = Path(source_value)
    if not source.is_absolute():
        source = output_dir / source
    if not source.is_file():
        return ""
    target_dir = packet_dir / "evidence"
    if "local_patch" in source.parts:
        target_dir = target_dir / "local_patch"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    shutil.copy2(source, target)
    return target.relative_to(packet_dir).as_posix()


def image_review_candidate_rows(
    output_dir: Path,
    packet_dir: Path,
    calibrated: dict[str, Any],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for finding in calibrated.get("findings", []) or []:
        if not isinstance(finding, dict) or not is_image_review_finding(finding):
            continue
        edge = edge_for_image_finding(finding)
        copied_evidence = [
            rel
            for rel in (copy_review_evidence_file(path, output_dir, packet_dir) for path in evidence_crop_paths(edge))
            if rel
        ]
        score_or_ratio = ""
        for key in ("score", "inlier_ratio", "best_hamming_distance"):
            if key in edge:
                score_or_ratio = str(edge.get(key))
                break
        key_metric = ""
        for key in ("tile_hit_count", "inlier_count", "good_matches", "hash_distance"):
            if key in edge:
                key_metric = f"{human_readable_key(key)}={edge.get(key)}"
                break
        rows.append({
            "finding_id": str(finding.get("finding_id", "")),
            "risk_level": str(finding.get("calibrated_risk_level") or finding.get("risk_level", "")),
            "finding_type": str(finding.get("finding_type", "")),
            "location": str(finding.get("location", "")),
            "left": str(edge.get("left", "")),
            "right": str(edge.get("right", "")),
            "similarity_scope": str(edge.get("similarity_scope", "")),
            "best_transform": str(edge.get("best_transform", "")),
            "score_or_ratio": score_or_ratio,
            "key_metric": key_metric,
            "evidence_files": "; ".join(copied_evidence),
            "recommended_action": str(finding.get("recommended_action", "")),
        })
    return rows


def human_readable_key(value: str) -> str:
    return str(value).replace("_", " ")


def write_image_review_candidates_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=IMAGE_REVIEW_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_safe_row(row, IMAGE_REVIEW_CSV_FIELDS))


def image_review_tracker_rows(candidate_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, row in enumerate(candidate_rows, start=1):
        candidate_files = "; ".join(
            item for item in (row.get("left", ""), row.get("right", ""), row.get("evidence_files", "")) if item
        )
        rows.append({
            "review_item_id": f"IMG-REV-{index:04d}",
            "source_finding_id": row.get("finding_id", ""),
            "finding_type": row.get("finding_type", ""),
            "risk_level": row.get("risk_level", ""),
            "location": row.get("location", ""),
            "candidate_files": candidate_files,
            "recommended_external_review": "ImageTwin/Proofig/manual image review; verify against raw acquisition records before interpretation",
            "review_owner": "",
            "review_status": "unresolved",
            "external_tool_or_method": "",
            "review_result_note": "",
            "attachment_reference": "",
        })
    return rows


def write_image_review_tracker_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=IMAGE_REVIEW_TRACKER_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_safe_row(row, IMAGE_REVIEW_TRACKER_FIELDS))


def external_handoff_priority(risk_level: str) -> str:
    if risk_level in {"R4", "R3"}:
        return "priority_review"
    if risk_level == "R2":
        return "standard_review"
    return "context_or_completeness_review"


def external_tool_route(finding_type: str, similarity_scope: str) -> str:
    text = f"{finding_type} {similarity_scope}".lower()
    if "channel_metadata" in text:
        return "manual microscopy metadata review with raw multichannel files, channel map, and acquisition records"
    if "splice" in text:
        return "specialist image-forensics review of raw files and assembly history; use ELA/JPEG, JPEG-ghost profile, noise, and CFA-like grid prompts only as triage"
    if "keypoint" in text or "geometric" in text:
        return "ImageTwin/Proofig or local feature-match review for rotated, resized, cropped, or perspective-shifted similarity"
    if "local_patch" in text or "copy_move" in text:
        return "Proofig/ImageTwin or manual region-level review using side-by-side crops plus raw acquisition records"
    if "image_reuse" in text or "near_duplicate" in text:
        return "ImageTwin/Proofig cross-image review of the candidate files and full figure context"
    return "manual image review with raw/source records and figure-assembly history"


def external_review_question(row: dict[str, str]) -> str:
    finding_type = row.get("finding_type", "")
    location = row.get("location", "")
    left = row.get("left", "")
    right = row.get("right", "")
    scope = row.get("similarity_scope", "")
    if finding_type == "channel_metadata_verification_gap":
        return (
            "Can the supplied raw multichannel/Z-stack file, channel map, and acquisition metadata support the declared "
            f"same-field or related-channel explanation for {location or left or right}?"
        )
    if finding_type == "splice_forensics_triage_signal":
        return (
            "Do the raw files and figure-assembly history explain the localized residual/noise prompt, or is specialist "
            "image-forensics review needed before submission?"
        )
    if finding_type == "same_image_copy_move":
        return (
            "Do the marked regions within the same image have a documented acquisition, processing, or assembly explanation "
            "when checked against the raw file and processing history?"
        )
    if finding_type == "keypoint_geometric_match":
        return (
            "Does an external image-review tool or manual feature review confirm a rotated/resized/cropped/perspective-shifted "
            f"relationship between {left or 'the first image'} and {right or 'the comparison image'}, and is that relationship expected?"
        )
    if finding_type == "local_patch_reuse":
        return (
            "Does the side-by-side crop evidence represent expected same-source material, or does it require raw-image and "
            "sample-map clarification before submission?"
        )
    if scope:
        return f"Does external or manual review support an expected explanation for this {scope} image candidate?"
    return "Does external or manual figure review support an expected explanation for this image candidate?"


def image_external_handoff_rows(candidate_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    governance = (
        "Check institutional, journal, patient/privacy, and collaborator rules before uploading images or raw records "
        "to any external service."
    )
    for index, row in enumerate(candidate_rows, start=1):
        candidate_files = "; ".join(
            item for item in (row.get("left", ""), row.get("right", "")) if item
        )
        context_bits = [
            item
            for item in (
                f"location={row.get('location', '')}" if row.get("location") else "",
                f"scope={row.get('similarity_scope', '')}" if row.get("similarity_scope") else "",
                f"transform={row.get('best_transform', '')}" if row.get("best_transform") else "",
                f"score_or_ratio={row.get('score_or_ratio', '')}" if row.get("score_or_ratio") else "",
                row.get("key_metric", ""),
            )
            if item
        ]
        rows.append({
            "handoff_item_id": f"IMG-HANDOFF-{index:04d}",
            "source_finding_id": row.get("finding_id", ""),
            "priority": external_handoff_priority(row.get("risk_level", "")),
            "finding_type": row.get("finding_type", ""),
            "risk_level": row.get("risk_level", ""),
            "candidate_files": candidate_files,
            "evidence_files": row.get("evidence_files", ""),
            "recommended_tool_route": external_tool_route(row.get("finding_type", ""), row.get("similarity_scope", "")),
            "review_question": external_review_question(row),
            "supporting_context": "; ".join(context_bits),
            "data_governance_note": governance,
            "review_status": "unresolved",
            "reviewer": "",
            "external_result_reference": "",
        })
    return rows


def write_external_tool_handoff_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=IMAGE_TOOL_HANDOFF_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_safe_row(row, IMAGE_TOOL_HANDOFF_FIELDS))


def write_external_tool_handoff_markdown(path: Path, rows: list[dict[str, str]]) -> None:
    lines = [
        "# External Image-Review Handoff",
        "",
        "This file helps a PI, image specialist, or external tool operator review the image candidates in this packet.",
        "It is a handoff aid, not an external-search result, approval certificate, misconduct finding, or statement about intent.",
        "",
        "Before using ImageTwin, Proofig, or any hosted review service, confirm institutional, journal, patient/privacy, and collaborator rules for uploading manuscript, figure, or raw image files.",
        "",
        "Recommended workflow:",
        "",
        "1. Open `external_tool_handoff.csv` and sort by `priority`.",
        "2. Review the listed candidate files, evidence crops, and detector payloads.",
        "3. Run the recommended external tool or manual review route when allowed.",
        "4. Record the reviewer, method, result note, and attachment path in `image_review_tracker.csv`.",
        "5. Interpret any external-tool output together with raw acquisition records, figure assembly history, sample/channel/lane maps, and benign explanations.",
        "",
        "中文提示：本文件用于把候选图像问题交给 ImageTwin、Proofig 或人工图像专家复核。它不是“通过/不通过”结论，也不判断作者意图。上传外部服务前，请先确认机构、期刊、患者隐私和合作者规则。",
        "",
    ]
    if rows:
        lines.extend([
            "## Handoff Items",
            "",
            "| ID | Priority | Finding | Recommended route | Review question |",
            "| --- | --- | --- | --- | --- |",
        ])
        for row in rows:
            lines.append(
                "| {handoff_item_id} | {priority} | {finding_type} ({risk_level}) | {route} | {question} |".format(
                    handoff_item_id=row.get("handoff_item_id", ""),
                    priority=row.get("priority", ""),
                    finding_type=row.get("finding_type", ""),
                    risk_level=row.get("risk_level", ""),
                    route=str(row.get("recommended_tool_route", "")).replace("|", "/"),
                    question=str(row.get("review_question", "")).replace("|", "/"),
                )
            )
    else:
        lines.extend([
            "## Handoff Items",
            "",
            "No calibrated image candidates were present. If image files were supplied, use `image_files.csv` as an inventory for optional manual review.",
        ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_image_review_files_csv(
    path: Path,
    snapshot: dict[str, Any],
    referenced_paths: set[str],
) -> list[dict[str, Any]]:
    rows = []
    for item in snapshot.get("files", []) or []:
        if not isinstance(item, dict) or not is_image_snapshot_file(item):
            continue
        file_path = str(item.get("path", ""))
        rows.append({
            "path": file_path,
            "role": str(item.get("role", "")),
            "sha256": str(item.get("sha256", "")),
            "size_bytes": str(item.get("size_bytes", "")),
            "candidate_referenced": "yes" if file_path in referenced_paths else "no",
        })
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=IMAGE_FILE_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_safe_row(row, IMAGE_FILE_CSV_FIELDS))
    return rows


def export_image_review_packet(
    output_dir: Path,
    packet_dir: Path,
    audit_summary: dict[str, Any],
    coverage: dict[str, Any],
    calibrated: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    image_file_count = sum(
        1
        for item in snapshot.get("files", []) or []
        if isinstance(item, dict) and is_image_snapshot_file(item)
    )
    has_image_context = bool(image_file_count or any(is_image_review_finding(item) for item in calibrated.get("findings", []) or []))
    if not has_image_context:
        return {
            "packet_dir": "",
            "candidate_count": 0,
            "image_file_count": 0,
            "positive_provenance_count": 0,
            "copied_artifacts": [],
        }

    review_dir = packet_dir / "image_review_packet"
    review_dir.mkdir(parents=True, exist_ok=True)
    candidate_rows = image_review_candidate_rows(output_dir, review_dir, calibrated)
    referenced = {
        image_file_base(path)
        for row in candidate_rows
        for path in (row.get("left", ""), row.get("right", ""))
        if image_file_base(path)
    }
    image_rows = write_image_review_files_csv(review_dir / "image_files.csv", snapshot, referenced)
    write_image_review_candidates_csv(review_dir / "image_review_candidates.csv", candidate_rows)
    tracker_rows = image_review_tracker_rows(candidate_rows)
    write_image_review_tracker_csv(review_dir / "image_review_tracker.csv", tracker_rows)
    handoff_rows = image_external_handoff_rows(candidate_rows)
    write_external_tool_handoff_csv(review_dir / "external_tool_handoff.csv", handoff_rows)
    write_external_tool_handoff_markdown(review_dir / "EXTERNAL_TOOL_HANDOFF.md", handoff_rows)

    detector_payloads = review_dir / "detector_payloads"
    copied_payloads = []
    for name in IMAGE_REVIEW_ARTIFACTS:
        if copy_if_exists(output_dir / name, detector_payloads / name):
            copied_payloads.append(f"detector_payloads/{name}")

    positive_rows = audit_summary.get("positive_provenance", []) or []
    payload = {
        "schema_version": "0.1.0",
        "candidate_count": len(candidate_rows),
        "image_file_count": len(image_rows),
        "positive_provenance_count": len(positive_rows),
        "candidates_csv": "image_review_candidates.csv",
        "tracker_csv": "image_review_tracker.csv",
        "external_tool_handoff_csv": "external_tool_handoff.csv",
        "external_tool_handoff_guide": "EXTERNAL_TOOL_HANDOFF.md",
        "image_files_csv": "image_files.csv",
        "detector_payloads": copied_payloads,
        "coverage": {
            "image_panels_screened": coverage.get("image_panels_screened", 0),
            "keypoint_pairs_screened": coverage.get("keypoint_pairs_screened", 0),
            "image_files_unreadable": coverage.get("image_files_unreadable", 0),
            "image_screening_boundary": coverage.get("image_screening_boundary", {}),
        },
        "positive_provenance": positive_rows,
        "scope_note": (
            "This packet is a target list for external image-review tools or human image-integrity review. "
            "It does not perform cross-paper image search and is not a misconduct or correctness verdict."
        ),
        "data_governance_note": (
            "External image-review services may require uploading manuscript or raw image files outside the lab. "
            "Check institutional, journal, patient/privacy, and collaborator rules before upload."
        ),
    }
    write_json(review_dir / "image_review_manifest.json", payload)

    readme_lines = [
        "# Image Review Packet",
        "",
        "Use this folder as a target list for ImageTwin, Proofig, or manual figure review.",
        "It organizes candidate image findings and relevant files; it does not determine misconduct, intent, or correctness.",
        "",
        "Suggested reading order:",
        "",
        "1. `image_review_candidates.csv` — candidate pairs/locations and evidence metrics.",
        "2. `image_review_tracker.csv` — editable follow-up tracker for reviewer, status, external tool/method, notes, and evidence attachment reference.",
        "3. `external_tool_handoff.csv` and `EXTERNAL_TOOL_HANDOFF.md` — tool/operator handoff list with recommended review route, review question, and data-governance note.",
        "4. `image_files.csv` — supplied image-like files with hashes and candidate references.",
        "5. `evidence/` — copied crop/side-by-side evidence from local-patch detectors when available.",
        "6. `detector_payloads/` — raw image-detector JSON payloads for technical audit trail.",
        "7. `image_review_manifest.json` — machine-readable packet summary, coverage boundary, and positive provenance.",
        "",
        "`image_review_tracker.csv` is for team follow-up after ImageTwin, Proofig, or manual review. It is not an automated clearance sheet.",
        "",
        "Boundary: no candidate here is a misconduct finding. Raw acquisition records, figure assembly history, and sample/channel/lane maps are still required for interpretation.",
        "",
        "中文提示：本目录是给外部图像工具或人工复核使用的候选索引，不是学术不端结论。上传外部服务前请先确认机构、期刊、患者隐私和合作者规则。",
    ]
    (review_dir / "README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")

    return {
        "packet_dir": str(review_dir),
        "candidate_count": len(candidate_rows),
        "tracker_count": len(tracker_rows),
        "external_handoff_count": len(handoff_rows),
        "image_file_count": len(image_rows),
        "positive_provenance_count": len(positive_rows),
        "copied_artifacts": sorted(copied_payloads),
    }


def export_submission_qc_packet(
    output_dir: Path,
    manifest: dict[str, Any],
    audit_summary: dict[str, Any],
    coverage: dict[str, Any],
    calibrated: dict[str, Any],
    snapshot: dict[str, Any],
    claim_coverage: dict[str, Any],
    methodology_checklist: dict[str, Any] | None = None,
    writing_readiness: dict[str, Any] | None = None,
    re_audit_diff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet_dir = output_dir / "submission_qc_packet"
    if packet_dir.exists():
        shutil.rmtree(packet_dir)
    packet_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for name in ("audit-report.md", "AUDIT_JSON_SUMMARY.json", "coverage.json", "calibrated_findings.json"):
        if copy_if_exists(output_dir / name, packet_dir / name):
            copied.append(name)
    for name in (
        "pdf_structure.json",
        "docx_structure.json",
        "xlsx_structure.json",
        "prism_project_intake.json",
        "fcs_metadata_intake.json",
        "pdf_embedded_images.json",
        "pptx_structure.json",
        "pptx_embedded_images.json",
        "key_embedded_images.json",
        "psd_preview_images.json",
        "image_metadata.json",
        "channel_metadata_candidates.json",
        "splice_forensics_candidates.json",
    ):
        if copy_if_exists(output_dir / name, packet_dir / name):
            copied.append(name)
    if copy_tree_if_exists(output_dir / "pdf_embedded_images", packet_dir / "pdf_embedded_images"):
        copied.append("pdf_embedded_images/")
    if copy_tree_if_exists(output_dir / "pptx_embedded_images", packet_dir / "pptx_embedded_images"):
        copied.append("pptx_embedded_images/")
    if copy_tree_if_exists(output_dir / "key_embedded_images", packet_dir / "key_embedded_images"):
        copied.append("key_embedded_images/")
    if copy_tree_if_exists(output_dir / "psd_preview_images", packet_dir / "psd_preview_images"):
        copied.append("psd_preview_images/")

    write_json(packet_dir / "audit_snapshot.json", snapshot)
    write_json(packet_dir / "file_hash_manifest.json", build_file_hash_manifest(snapshot))
    write_json(packet_dir / "claim_coverage.json", claim_coverage)
    if methodology_checklist is not None:
        write_json(packet_dir / "methodology_checklist.json", methodology_checklist)
        copy_if_exists(output_dir / "methodology_checklist.csv", packet_dir / "methodology_checklist.csv")
    if writing_readiness is not None:
        write_json(packet_dir / "writing_readiness.json", writing_readiness)
        copy_if_exists(output_dir / "writing_readiness.csv", packet_dir / "writing_readiness.csv")
    write_json(packet_dir / "calibrated_findings.json", calibrated)
    write_missing_materials_csv(packet_dir / "missing_materials.csv", manifest)
    write_verified_traceability_csv(packet_dir / "verified_traceability.csv", audit_summary)
    write_claim_coverage_csv(packet_dir / "claim_coverage.csv", claim_coverage)
    action_rows = unresolved_action_rows(manifest, audit_summary, claim_coverage)
    write_unresolved_actions_csv(packet_dir / "unresolved_actions.csv", action_rows)
    audience_exports = write_audience_exports(packet_dir, audit_summary, coverage, action_rows, claim_coverage)
    plan_rows = correction_plan_rows(action_rows)
    write_correction_plan_csv(packet_dir / "correction_plan.csv", plan_rows)
    write_correction_plan_markdown(packet_dir / "correction_plan.md", plan_rows)
    write_empty_action_tracker_csv(packet_dir / "resolved_actions.csv")
    write_empty_action_tracker_csv(packet_dir / "accepted_with_reason.csv")
    (packet_dir / "author_signoff.yaml").write_text(
        yaml.safe_dump(author_signoff_template(str(snapshot.get("audit_id", ""))), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    report_text = (output_dir / "audit-report.md").read_text(encoding="utf-8") if (output_dir / "audit-report.md").is_file() else ""
    (packet_dir / "audit-report.html").write_text(
        markdown_to_basic_html(report_text, "Biomedical submission QC report"),
        encoding="utf-8",
    )
    pdf_written = write_basic_pdf(packet_dir / "audit-report.pdf", report_text)

    if re_audit_diff is not None:
        write_json(packet_dir / "re_audit_diff.json", re_audit_diff)
        write_re_audit_diff_markdown(packet_dir / "re_audit_diff.md", re_audit_diff)
        copy_if_exists(output_dir / "re_audit_diff.csv", packet_dir / "re_audit_diff.csv")

    image_review_packet = export_image_review_packet(
        output_dir,
        packet_dir,
        audit_summary,
        coverage,
        calibrated,
        snapshot,
    )
    if image_review_packet.get("packet_dir"):
        copied.append("image_review_packet/")

    start_here_lines = [
        "# START HERE",
        "",
        "Read these files in order:",
        "",
        "1. `audit-report.md` or `audit-report.html` — human report with scope, candidate findings, and action queue.",
        "2. `unresolved_actions.csv` — team tracker for required follow-up.",
        "3. `correction_plan.md` — short correction-plan view derived from open actions.",
        "4. `audience_exports/PI_BRIEF.md`, `COAUTHOR_ACTIONS.md`, and `JOURNAL_RESPONSE_DRAFT.md` — editable audience-specific communication drafts.",
        "5. `re_audit_diff.md` if present — human-readable comparison of fixed, new, persisted, and still-missing items.",
        "6. `AUDIT_JSON_SUMMARY.json` — machine-readable summary for re-audit or webapp import.",
        "7. `file_hash_manifest.json` — hashes of the reviewed package files.",
        "8. `docx_structure.json` if present — DOCX paragraph/caption/table structure for claim-manifest preparation; this is not provenance proof.",
        "9. `xlsx_structure.json` if present — XLSX workbook/sheet metadata for source-data and claim-manifest preparation; this is not statistical validation.",
        "10. `prism_project_intake.json` if present — Prism table/graph metadata hints for source-manifest preparation; these are not verified provenance.",
        "11. `fcs_metadata_intake.json` if present — FCS event/channel/instrument metadata hints for flow-material review; these are not gating or compensation validation.",
        "12. `pdf_embedded_images/` if present — presentation-layer images exported from PDFs; these are not raw records.",
        "13. `pptx_structure.json` if present — PPTX slide text, speaker-note, alt-text, and path structure for assembly-manifest preparation; this is not provenance proof.",
        "14. `pptx_embedded_images/` if present — presentation-layer images exported from PPTX assembly files; these are not raw records.",
        "15. `key_embedded_images/` if present — presentation-layer images exported from Keynote assembly files; these are not raw records.",
        "16. `psd_preview_images/` if present — flattened PSD previews for intake review; these are not raw records or layer provenance.",
        "17. `image_review_packet/` if present — candidate image-review target list plus external-tool handoff sheet for ImageTwin/Proofig/manual figure review.",
        "",
        "Boundary: this packet is not a clean-manuscript certificate and does not determine misconduct, intent, or author responsibility.",
        "",
        "中文提示：请先读 `audit-report.md` 或 `audit-report.html`，再用 `unresolved_actions.csv` 跟踪处理项。"
        " 本包不是“论文无问题证明”，也不判断作者意图或责任。",
    ]
    (packet_dir / "START_HERE.md").write_text("\n".join(start_here_lines) + "\n", encoding="utf-8")

    readme_lines = [
        "# Submission QC Packet",
        "",
        "This packet records the supplied audit materials, traceability outputs, unresolved actions, and sign-off template.",
        "It is not a clean-manuscript certificate and does not determine misconduct, intent, or author guilt.",
        "",
        "- Start with `START_HERE.md` for the reading order.",
        "- `audit_snapshot.json` and `file_hash_manifest.json` record the package version reviewed.",
        "- `claim_coverage.*` records claim-to-evidence coverage when a claim manifest was supplied.",
        "- `methodology_checklist.*` records reporting-standard readiness prompts and supporting-material gaps.",
        "- `writing_readiness.*` records writing, reference, and generic submission-file readiness prompts.",
        "- `docx_structure.json`, `pdf_structure.json`, `xlsx_structure.json`, `prism_project_intake.json`, `fcs_metadata_intake.json`, `pdf_embedded_images.*`, `pptx_structure.json`, `pptx_embedded_images.*`, `key_embedded_images.*`, `psd_preview_images.*`, `image_metadata.json`, `channel_metadata_candidates.json`, and `splice_forensics_candidates.json` record document/assembly/source-project/flow/image metadata intake and weak image-forensics triage when relevant files were supplied.",
        "- `image_review_packet/` organizes image candidate targets, evidence metrics, and an external-tool handoff sheet for ImageTwin/Proofig/manual figure review when image files are present.",
        "- `unresolved_actions.csv` collects remaining completeness gaps, findings, and claim-evidence gaps.",
        "- `correction_plan.*` maps unresolved actions into the pre-submission correction-plan tracker.",
        "- `audience_exports/` contains editable PI, co-author, and journal/reviewer response drafts generated from the neutral action queue.",
        "- `re_audit_diff.*` appears when this run was compared with a previous audit and summarizes no-longer-listed, new, still-present, and still-missing items.",
        "- `resolved_actions.csv` and `accepted_with_reason.csv` are empty tracker templates for team follow-up.",
        "- `author_signoff.yaml` is a template for internal responsibility review before submission.",
    ]
    if not pdf_written:
        readme_lines.append("- `audit-report.pdf` was not generated because the PDF runtime was unavailable.")
    (packet_dir / "QC_PACKET_README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")

    return {
        "packet_dir": str(packet_dir),
        "files": sorted(path.name for path in packet_dir.iterdir() if path.is_file()),
        "unresolved_action_count": len(action_rows),
        "claim_manifest_supplied": bool(claim_coverage.get("supplied")),
        "pdf_report_written": pdf_written,
        "copied_artifacts": copied,
        "image_review_packet": image_review_packet,
        "audience_exports": audience_exports,
    }


def risk_counts(summary: dict[str, Any]) -> dict[str, int]:
    counts = {risk: 0 for risk in RISK_ORDER}
    for item in summary.get("findings", []) or []:
        risk = item.get("risk_level")
        if risk in counts:
            counts[risk] += 1
    return counts


def material_label(item: Any) -> str:
    if isinstance(item, dict):
        for key in ("category", "material", "path", "reason"):
            value = str(item.get(key, "")).strip()
            if value:
                return value
        return json.dumps(item, sort_keys=True, ensure_ascii=False)
    return str(item).strip()


def material_changes(previous_summary: dict[str, Any], current_summary: dict[str, Any]) -> dict[str, Any]:
    previous = {label for item in previous_summary.get("materials_missing", []) or [] if (label := material_label(item))}
    current = {label for item in current_summary.get("materials_missing", []) or [] if (label := material_label(item))}
    resolved = sorted(previous - current)
    new = sorted(current - previous)
    persisted = sorted(previous & current)
    return {
        "resolved_count": len(resolved),
        "new_count": len(new),
        "persisted_count": len(persisted),
        "resolved": resolved,
        "new": new,
        "persisted": persisted,
    }


def load_optional_json(path: Path) -> dict[str, Any]:
    return read_json(path) if path.is_file() else {}


def finding_risk(finding: dict[str, Any]) -> str:
    return str(finding.get("calibrated_risk_level") or finding.get("risk_level") or "")


def finding_key(finding: dict[str, Any]) -> str:
    finding_id = str(finding.get("finding_id") or "").strip()
    if finding_id:
        return finding_id
    signature = {
        "finding_type": finding.get("finding_type"),
        "module": finding.get("module"),
        "location": finding.get("location"),
        "evidence_type": finding.get("evidence_type"),
        "source_candidate_tags": finding.get("source_candidate_tags", []),
    }
    digest = hashlib.sha256(json.dumps(signature, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    return f"finding-signature-{digest}"


def finding_summary(key: str, finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "finding_key": key,
        "finding_id": finding.get("finding_id") or key,
        "risk": finding_risk(finding),
        "finding_type": finding.get("finding_type", ""),
        "module": finding.get("module", ""),
        "location": finding.get("location", ""),
        "recommended_action": finding.get("recommended_action", ""),
    }


def finding_map(findings_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    findings = findings_payload.get("findings", []) or []
    return {finding_key(item): item for item in findings}


def build_finding_changes(previous_dir: Path, current_dir: Path) -> dict[str, Any]:
    previous = finding_map(load_optional_json(previous_dir / "calibrated_findings.json"))
    current = finding_map(load_optional_json(current_dir / "calibrated_findings.json"))
    previous_keys = set(previous)
    current_keys = set(current)

    fixed = [
        finding_summary(key, previous[key])
        for key in sorted(previous_keys - current_keys)
    ]
    new = [
        finding_summary(key, current[key])
        for key in sorted(current_keys - previous_keys)
    ]
    persisted = []
    for key in sorted(previous_keys & current_keys):
        persisted.append({
            "finding_key": key,
            "finding_id": current[key].get("finding_id") or previous[key].get("finding_id") or key,
            "finding_type": current[key].get("finding_type") or previous[key].get("finding_type", ""),
            "module": current[key].get("module") or previous[key].get("module", ""),
            "location": current[key].get("location") or previous[key].get("location", ""),
            "previous_risk": finding_risk(previous[key]),
            "current_risk": finding_risk(current[key]),
            "risk_changed": finding_risk(previous[key]) != finding_risk(current[key]),
            "recommended_action": current[key].get("recommended_action", ""),
        })
    return {
        "fixed_count": len(fixed),
        "new_count": len(new),
        "persisted_count": len(persisted),
        "fixed": fixed,
        "new": new,
        "persisted": persisted,
    }


def build_re_audit_diff(previous_dir: Path, current_dir: Path) -> dict[str, Any]:
    previous_summary = load_optional_json(previous_dir / "AUDIT_JSON_SUMMARY.json")
    current_summary = load_optional_json(current_dir / "AUDIT_JSON_SUMMARY.json")
    previous_claims = load_optional_json(previous_dir / "claim_coverage.json")
    current_claims = load_optional_json(current_dir / "claim_coverage.json")
    previous_actions = list(csv.DictReader((previous_dir / "unresolved_actions.csv").open(encoding="utf-8"))) if (previous_dir / "unresolved_actions.csv").is_file() else []
    current_actions = list(csv.DictReader((current_dir / "unresolved_actions.csv").open(encoding="utf-8"))) if (current_dir / "unresolved_actions.csv").is_file() else []
    finding_changes = build_finding_changes(previous_dir, current_dir)
    missing_material_changes = material_changes(previous_summary, current_summary)
    return {
        "schema_version": "0.1.0",
        "previous_dir": str(previous_dir),
        "current_dir": str(current_dir),
        "scope_note": (
            "A re-audit diff shows which calibrated findings appear fixed, new, or still present "
            "between two audit outputs; it is not a pass/fail decision."
        ),
        "overall_risk": {
            "previous": previous_summary.get("overall_risk"),
            "current": current_summary.get("overall_risk"),
        },
        "risk_counts": {
            "previous": risk_counts(previous_summary),
            "current": risk_counts(current_summary),
        },
        "missing_material_count": {
            "previous": len(previous_summary.get("materials_missing", []) or []),
            "current": len(current_summary.get("materials_missing", []) or []),
        },
        "positive_provenance_count": {
            "previous": len(previous_summary.get("positive_provenance", []) or []),
            "current": len(current_summary.get("positive_provenance", []) or []),
        },
        "unresolved_action_count": {
            "previous": len(previous_actions),
            "current": len(current_actions),
        },
        "claim_evidence_gaps": {
            "previous": previous_claims.get("claims_with_unresolved_evidence_gap"),
            "current": current_claims.get("claims_with_unresolved_evidence_gap"),
        },
        "material_changes": missing_material_changes,
        "finding_changes": finding_changes,
    }


def markdown_table_row(values: list[Any]) -> str:
    return "| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in values) + " |"


def finding_change_lines(items: list[dict[str, Any]], persisted: bool = False) -> list[str]:
    if not items:
        return ["- None listed."]
    lines = []
    for item in items[:20]:
        if persisted:
            risk = f"{item.get('previous_risk', '')} -> {item.get('current_risk', '')}"
        else:
            risk = str(item.get("risk", ""))
        lines.append(
            f"- `{item.get('finding_id', '')}` ({risk}) {item.get('finding_type', '')} at "
            f"`{item.get('location', '')}`."
        )
    if len(items) > 20:
        lines.append(f"- ... {len(items) - 20} more in `re_audit_diff.json`.")
    return lines


def material_change_lines(items: list[str]) -> list[str]:
    if not items:
        return ["- None listed."]
    lines = [f"- {item}" for item in items[:20]]
    if len(items) > 20:
        lines.append(f"- ... {len(items) - 20} more in `re_audit_diff.json`.")
    return lines


def write_re_audit_diff_markdown(path: Path, diff: dict[str, Any]) -> None:
    finding_changes = diff.get("finding_changes", {}) or {}
    material_diff = diff.get("material_changes", {}) or {}
    lines = [
        "# Re-audit Diff / 复审差异",
        "",
        "> This compares two audit output directories. It shows what no longer appears, what is new, and what still needs review. It is not a pass/fail decision.",
        "> 本文件比较两次审计输出，用于查看哪些不再出现、哪些新增、哪些仍需复核；它不是通过/不通过结论。",
        "",
        "## At A Glance",
        "",
        "| Metric | Previous | Current |",
        "| --- | ---: | ---: |",
        markdown_table_row(["Overall risk", diff.get("overall_risk", {}).get("previous", ""), diff.get("overall_risk", {}).get("current", "")]),
        markdown_table_row(["Unresolved actions", diff.get("unresolved_action_count", {}).get("previous", ""), diff.get("unresolved_action_count", {}).get("current", "")]),
        markdown_table_row(["Missing material categories", diff.get("missing_material_count", {}).get("previous", ""), diff.get("missing_material_count", {}).get("current", "")]),
        markdown_table_row(["Positive provenance links", diff.get("positive_provenance_count", {}).get("previous", ""), diff.get("positive_provenance_count", {}).get("current", "")]),
        markdown_table_row(["Claim-evidence gaps", diff.get("claim_evidence_gaps", {}).get("previous", ""), diff.get("claim_evidence_gaps", {}).get("current", "")]),
        "",
        "## Finding Movement",
        "",
        "| Category | Count |",
        "| --- | ---: |",
        markdown_table_row(["No longer listed / 不再出现", finding_changes.get("fixed_count", 0)]),
        markdown_table_row(["New / 新增", finding_changes.get("new_count", 0)]),
        markdown_table_row(["Still present / 仍存在", finding_changes.get("persisted_count", 0)]),
        "",
        "### No Longer Listed / 不再出现",
        "",
        *finding_change_lines(finding_changes.get("fixed", []) or []),
        "",
        "### New / 新增",
        "",
        *finding_change_lines(finding_changes.get("new", []) or []),
        "",
        "### Still Present / 仍存在",
        "",
        *finding_change_lines(finding_changes.get("persisted", []) or [], persisted=True),
        "",
        "## Missing Materials Movement / 缺失材料变化",
        "",
        "| Category | Count |",
        "| --- | ---: |",
        markdown_table_row(["Resolved / 已补齐或不再缺失", material_diff.get("resolved_count", 0)]),
        markdown_table_row(["New / 新增缺口", material_diff.get("new_count", 0)]),
        markdown_table_row(["Still missing / 仍缺失", material_diff.get("persisted_count", 0)]),
        "",
        "### Resolved / 已补齐或不再缺失",
        "",
        *material_change_lines(material_diff.get("resolved", []) or []),
        "",
        "### New / 新增缺口",
        "",
        *material_change_lines(material_diff.get("new", []) or []),
        "",
        "### Still Missing / 仍缺失",
        "",
        *material_change_lines(material_diff.get("persisted", []) or []),
        "",
        "## Next Step",
        "",
        "Use this diff with `unresolved_actions.csv` and `correction_plan.md`: assign owners for new and persisted items, attach source/raw records for still-missing materials, and rerun the audit after remediation.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_re_audit_diff_csv(path: Path, diff: dict[str, Any]) -> None:
    rows = [
        ("overall_risk", diff["overall_risk"].get("previous"), diff["overall_risk"].get("current")),
        (
            "missing_material_count",
            diff["missing_material_count"].get("previous"),
            diff["missing_material_count"].get("current"),
        ),
        (
            "positive_provenance_count",
            diff["positive_provenance_count"].get("previous"),
            diff["positive_provenance_count"].get("current"),
        ),
        (
            "unresolved_action_count",
            diff["unresolved_action_count"].get("previous"),
            diff["unresolved_action_count"].get("current"),
        ),
        (
            "claim_evidence_gaps",
            diff["claim_evidence_gaps"].get("previous"),
            diff["claim_evidence_gaps"].get("current"),
        ),
    ]
    for risk in RISK_ORDER:
        rows.append((
            f"finding_count_{risk}",
            diff["risk_counts"]["previous"].get(risk, 0),
            diff["risk_counts"]["current"].get(risk, 0),
        ))
    finding_changes = diff.get("finding_changes", {})
    rows.extend([
        ("findings_fixed", finding_changes.get("fixed_count", 0), ""),
        ("findings_new", "", finding_changes.get("new_count", 0)),
        ("findings_persisted", finding_changes.get("persisted_count", 0), finding_changes.get("persisted_count", 0)),
    ])
    material_diff = diff.get("material_changes", {})
    rows.extend([
        ("materials_resolved", material_diff.get("resolved_count", 0), ""),
        ("materials_new", "", material_diff.get("new_count", 0)),
        ("materials_still_missing", material_diff.get("persisted_count", 0), material_diff.get("persisted_count", 0)),
    ])
    for item in finding_changes.get("fixed", []) or []:
        rows.append((f"fixed:{item.get('finding_id')}", item.get("risk"), ""))
    for item in finding_changes.get("new", []) or []:
        rows.append((f"new:{item.get('finding_id')}", "", item.get("risk")))
    for item in finding_changes.get("persisted", []) or []:
        rows.append((
            f"persisted:{item.get('finding_id')}",
            item.get("previous_risk"),
            item.get("current_risk"),
        ))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "previous", "current"])
        writer.writerows([csv_safe_cell(cell) for cell in row] for row in rows)
