"""Calibration and report assembly helpers for the audit pipeline."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from calibrators.contract_validation import ContractError, validate_instance
from scripts.pipeline.common import (
    CALIBRATED_SCHEMA,
    PYTHON,
    ROOT,
    SUMMARY_SCHEMA,
    command_display,
    read_json,
    run,
    write_json,
)


def write_empty_calibrated(mode: str, output: Path) -> None:
    payload = {
        "mode": mode,
        "findings": [],
        "candidate_count": 0,
        "rules": str(ROOT / "schemas" / "risk_rules.yaml"),
    }
    validate_instance(payload, CALIBRATED_SCHEMA, "empty calibrated findings")
    write_json(output, payload)


def write_calibration_failure(
    mode: str,
    output: Path,
    detector_outputs: list[Path],
    cmd: list[str],
    reason: str,
) -> None:
    payload = {
        "mode": mode,
        "candidate_count": sum(len(read_json(path).get("candidates", []) or []) for path in detector_outputs if path.exists()),
        "findings": [
            {
                "finding_id": "PIPELINE-CALIBRATION-0001",
                "calibrated_risk_level": "R1",
                "module": "pipeline",
                "location": "risk calibration",
                "finding_type": "calibration_execution_failure",
                "evidence_type": "audit_coverage_gap",
                "evidence": {
                    "message": "Risk calibration did not complete; detector outputs are preserved but the audit report is partial.",
                    "command": command_display(cmd),
                    "reason": reason,
                    "detector_outputs": [str(path) for path in detector_outputs],
                },
                "evidence_strength": "weak_signal",
                "benign_explanations_considered": [
                    "the pipeline or configuration may have failed independently of the research materials",
                    "detector outputs may still be reviewable manually",
                ],
                "required_materials_to_resolve": [
                    "calibrator error logs",
                    "manual review of preserved detector outputs",
                ],
                "recommended_action": "Resolve the calibration error and re-run before treating this audit as complete.",
                "risk_caps_applied": ["calibration_execution_failure:R1", "audit_coverage_gap:R1"],
                "calibration_reason": "Fallback R1 because risk calibration failed after detector execution.",
            }
        ],
        "rules": str(ROOT / "schemas" / "risk_rules.yaml"),
    }
    validate_instance(payload, CALIBRATED_SCHEMA, "calibration failure findings")
    write_json(output, payload)


def run_calibrator(detector_outputs: list[Path], mode: str, output_dir: Path) -> Path:
    calibrated = output_dir / "calibrated_findings.json"
    if not detector_outputs:
        write_empty_calibrated(mode, calibrated)
        return calibrated

    cmd = [
        PYTHON,
        "calibrators/risk_cap_engine.py",
        "--mode",
        mode,
        "--rules",
        str(ROOT / "schemas" / "risk_rules.yaml"),
        "--output",
        str(calibrated),
    ]
    for path in detector_outputs:
        cmd.extend(["--input", str(path)])
    try:
        run(cmd)
    except subprocess.CalledProcessError as exc:
        write_calibration_failure(mode, calibrated, detector_outputs, cmd, str(exc))
        return calibrated
    validate_instance(read_json(calibrated), CALIBRATED_SCHEMA, "calibrated findings")
    return calibrated


def fallback_audit_summary(
    manifest: Path,
    calibrated: Path,
    mode: str,
    case_id: str | None,
    scan_profile: str,
    reason: str,
) -> dict[str, Any]:
    manifest_payload = read_json(manifest)
    calibrated_payload = read_json(calibrated)
    files = [str(item.get("path", "")) for item in manifest_payload.get("files", []) or [] if item.get("path")]
    findings = []
    for item in calibrated_payload.get("findings", []) or []:
        findings.append({
            "finding_id": str(item.get("finding_id", "PIPELINE-REPORT-0001")),
            "risk_level": str(item.get("calibrated_risk_level", "R1")),
            "finding_type": str(item.get("finding_type", "report_generation_failure")),
            "location": str(item.get("location", "report generation")),
            "evidence_type": str(item.get("evidence_type", "audit_coverage_gap")),
            "benign_explanations_considered": list(item.get("benign_explanations_considered", []) or [
                "the reporting layer may have failed independently of the research materials",
            ]),
            "required_materials_to_resolve": list(item.get("required_materials_to_resolve", []) or [
                "report generation logs",
                "manual review of calibrated findings",
            ]),
            "recommended_action": str(item.get("recommended_action", "Re-run after resolving the reporting error.")),
        })
    if not findings:
        findings.append({
            "finding_id": "PIPELINE-REPORT-0001",
            "risk_level": "R1",
            "finding_type": "report_generation_failure",
            "location": "report generation",
            "evidence_type": "audit_coverage_gap",
            "benign_explanations_considered": [
                "the reporting layer may have failed independently of the research materials",
            ],
            "required_materials_to_resolve": [
                "report generation logs",
                "manual review of preserved detector outputs and calibrated findings",
            ],
            "recommended_action": "Resolve the report generation error and re-run before treating this audit as complete.",
        })
    risk_order = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}
    overall = max((item["risk_level"] for item in findings), key=lambda risk: risk_order.get(risk, 0), default="R1")
    summary = {
        "audit_mode": mode,
        "case_id": case_id,
        "scan_profile": scan_profile,
        "materials_reviewed": files,
        "materials_missing": ["complete human report assembly"],
        "overall_risk": overall,
        "misconduct_verdict_present": False,
        "risk_caps_applied": ["report_generation_failure:R1"],
        "positive_provenance": [],
        "traceability_gaps": [],
        "findings": findings,
        "action_queue": {
            "categories": {
                "must_resolve": [],
                "provide_materials": [],
                "clarify_or_disclose": [],
                "low_priority_checks": [
                    {
                        "action_id": "PIPELINE-REPORT-0001",
                        "action_category": "low_priority_checks",
                        "risk_level": "R1",
                        "action_type": "pipeline_follow_up",
                        "location": "report generation",
                        "required_action": "Resolve the report assembly failure and re-run the audit.",
                        "owner": "suggested_owner",
                        "status": "unresolved",
                        "human_note": "",
                        "accepted_with_reason": "",
                        "attachment_reference": "",
                        "source": "pipeline_fallback",
                    }
                ],
            },
            "counts": {
                "must_resolve": 0,
                "provide_materials": 0,
                "clarify_or_disclose": 0,
                "low_priority_checks": 1,
            },
            "tracker_fields": ["owner", "status", "human_note", "accepted_with_reason", "attachment_reference"],
            "status_options": ["unresolved", "resolved", "accepted_with_reason", "false_positive"],
        },
        "pipeline_error": {
            "stage": "report_generation",
            "reason": reason,
        },
    }
    validate_instance(summary, SUMMARY_SCHEMA, "fallback audit summary")
    return summary


def write_fallback_report(
    report: Path,
    summary: dict[str, Any],
    reason: str,
) -> Path:
    lines = [
        "# Biomedical Research Integrity Audit Report",
        "",
        "## Quick Read / 快速阅读",
        "",
        "- Report assembly did not complete; this fallback report preserves the audit boundary and machine-readable summary.",
        "- 报告组装未完成；此 fallback 报告只保留审计边界和机器可读摘要。",
        "- Do not treat this run as complete until the reporting error is resolved and the audit is re-run.",
        "- 在修复报告错误并重跑前，不要把本次输出当作完整审计。",
        "",
        "## Pipeline Error / 流水线错误",
        "",
        f"`{reason}`",
        "",
        "```json AUDIT_JSON_SUMMARY",
        json.dumps(summary, indent=2, ensure_ascii=False),
        "```",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def run_report(
    manifest: Path,
    calibrated: Path,
    positive_sources: list[Path],
    mode: str,
    case_id: str | None,
    output_dir: Path,
    coverage: Path | None = None,
    claim_coverage: Path | None = None,
    methodology_checklist: Path | None = None,
    writing_readiness: Path | None = None,
    scan_profile: str = "standard",
) -> Path:
    report = output_dir / "audit-report.md"
    cmd = [
        PYTHON,
        "skill/biomed-research-integrity-auditor/scripts/report_assembler.py",
        "--mode",
        mode,
        "--manifest",
        str(manifest),
        "--findings",
        str(calibrated),
        "--output",
        str(report),
    ]
    for path in positive_sources:
        cmd.extend(["--positive-evidence", str(path)])
    if coverage is not None:
        cmd.extend(["--coverage", str(coverage)])
    if claim_coverage is not None:
        cmd.extend(["--claim-coverage", str(claim_coverage)])
    if methodology_checklist is not None:
        cmd.extend(["--methodology-checklist", str(methodology_checklist)])
    if writing_readiness is not None:
        cmd.extend(["--writing-readiness", str(writing_readiness)])
    cmd.extend(["--scan-profile", scan_profile])
    if case_id:
        cmd.extend(["--case-id", case_id])
    try:
        run(cmd)
    except subprocess.CalledProcessError as exc:
        summary = fallback_audit_summary(manifest, calibrated, mode, case_id, scan_profile, str(exc))
        write_fallback_report(report, summary, str(exc))
    return report


def write_start_here(output_dir: Path, package: Path, qc_packet: dict[str, Any], summary: dict[str, Any]) -> Path:
    packet_dir = Path(str(qc_packet.get("packet_dir", output_dir / "submission_qc_packet")))
    audience_exports = qc_packet.get("audience_exports") if isinstance(qc_packet, dict) else {}
    audience_exports_dir = ""
    if isinstance(audience_exports, dict) and audience_exports:
        candidate = packet_dir / "audience_exports"
        audience_exports_dir = str(candidate.relative_to(output_dir) if candidate.is_relative_to(output_dir) else candidate)
    image_review_packet = qc_packet.get("image_review_packet") if isinstance(qc_packet, dict) else {}
    image_review_dir = ""
    if isinstance(image_review_packet, dict) and image_review_packet.get("packet_dir"):
        candidate = Path(str(image_review_packet.get("packet_dir")))
        image_review_dir = str(candidate.relative_to(output_dir) if candidate.is_relative_to(output_dir) else candidate)
    has_re_audit_diff = (output_dir / "re_audit_diff.md").is_file()
    package_label = package.name or "supplied package"
    lines = [
        "# START HERE",
        "",
        f"Package reviewed: `{package_label}` (local path redacted)",
        f"Overall audit risk band: `{summary.get('overall_risk', 'R0')}`",
        "",
        "Read these files in order:",
        "",
        "1. `audit-report.md` — human-first bilingual report.",
        "2. `unresolved_actions.csv` — open action tracker for follow-up.",
        "3. `correction_plan.md` — concise correction-plan view.",
        f"4. `{packet_dir.relative_to(output_dir) if packet_dir.is_relative_to(output_dir) else packet_dir}` — leave-behind QC packet.",
        "5. `AUDIT_JSON_SUMMARY.json` — machine-readable summary for re-audit or webapp import.",
    ]
    next_index = 6
    if audience_exports_dir:
        lines.append(f"{next_index}. `{audience_exports_dir}` — editable PI, co-author, and journal/reviewer communication drafts.")
        next_index += 1
    if has_re_audit_diff:
        lines.append(f"{next_index}. `re_audit_diff.md` — human-readable comparison with the previous audit run.")
        next_index += 1
    if image_review_dir:
        lines.append(f"{next_index}. `{image_review_dir}` — image-review target list for external tools or manual figure review.")
    lines += [
        "",
        "Boundary: no finding is a misconduct verdict, and no-finding output is not proof that the manuscript is correct.",
        "",
        "中文提示：先读 `audit-report.md`，再用 `unresolved_actions.csv` 跟踪处理项；无发现不等于论文已被证明正确。",
    ]
    path = output_dir / "START_HERE.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def extract_audit_summary(report: Path) -> dict[str, Any]:
    text = report.read_text(encoding="utf-8")
    match = re.search(r"```json AUDIT_JSON_SUMMARY\n(.*?)\n```", text, flags=re.DOTALL)
    if not match:
        raise ContractError(f"audit report has no AUDIT_JSON_SUMMARY block: {report}")
    summary = json.loads(match.group(1))
    validate_instance(summary, SUMMARY_SCHEMA, "audit summary")
    return summary
