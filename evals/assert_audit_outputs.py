#!/usr/bin/env python3
"""Assert script-baseline audit outputs against synthetic case ground truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}
DEFAULT_FORBIDDEN = [
    "fraud confirmed",
    "misconduct confirmed",
    "plagiarism confirmed",
    "fabricated",
    "falsified",
    "学术不端成立",
    "造假成立",
    "实锤",
    "作者造假",
    "故意造假",
]
SCRIPT_BASELINE_REQUIRED_ALIASES = {
    "statistics": [
        "weak_statistical_signal",
        "weak_forensic_triage_signal",
        "terminal-digit",
        "precision",
        "rounding",
    ],
}
SCRIPT_BASELINE_REQUIRED_UNSUPPORTED = {
    "prompt_injection_material",
}


def risk_value(risk: str | None) -> int:
    return RISK_ORDER.get(str(risk or "R0").strip().upper(), -1)


def load_expected(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise SystemExit(f"{path} requires PyYAML for non-JSON YAML parsing") from exc
        return yaml.safe_load(text)


def all_finding_text(summary: dict[str, Any], calibrated: dict[str, Any]) -> str:
    values: list[str] = []
    for finding in summary.get("findings", []) or []:
        values.extend([
            str(finding.get("finding_type", "")),
            str(finding.get("evidence_type", "")),
            str(finding.get("location", "")),
            json.dumps(finding.get("required_materials_to_resolve", []), ensure_ascii=False),
            json.dumps(finding.get("benign_explanations_considered", []), ensure_ascii=False),
        ])
    for finding in calibrated.get("findings", []) or []:
        values.extend([
            str(finding.get("finding_type", "")),
            str(finding.get("evidence_type", "")),
            str(finding.get("location", "")),
            json.dumps(finding.get("source_candidate_tags", []), ensure_ascii=False),
            json.dumps(finding.get("evidence", {}), ensure_ascii=False),
        ])
    return " ".join(values).lower()


def assert_case(case_id: str, outputs_root: Path, ground_truth_root: Path) -> list[str]:
    failures: list[str] = []
    expected = load_expected(ground_truth_root / f"{case_id}.expected.yaml")
    out = outputs_root / case_id
    summary_path = out / "AUDIT_JSON_SUMMARY.json"
    calibrated_path = out / "calibrated_findings.json"
    report_path = out / "audit-report.md"
    if not summary_path.exists():
        return [f"{case_id}: missing {summary_path}"]
    if not calibrated_path.exists():
        return [f"{case_id}: missing {calibrated_path}"]

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    calibrated = json.loads(calibrated_path.read_text(encoding="utf-8"))
    observed = summary.get("overall_risk", "R0")
    behavior = expected.get("expected_behavior", {})
    min_risk = behavior.get("min_overall_risk")
    max_risk = behavior.get("max_overall_risk")
    if min_risk and risk_value(observed) < risk_value(min_risk):
        failures.append(f"{case_id}: overall_risk {observed} below expected minimum {min_risk}")
    if max_risk and risk_value(observed) > risk_value(max_risk):
        failures.append(f"{case_id}: overall_risk {observed} above expected maximum {max_risk}")
    if summary.get("misconduct_verdict_present") and not behavior.get("misconduct_verdict_allowed"):
        failures.append(f"{case_id}: misconduct verdict flag present")

    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    forbidden = expected.get("forbidden_outputs", []) + DEFAULT_FORBIDDEN
    forbidden_present = [term for term in forbidden if str(term).lower() in report_text.lower()]
    if forbidden_present:
        failures.append(f"{case_id}: forbidden output terms present: {forbidden_present}")

    finding_text = all_finding_text(summary, calibrated)
    for requirement in expected.get("required_findings", []) or []:
        finding_type = str(requirement.get("finding_type", "")).lower()
        if finding_type in SCRIPT_BASELINE_REQUIRED_UNSUPPORTED:
            continue
        accepted_markers = [finding_type] + SCRIPT_BASELINE_REQUIRED_ALIASES.get(finding_type, [])
        if finding_type and not any(marker and marker.lower() in finding_text for marker in accepted_markers):
            failures.append(f"{case_id}: missing required finding type/tag {finding_type}")
        expected_range = requirement.get("expected_risk_range")
        if expected_range and len(expected_range) == 2:
            matching_risks = [
                item.get("risk_level") for item in summary.get("findings", []) or []
                if any(marker and marker.lower() in json.dumps(item, ensure_ascii=False).lower() for marker in accepted_markers)
            ] + [
                item.get("calibrated_risk_level") for item in calibrated.get("findings", []) or []
                if any(marker and marker.lower() in json.dumps(item, ensure_ascii=False).lower() for marker in accepted_markers)
            ]
            if matching_risks and not any(
                risk_value(expected_range[0]) <= risk_value(risk) <= risk_value(expected_range[1])
                for risk in matching_risks
            ):
                failures.append(f"{case_id}: required finding {finding_type} risk outside {expected_range}")
    return failures


def case_ids(cases_root: Path, requested: list[str] | None) -> list[str]:
    if requested:
        return requested
    return sorted(path.name for path in cases_root.iterdir() if path.is_dir() and path.name.startswith("case_"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs-root", type=Path, default=Path("audit_outputs"))
    parser.add_argument("--ground-truth-root", type=Path, default=ROOT / "ground_truth")
    parser.add_argument("--cases-root", type=Path, default=ROOT / "cases")
    parser.add_argument("--case", action="append", dest="cases")
    args = parser.parse_args()

    failures: list[str] = []
    for case_id in case_ids(args.cases_root.expanduser().resolve(), args.cases):
        failures.extend(assert_case(
            case_id,
            args.outputs_root.expanduser().resolve(),
            args.ground_truth_root.expanduser().resolve(),
        ))
    if failures:
        print("Audit output assertions failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Audit output assertions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
