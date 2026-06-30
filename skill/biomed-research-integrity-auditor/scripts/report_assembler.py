#!/usr/bin/env python3
"""Assemble a Markdown biomedical integrity audit report from JSON artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from calibrators.contract_validation import ContractError, validate_instance  # noqa: E402


SUMMARY_SCHEMA = ROOT / "schemas" / "audit_summary.schema.json"
CALIBRATED_SCHEMA = ROOT / "schemas" / "calibrated_findings.schema.json"
RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}


def humanize(value: str) -> str:
    return str(value).replace("_", " ").replace("-", " ").strip()


def load_json(path: Path | None, default: Any) -> Any:
    if path is None:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def coerce_finding(item: dict[str, Any], idx: int) -> dict[str, Any]:
    if "calibrated_risk_level" not in item:
        raise ContractError(
            f"finding {item.get('finding_id', idx)!r} is not calibrated; "
            "report_assembler only accepts calibrator output with calibrated_risk_level"
        )
    result = dict(item)
    result.setdefault("finding_id", f"BIOMED-GEN-{idx:04d}")
    result["risk_level"] = result["calibrated_risk_level"]
    result.setdefault("module", "Structured Finding")
    result.setdefault("location", "")
    result.setdefault("finding_type", result.get("type", "Structured audit finding"))
    result.setdefault("evidence_type", humanize(result.get("module", "structured_finding")).lower())
    result.setdefault("evidence", "")
    if RISK_ORDER.get(result.get("risk_level", "R0"), 0) >= RISK_ORDER["R3"]:
        result.setdefault("benign_explanations_considered", [
            "rounding, normalization, export, or reporting differences may explain the observation",
            "source/raw records are needed before escalation",
        ])
        result.setdefault("required_materials_to_resolve", [
            "source data",
            "raw records",
            "analysis file or code",
        ])
        result.setdefault("recommended_action", "Verify against source/raw records and analysis files before escalation.")
    else:
        result.setdefault("benign_explanations_considered", [])
        result.setdefault("required_materials_to_resolve", [])
        result.setdefault("recommended_action", "")
    return result


def normalize_findings(payloads: list[Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for payload in payloads:
        if isinstance(payload, list):
            findings.extend(coerce_finding(item, idx) for idx, item in enumerate(payload, start=1))
        elif isinstance(payload, dict):
            if isinstance(payload.get("findings"), list):
                if "candidate_count" in payload:
                    validate_instance(payload, CALIBRATED_SCHEMA, "calibrated findings")
                findings.extend(coerce_finding(item, idx) for idx, item in enumerate(payload["findings"], start=1))
            elif isinstance(payload.get("candidates"), list):
                raise ContractError("report_assembler received uncalibrated detector candidates")
            elif payload.get("missing_materials"):
                raise ContractError("report_assembler received manifest/missing materials as findings input")
    return findings


def normalize_positive_evidence(payloads: list[Any]) -> list[dict[str, Any]]:
    positive = []
    for payload in payloads:
        if isinstance(payload, dict):
            positive.extend(payload.get("positive_evidence", []) or [])
    return positive


def table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join("---" for _ in rows[0]) + " |"
    body = ["| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |" for row in rows[1:]]
    return "\n".join([header, sep, *body]) + "\n"


def normalized_mode(mode: str) -> str:
    if mode == "internal":
        return "internal_presubmission"
    if mode == "external":
        return "external_public_material"
    return mode


def overall_risk(findings: list[dict[str, Any]], manifest: dict[str, Any]) -> str:
    risks = [item.get("risk_level", "R0") for item in findings]
    if manifest.get("missing_materials"):
        risks.append("R1")
    return max(risks or ["R0"], key=lambda risk: RISK_ORDER.get(risk, -1))


def reviewed_materials(manifest: dict[str, Any]) -> list[str]:
    return [item.get("path", "") for item in manifest.get("files", []) if item.get("path")]


def missing_materials(manifest: dict[str, Any]) -> list[str]:
    return [humanize(item.get("category", "")) for item in manifest.get("missing_materials", []) if item.get("category")]


def summary_finding(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "finding_id": item.get("finding_id", ""),
        "risk_level": item.get("risk_level", "R0"),
        "finding_type": item.get("finding_type", ""),
        "location": item.get("location", ""),
        "evidence_type": item.get("evidence_type", item.get("module", "")),
        "benign_explanations_considered": item.get("benign_explanations_considered", []),
        "required_materials_to_resolve": item.get("required_materials_to_resolve", []),
        "recommended_action": item.get("recommended_action", ""),
    }


def summary_positive_provenance(positive_evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in positive_evidence:
        for edge in item.get("edges", []) or []:
            left = str(edge.get("left", ""))
            right = str(edge.get("right", ""))
            left_role = str(edge.get("left_role", ""))
            right_role = str(edge.get("right_role", ""))
            if left_role == "figure_panel":
                figure_panel, source_record = left, right
            elif right_role == "figure_panel":
                figure_panel, source_record = right, left
            else:
                figure_panel, source_record = left, right

            provenance_edge = edge.get("provenance_edge") or {}
            evidence_source = str(
                provenance_edge.get("evidence_source")
                or edge.get("evidence_source")
                or "provenance graph"
            )
            key = (figure_panel, source_record, evidence_source)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "provenance_id": f"PROV-{len(rows) + 1:04d}",
                "relation_type": str(edge.get("contextual_tag") or "expected_traceability"),
                "figure_panel": figure_panel,
                "source_record": source_record,
                "evidence_source": evidence_source,
                "risk_effect": "positive_evidence",
            })
    return rows


def summary_traceability_gaps(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for item in findings:
        tags = set(str(tag) for tag in item.get("source_candidate_tags", []) or [])
        finding_type = str(item.get("finding_type", ""))
        evidence_type = str(item.get("evidence_type", ""))
        if "unresolved_fig_raw_similarity" not in tags | {finding_type, evidence_type}:
            continue
        gaps.append({
            "gap_id": f"TRACE-{len(gaps) + 1:04d}",
            "finding_type": finding_type or evidence_type,
            "risk_level": item.get("risk_level", "R1"),
            "location": item.get("location", ""),
            "required_materials_to_resolve": item.get("required_materials_to_resolve", []),
        })
    return gaps


def build_summary(
    mode: str,
    case_id: str | None,
    manifest: dict[str, Any],
    findings: list[dict[str, Any]],
    positive_evidence: list[dict[str, Any]] | None = None,
    coverage: dict[str, Any] | None = None,
    claim_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    caps = []
    normalized = normalized_mode(mode)
    if normalized == "external_public_material" and not any(path.lower().endswith((".csv", ".xlsx", ".tif", ".tiff", ".czi", ".nd2", ".fcs")) for path in reviewed_materials(manifest)):
        caps.append("Public or presentation-layer materials only; source/raw-level verification is limited.")
    if manifest.get("missing_materials"):
        caps.append("Missing materials are completeness gaps, not evidence of misconduct.")
    for item in findings:
        caps.extend(item.get("risk_caps_applied", []) or [])
    return {
        "audit_mode": normalized,
        "case_id": case_id,
        "materials_reviewed": reviewed_materials(manifest),
        "materials_missing": missing_materials(manifest),
        "overall_risk": overall_risk(findings, manifest),
        "misconduct_verdict_present": False,
        "risk_caps_applied": sorted(set(caps)),
        "positive_provenance": summary_positive_provenance(positive_evidence or []),
        "traceability_gaps": summary_traceability_gaps(findings),
        "findings": [summary_finding(item) for item in findings],
        **({"audit_coverage": coverage} if coverage else {}),
        **({"claim_coverage": claim_coverage} if claim_coverage else {}),
    }


def render_coverage(coverage: dict[str, Any] | None) -> list[str]:
    if not coverage:
        return []
    lines = ["## Audit Coverage", ""]
    lines += ["Modules executed in this run:", ""]
    executed = coverage.get("modules_executed", []) or ["(none)"]
    lines += [f"- {item}" for item in executed]
    lines += ["", "Modules not executed in this run:", ""]
    not_executed = coverage.get("modules_not_executed", []) or ["(none)"]
    lines += [f"- {item}" for item in not_executed]
    lines += [""]
    lines += [f"- Image panels screened: {coverage.get('image_panels_screened', 0)}"]
    if coverage.get("image_files_unreadable"):
        lines += [f"- Image files that could not be read and were excluded from screening: {coverage['image_files_unreadable']}"]
    lines += [f"- Source-data tables screened: {coverage.get('source_tables_screened', 0)}"]
    if coverage.get("detector_failures"):
        lines += [f"- Detector execution failures (results partial for these modules): {', '.join(coverage['detector_failures'])}"]
    if coverage.get("audit_coverage_gap"):
        lines += ["- No detector could run on the supplied materials; this is a completeness gap, not a clean result."]
    scope_note = coverage.get("scope_note")
    if scope_note:
        lines += ["", f"> {scope_note}"]
    lines += [""]
    return lines


def render_claim_coverage(claim_coverage: dict[str, Any] | None) -> list[str]:
    if not claim_coverage:
        return []
    lines = ["## Claim Coverage", ""]
    if not claim_coverage.get("supplied"):
        lines += [
            "No `claim_manifest.csv` was supplied for this audit run.",
            "",
            "> Claim coverage is a claim-to-evidence completeness check, not a correctness verdict.",
            "",
        ]
        return lines
    lines += [table([
        ["Metric", "Count"],
        ["Claims declared", str(claim_coverage.get("claims_declared", 0))],
        ["Claims with source data", str(claim_coverage.get("claims_with_source_data", 0))],
        ["Claims with raw records", str(claim_coverage.get("claims_with_raw_records", 0))],
        ["Claims with analysis code", str(claim_coverage.get("claims_with_analysis_code", 0))],
        ["Claims with protocol link", str(claim_coverage.get("claims_with_protocol_link", 0))],
        ["Claims with unresolved evidence gap", str(claim_coverage.get("claims_with_unresolved_evidence_gap", 0))],
    ])]
    if claim_coverage.get("unresolved_claims"):
        lines += ["Unresolved claim-to-evidence gaps:", ""]
        for item in claim_coverage.get("unresolved_claims", []):
            reasons = ", ".join(item.get("gap_reasons", []) or ["not documented"])
            lines.append(f"- {item.get('claim_id', '')}: {reasons}")
        lines.append("")
    scope_note = claim_coverage.get("scope_note")
    if scope_note:
        lines += [f"> {scope_note}", ""]
    return lines


def render_report(
    mode: str,
    manifest: dict[str, Any],
    findings: list[dict[str, Any]],
    case_id: str | None,
    positive_evidence: list[dict[str, Any]] | None = None,
    coverage: dict[str, Any] | None = None,
    claim_coverage: dict[str, Any] | None = None,
) -> str:
    normalized = normalized_mode(mode)
    title = "Biomedical Research Integrity Pre-submission Audit" if normalized == "internal_presubmission" else "Biomedical Literature Concern Triage"
    positive_evidence = positive_evidence or []
    summary = build_summary(mode, case_id, manifest, findings, positive_evidence, coverage, claim_coverage)
    validate_instance(summary, SUMMARY_SCHEMA, "audit summary")
    lines = [f"# {title}", ""]
    lines += ["## Scope", ""]
    lines += [f"- Mode: {mode}", f"- Package root: {manifest.get('root', 'not supplied')}", ""]
    lines += render_coverage(coverage)
    lines += render_claim_coverage(claim_coverage)

    lines += ["## Missing Materials Matrix", ""]
    missing_rows = [["Category", "Risk", "Reason"]]
    for item in manifest.get("missing_materials", []):
        missing_rows.append([item.get("category", ""), item.get("risk_level", "R1"), item.get("reason", "")])
    lines += [table(missing_rows) if len(missing_rows) > 1 else "No missing expected material categories were reported.\n"]

    if positive_evidence:
        lines += ["## Verified Traceability Evidence", ""]
        for item in positive_evidence:
            for edge in item.get("edges", []):
                lines.append(
                    "- "
                    f"{edge.get('left', '')} is traceable to {edge.get('right', '')} "
                    f"via {edge.get('provenance_edge', {}).get('evidence_source', 'provenance graph')}."
                )
        lines += [
            "",
            "These links are positive provenance evidence, not image-reuse concerns.",
            "",
        ]

    lines += ["## Risk Register", ""]
    risk_rows = [["Finding ID", "Risk", "Module", "Location", "Finding"]]
    for item in findings:
        risk_rows.append([
            item.get("finding_id", ""),
            item.get("risk_level", ""),
            item.get("module", ""),
            item.get("location", ""),
            item.get("finding_type", ""),
        ])
    lines += [table(risk_rows) if len(risk_rows) > 1 else "No structured findings supplied.\n"]

    lines += ["## Evidence Ledger", ""]
    for item in findings:
        lines += [
            f"### {item.get('finding_id', 'UNNUMBERED')}",
            "",
            f"- Risk Level: {item.get('risk_level', '')}",
            f"- Module: {item.get('module', '')}",
            f"- Location: {item.get('location', '')}",
            f"- Finding Type: {item.get('finding_type', '')}",
            f"- Evidence: `{json.dumps(item.get('evidence', ''), ensure_ascii=False)}`",
            f"- Benign explanations considered: {', '.join(item.get('benign_explanations_considered', [])) or 'not documented'}",
            f"- Required materials to resolve: {', '.join(item.get('required_materials_to_resolve', [])) or 'not documented'}",
            f"- Recommended action: {item.get('recommended_action', 'Verify against source records before escalating.')}",
            f"- Note: {item.get('note', 'Automated or structured finding; verify against raw/source records.')}",
            "",
        ]

    lines += [
        "## Boundary",
        "",
        "This report identifies research-integrity risks and completeness gaps. It does not determine misconduct, intent, or author guilt.",
        "",
        "## Audit JSON Summary",
        "",
        "```json AUDIT_JSON_SUMMARY",
        json.dumps(summary, indent=2, ensure_ascii=False),
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["internal", "external", "internal_presubmission", "external_public_material", "response_to_concern"],
        default="internal_presubmission",
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--findings", type=Path, action="append", default=[])
    parser.add_argument("--positive-evidence", type=Path, action="append", default=[])
    parser.add_argument("--coverage", type=Path)
    parser.add_argument("--claim-coverage", type=Path)
    parser.add_argument("--case-id")
    parser.add_argument("--output", type=Path, default=Path("audit-report.md"))
    args = parser.parse_args()

    manifest = load_json(args.manifest, {})
    finding_payloads = [load_json(path, {}) for path in args.findings]
    positive_payloads = [load_json(path, {}) for path in args.positive_evidence]
    findings = normalize_findings(finding_payloads)
    positive_evidence = normalize_positive_evidence(positive_payloads)
    coverage = load_json(args.coverage, None) if args.coverage else None
    claim_coverage = load_json(args.claim_coverage, None) if args.claim_coverage else None
    args.output.write_text(
        render_report(args.mode, manifest, findings, args.case_id, positive_evidence, coverage, claim_coverage),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), "findings": len(findings)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
