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
import textwrap
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
    "location",
    "required_action",
    "owner",
    "status",
    "human_note",
    "accepted_with_reason",
    "source",
]

CORRECTION_PLAN_FIELDNAMES = [
    "finding_id",
    "risk",
    "required_correction",
    "owner",
    "evidence_after_correction",
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

    def append(action_type: str, risk_level: str, location: str, action: str, source: str) -> None:
        category = category_for(action_type, risk_level, location, action)
        rows.append({
            "action_id": f"ACT-{len(rows) + 1:04d}",
            "action_category": category,
            "risk_level": risk_level,
            "action_type": action_type,
            "location": location,
            "required_action": action,
            "owner": owner_for(action_type, location, action),
            "status": "unresolved",
            "human_note": "",
            "accepted_with_reason": "",
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
        "| Finding ID | Risk | Required correction | Owner | Evidence after correction | Status |",
        "| --- | --- | --- | --- | --- | --- |",
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
                    markdown_cell(row.get("status", "")),
                ])
                + " |"
            )
    else:
        lines.append("|  |  | No unresolved correction currently listed within this audit scope. |  |  |  |")
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


def markdown_to_basic_html(markdown_text: str, title: str) -> str:
    body_lines = []
    in_code = False
    for raw in markdown_text.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            body_lines.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        escaped = html.escape(line)
        if in_code:
            body_lines.append(escaped)
        elif line.startswith("# "):
            body_lines.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            body_lines.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            body_lines.append(f"<h3>{html.escape(line[4:].strip())}</h3>")
        elif line.startswith("- "):
            body_lines.append(f"<p>&bull; {html.escape(line[2:].strip())}</p>")
        elif line.startswith("> "):
            body_lines.append(f"<blockquote>{html.escape(line[2:].strip())}</blockquote>")
        elif line:
            body_lines.append(f"<p>{escaped}</p>")
        else:
            body_lines.append("")
    return "\n".join([
        "<!doctype html>",
        "<html lang=\"en\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        f"<title>{html.escape(title)}</title>",
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:980px;margin:40px auto;line-height:1.55;color:#1f2937}pre{white-space:pre-wrap;background:#f8fafc;padding:16px;border:1px solid #e5e7eb}blockquote{border-left:4px solid #0f766e;padding-left:12px;color:#475569}table{border-collapse:collapse}td,th{border:1px solid #e5e7eb;padding:4px 8px}</style>",
        "</head>",
        "<body>",
        *body_lines,
        "</body>",
        "</html>",
    ])


def write_basic_pdf(path: Path, text: str) -> bool:
    try:
        import fitz  # type: ignore
    except Exception:
        return False
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50
    for paragraph in text.splitlines():
        lines = textwrap.wrap(paragraph, width=92) or [""]
        for line in lines:
            if y > 800:
                page = doc.new_page(width=595, height=842)
                y = 50
            page.insert_text((50, y), line, fontsize=9)
            y += 12
    doc.save(path)
    doc.close()
    return True


def copy_if_exists(source: Path, target: Path) -> bool:
    if not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


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
    packet_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for name in ("audit-report.md", "AUDIT_JSON_SUMMARY.json", "coverage.json", "calibrated_findings.json"):
        if copy_if_exists(output_dir / name, packet_dir / name):
            copied.append(name)

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

    readme_lines = [
        "# Submission QC Packet",
        "",
        "This packet records the supplied audit materials, traceability outputs, unresolved actions, and sign-off template.",
        "It is not a clean-manuscript certificate and does not determine misconduct, intent, or author guilt.",
        "",
        "- `audit_snapshot.json` and `file_hash_manifest.json` record the package version reviewed.",
        "- `claim_coverage.*` records claim-to-evidence coverage when a claim manifest was supplied.",
        "- `methodology_checklist.*` records reporting-standard readiness prompts and supporting-material gaps.",
        "- `writing_readiness.*` records writing, reference, and generic submission-file readiness prompts.",
        "- `unresolved_actions.csv` collects remaining completeness gaps, findings, and claim-evidence gaps.",
        "- `correction_plan.*` maps unresolved actions into the pre-submission correction-plan tracker.",
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
    }


def risk_counts(summary: dict[str, Any]) -> dict[str, int]:
    counts = {risk: 0 for risk in RISK_ORDER}
    for item in summary.get("findings", []) or []:
        risk = item.get("risk_level")
        if risk in counts:
            counts[risk] += 1
    return counts


def load_optional_json(path: Path) -> dict[str, Any]:
    return read_json(path) if path.is_file() else {}


def build_re_audit_diff(previous_dir: Path, current_dir: Path) -> dict[str, Any]:
    previous_summary = load_optional_json(previous_dir / "AUDIT_JSON_SUMMARY.json")
    current_summary = load_optional_json(current_dir / "AUDIT_JSON_SUMMARY.json")
    previous_claims = load_optional_json(previous_dir / "claim_coverage.json")
    current_claims = load_optional_json(current_dir / "claim_coverage.json")
    previous_actions = list(csv.DictReader((previous_dir / "unresolved_actions.csv").open(encoding="utf-8"))) if (previous_dir / "unresolved_actions.csv").is_file() else []
    current_actions = list(csv.DictReader((current_dir / "unresolved_actions.csv").open(encoding="utf-8"))) if (current_dir / "unresolved_actions.csv").is_file() else []
    return {
        "schema_version": "0.1.0",
        "previous_dir": str(previous_dir),
        "current_dir": str(current_dir),
        "scope_note": "A re-audit diff shows changes between two audit outputs; it is not a pass/fail decision.",
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
    }


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
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "previous", "current"])
        writer.writerows([csv_safe_cell(cell) for cell in row] for row in rows)
