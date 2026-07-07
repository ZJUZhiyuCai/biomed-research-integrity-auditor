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
GENERIC_LOCATION_TERMS = {
    "and",
    "article",
    "fig",
    "figure",
    "panel",
    "paragraph",
    "supp",
    "supplemental",
    "supplementary",
    "table",
}
ISSUE_FAMILY_TERMS = {
    "image_global_similarity": {"global", "near duplicate", "duplicate", "image similarity", "whole image"},
    "image_local_reuse": {"local", "patch", "reuse", "copy", "image reuse", "local similarity"},
    "same_image_copy_move": {"same image", "copy move", "copy-move", "self reuse"},
    "same_section_overlap": {"same section", "section overlap", "text overlap", "phrase overlap"},
    "western_blot_or_gel": {"western", "blot", "gel", "lane"},
    "microscopy_reuse": {"microscopy", "micrograph", "histology", "image reuse", "patch"},
    "statistics_or_numeric": {"stat", "numeric", "digit", "p value", "p-value", "sd", "sem", "mean"},
    "text_overlap": {"text", "overlap", "phrase", "similarity"},
    "reporting_gap": {"reporting", "gap", "missing", "coverage", "materials"},
    "methodological_concern": {"method", "methodology", "checklist", "reporting"},
    "publication_status": {"publication", "status", "retraction", "correction", "metadata"},
    "metadata_status": {"metadata", "status", "retraction", "correction"},
}


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


def normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value).lower())).strip()


def compact_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def finding_full_text(finding: dict[str, Any]) -> str:
    try:
        evidence = json.dumps(finding.get("evidence", {}), ensure_ascii=False)
    except TypeError:
        evidence = str(finding.get("evidence", ""))
    return normalized_text(" ".join(
        str(finding.get(key, ""))
        for key in (
            "finding_id",
            "finding_type",
            "location",
            "evidence_type",
            "module",
            "recommended_action",
            "source_candidate_tags",
        )
    ) + " " + evidence)


def label_issue_compatible(label: dict[str, Any], finding: dict[str, Any]) -> bool:
    issue_type = str(label.get("issue_type", "") or "")
    if not issue_type:
        return True
    text = finding_full_text(finding)
    terms = ISSUE_FAMILY_TERMS.get(issue_type, {issue_type.replace("_", " ")})
    return any(normalized_text(term) in text for term in terms)


def label_location_terms(label: dict[str, Any]) -> set[str]:
    location = label.get("paper_location", {}) or {}
    terms: set[str] = set()
    for key in ("figure", "panel", "table", "paragraph"):
        value = str(location.get(key, "") or "")
        if not value:
            continue
        compact = compact_text(value)
        if len(compact) >= 3:
            terms.add(compact)
        for token in normalized_text(value).split():
            if token not in GENERIC_LOCATION_TERMS and len(token) >= 2:
                terms.add(token)
        for match in re.findall(r"(?:fig(?:ure)?|table|panel|supp(?:lemental|lementary)?\s*fig(?:ure)?)?\s*(s?\d+[a-z]?)", value, flags=re.I):
            normalized = normalized_text(match)
            if len(normalized) >= 2:
                terms.add(normalized)
    return {term for term in terms if term}


def label_location_compatible(label: dict[str, Any], finding: dict[str, Any]) -> bool:
    terms = label_location_terms(label)
    if not terms:
        return True
    full_text = finding_full_text(finding)
    compact = compact_text(full_text)
    return any(term in full_text or compact_text(term) in compact for term in terms)


def finding_text(finding: dict[str, Any]) -> str:
    return " ".join(
        str(finding.get(key, ""))
        for key in ("finding_type", "location", "evidence_type", "recommended_action")
    ).lower()


def label_matches_finding(label: dict[str, Any], finding: dict[str, Any]) -> bool:
    return label_issue_compatible(label, finding) and label_location_compatible(label, finding)


def label_hit(label: dict[str, Any], findings: list[dict[str, Any]]) -> bool:
    return any(label_matches_finding(label, finding) for finding in findings)


def is_recall_label(label: dict[str, Any]) -> bool:
    return str(label.get("evaluation_role", "recall_label")) == "recall_label"


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
    recall_labels = [label for label in labels if is_recall_label(label)]
    scope_gap_labels = [label for label in labels if str(label.get("evaluation_role", "recall_label")) == "scope_gap"]
    reference_labels = [label for label in labels if str(label.get("evaluation_role", "recall_label")) == "reference_only"]
    for label in recall_labels:
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
            for finding in [item for item in findings if label_matches_finding(label, item)]:
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
        "labels_total": len(labels),
        "recall_labels": len(recall_labels),
        "scope_gap_labels": len(scope_gap_labels),
        "reference_only_labels": len(reference_labels),
        "label_hits": total_hits,
        "finding_level_recall": recall,
        "risk_cap_violations": cap_violations,
        "boundary_violations": boundary_count,
        "cases": cases,
        "scope_note": (
            "Metrics compare audit outputs only to labels marked evaluation_role=recall_label. "
            "Scope-gap labels document public observations outside the current detector scope and are not counted as misses. "
            "Labels are not misconduct truth, and matched controls are not clean-paper proof."
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
        "scope_gap_labels": payload["scope_gap_labels"],
        "risk_cap_violations": payload["risk_cap_violations"],
        "boundary_violations": payload["boundary_violations"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
