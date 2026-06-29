#!/usr/bin/env python3
"""Assemble a Markdown biomedical integrity audit report from JSON artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}


def humanize(value: str) -> str:
    return str(value).replace("_", " ").replace("-", " ").strip()


def load_json(path: Path | None, default: Any) -> Any:
    if path is None:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def coerce_finding(item: dict[str, Any], idx: int) -> dict[str, Any]:
    result = dict(item)
    result.setdefault("finding_id", f"BIOMED-GEN-{idx:04d}")
    result.setdefault("risk_level", "R1")
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
                findings.extend(coerce_finding(item, idx) for idx, item in enumerate(payload["findings"], start=1))
            elif isinstance(payload.get("candidates"), list):
                for idx, item in enumerate(payload["candidates"], start=1):
                    findings.append({
                        "finding_id": f"BIOMED-IMG-{idx:04d}",
                        "risk_level": item.get("calibrated_risk_level", item.get("risk_level", "R2")),
                        "module": "Image Integrity",
                        "location": " / ".join(item.get("locations", []) or [f"{item.get('left')} / {item.get('right')}"]),
                        "finding_type": item.get("candidate_type", "Perceptual-hash image similarity candidate"),
                        "evidence_type": item.get("candidate_type", "image_similarity_candidate"),
                        "evidence": item,
                        "benign_explanations_considered": [
                            "same field intentionally reused",
                            "figure assembly error",
                            "image compression or export artifact",
                        ],
                        "required_materials_to_resolve": [
                            "original image files",
                            "acquisition metadata",
                            "figure assembly file",
                        ],
                        "recommended_action": item.get("recommended_action", "Inspect the candidate pair against original images and sample identity before escalating."),
                        "note": item.get("note", "Detector candidate only; calibrate before using R3/R4 language."),
                    })
            elif payload.get("missing_materials"):
                for idx, item in enumerate(payload["missing_materials"], start=1):
                    findings.append({
                        "finding_id": f"BIOMED-PKG-{idx:04d}",
                        "risk_level": item.get("risk_level", "R1"),
                        "module": "Package Completeness",
                        "location": item.get("category", ""),
                        "finding_type": "Missing material category",
                        "evidence_type": "completeness_gap",
                        "evidence": item.get("reason", ""),
                        "benign_explanations_considered": [
                            "material may exist but was not supplied in the audit package",
                        ],
                        "required_materials_to_resolve": [humanize(item.get("category", "missing material"))],
                        "recommended_action": "Request the missing material before treating the audit as complete.",
                    })
    return findings


def table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join("---" for _ in rows[0]) + " |"
    body = ["| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |" for row in rows[1:]]
    return "\n".join([header, sep, *body]) + "\n"


def normalized_mode(mode: str) -> str:
    return "internal_presubmission" if mode == "internal" else "external_literature_triage"


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


def build_summary(mode: str, case_id: str | None, manifest: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    caps = []
    if mode == "external" and not any(path.lower().endswith((".csv", ".xlsx", ".tif", ".tiff", ".czi", ".nd2", ".fcs")) for path in reviewed_materials(manifest)):
        caps.append("Public or presentation-layer materials only; source/raw-level verification is limited.")
    if manifest.get("missing_materials"):
        caps.append("Missing materials are completeness gaps, not evidence of misconduct.")
    return {
        "audit_mode": normalized_mode(mode),
        "case_id": case_id,
        "materials_reviewed": reviewed_materials(manifest),
        "materials_missing": missing_materials(manifest),
        "overall_risk": overall_risk(findings, manifest),
        "misconduct_verdict_present": False,
        "risk_caps_applied": caps,
        "findings": [summary_finding(item) for item in findings],
    }


def render_report(mode: str, manifest: dict[str, Any], findings: list[dict[str, Any]], case_id: str | None) -> str:
    title = "Biomedical Research Integrity Pre-submission Audit" if mode == "internal" else "Biomedical Literature Concern Triage"
    lines = [f"# {title}", ""]
    lines += ["## Scope", ""]
    lines += [f"- Mode: {mode}", f"- Package root: {manifest.get('root', 'not supplied')}", ""]

    lines += ["## Missing Materials Matrix", ""]
    missing_rows = [["Category", "Risk", "Reason"]]
    for item in manifest.get("missing_materials", []):
        missing_rows.append([item.get("category", ""), item.get("risk_level", "R1"), item.get("reason", "")])
    lines += [table(missing_rows) if len(missing_rows) > 1 else "No missing expected material categories were reported.\n"]

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
        json.dumps(build_summary(mode, case_id, manifest, findings), indent=2, ensure_ascii=False),
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["internal", "external"], default="internal")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--findings", type=Path, action="append", default=[])
    parser.add_argument("--case-id")
    parser.add_argument("--output", type=Path, default=Path("audit-report.md"))
    args = parser.parse_args()

    manifest = load_json(args.manifest, {})
    finding_payloads = [load_json(path, {}) for path in args.findings]
    findings = normalize_findings(finding_payloads)
    args.output.write_text(render_report(args.mode, manifest, findings, args.case_id), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "findings": len(findings)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
