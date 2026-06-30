#!/usr/bin/env python3
"""Evaluate audit outputs against PPPR finding-level labels."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "benchmarks" / "pppr_integrity_benchmark" / "labels.schema.json"
RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}
BOUNDARY_TERMS = (
    "proven misconduct",
    "committed misconduct",
    "the authors cheated",
    "fabricated the data",
    "intentional falsification",
)


def load_labels(path: Path) -> list[dict[str, Any]]:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    labels = []
    if not path.is_file() or not path.read_text(encoding="utf-8").strip():
        return labels
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        errors = sorted(validator.iter_errors(item), key=lambda error: error.path)
        if errors:
            raise SystemExit(f"{path}:{line_no} label failed schema validation: {errors[0].message}")
        labels.append(item)
    return labels


def expected_max_risk(expected: str) -> str:
    risks = re.findall(r"R[0-4]", expected)
    if not risks:
        return "R4"
    return max(risks, key=lambda risk: RISK_ORDER[risk])


def output_paths(outputs_root: Path, case_id: str) -> tuple[Path, Path]:
    case_dir = outputs_root / case_id
    return case_dir / "AUDIT_JSON_SUMMARY.json", case_dir / "audit-report.md"


def label_tokens(label: dict[str, Any]) -> set[str]:
    tokens = {str(label.get("issue_type", "")).lower().replace("_", " ")}
    location = label.get("paper_location", {}) or {}
    for key in ("figure", "panel", "table", "paragraph"):
        value = str(location.get(key, "") or "").lower()
        if value:
            tokens.add(value)
    return {token for token in tokens if token}


def finding_text(finding: dict[str, Any]) -> str:
    return " ".join(
        str(finding.get(key, ""))
        for key in ("finding_type", "location", "evidence_type", "recommended_action")
    ).lower()


def label_hit(label: dict[str, Any], findings: list[dict[str, Any]]) -> bool:
    tokens = label_tokens(label)
    if not tokens:
        return bool(findings)
    for finding in findings:
        text = finding_text(finding)
        if any(token in text for token in tokens):
            return True
    return False


def boundary_violations(summary: dict[str, Any], report_text: str) -> list[str]:
    violations = []
    if summary.get("misconduct_verdict_present"):
        violations.append("misconduct_verdict_present=true")
    lowered = report_text.lower()
    for term in BOUNDARY_TERMS:
        if term in lowered:
            violations.append(f"boundary term: {term}")
    return violations


def evaluate(labels: list[dict[str, Any]], outputs_root: Path) -> dict[str, Any]:
    labels_by_case: dict[str, list[dict[str, Any]]] = {}
    for label in labels:
        labels_by_case.setdefault(label["case_id"], []).append(label)

    cases = []
    total_hits = 0
    total_labels = 0
    cap_violations = 0
    boundary_count = 0
    missing_outputs = 0
    for case_id, case_labels in sorted(labels_by_case.items()):
        summary_path, report_path = output_paths(outputs_root, case_id)
        if not summary_path.is_file():
            missing_outputs += 1
            cases.append({"case_id": case_id, "missing_output": True})
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        report_text = report_path.read_text(encoding="utf-8", errors="ignore") if report_path.is_file() else ""
        findings = summary.get("findings", []) or []
        case_hits = sum(1 for label in case_labels if label_hit(label, findings))
        total_hits += case_hits
        total_labels += len(case_labels)
        case_cap_violations = 0
        for label in case_labels:
            max_risk = expected_max_risk(str(label.get("expected_risk", "")))
            for finding in findings:
                risk = finding.get("risk_level", "R0")
                if RISK_ORDER.get(risk, 0) > RISK_ORDER[max_risk]:
                    case_cap_violations += 1
        cap_violations += case_cap_violations
        boundary = boundary_violations(summary, report_text)
        boundary_count += len(boundary)
        cases.append({
            "case_id": case_id,
            "labels": len(case_labels),
            "label_hits": case_hits,
            "finding_count": len(findings),
            "overall_risk": summary.get("overall_risk"),
            "risk_cap_violations": case_cap_violations,
            "boundary_violations": boundary,
        })
    recall = (total_hits / total_labels) if total_labels else None
    return {
        "cases_evaluated": len(labels_by_case),
        "missing_outputs": missing_outputs,
        "labels": total_labels,
        "label_hits": total_hits,
        "finding_level_recall": recall,
        "risk_cap_violations": cap_violations,
        "boundary_violations": boundary_count,
        "cases": cases,
        "scope_note": (
            "Metrics compare audit outputs to public-concern labels. Labels are not misconduct truth, "
            "and matched controls are not clean-paper proof."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--outputs-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    labels = load_labels(args.labels)
    payload = evaluate(labels, args.outputs_root.expanduser().resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "cases_evaluated": payload["cases_evaluated"],
        "labels": payload["labels"],
        "risk_cap_violations": payload["risk_cap_violations"],
        "boundary_violations": payload["boundary_violations"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
