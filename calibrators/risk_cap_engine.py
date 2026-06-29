#!/usr/bin/env python3
"""Calibrate detector candidates into bounded research-integrity findings."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from calibrators.contract_validation import ContractError, validate_instance  # noqa: E402


DEFAULT_RULES = ROOT / "schemas" / "risk_rules.yaml"
DETECTOR_SCHEMA = ROOT / "schemas" / "detector_output.schema.json"
CALIBRATED_SCHEMA = ROOT / "schemas" / "calibrated_findings.schema.json"
RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}
ORDER_RISK = {value: key for key, value in RISK_ORDER.items()}


def risk_value(risk: str | None) -> int:
    return RISK_ORDER.get(str(risk or "R0").upper(), 0)


def cap_risk(risk: str, cap: str) -> str:
    return ORDER_RISK[min(risk_value(risk), risk_value(cap))]


def load_rules(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ContractError(f"risk rules not found: {path}")
    rules = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    required = ["mode_caps", "detector_caps", "r4_requirements", "mandatory_fields_for_r3_plus"]
    missing = [field for field in required if field not in rules]
    if missing:
        raise ContractError(f"risk rules missing required sections: {', '.join(missing)}")
    for mode, cfg in rules["mode_caps"].items():
        if not isinstance(cfg, dict) or "default_max" not in cfg:
            raise ContractError(f"risk rules mode_caps.{mode} must define default_max")
    return rules


def suggested_risk(candidate: dict[str, Any]) -> str:
    if "risk_level" in candidate or "calibrated_risk_level" in candidate:
        raise ContractError(f"{candidate.get('candidate_id', '<candidate>')} contains a final risk field")

    suggestion = str(candidate.get("risk_suggestion", "R1")).upper()
    risks = re.findall(r"R[0-4]", suggestion)
    if risks:
        return max(risks, key=risk_value)

    strength = candidate.get("evidence_strength")
    if strength == "direct_contradiction":
        return "R4"
    if strength == "strong_candidate":
        return "R3"
    if strength == "candidate":
        return "R2"
    return "R1"


def candidate_tags(candidate: dict[str, Any]) -> set[str]:
    tags = set(str(tag) for tag in candidate.get("risk_cap_tags", []) or [])
    for key in ("candidate_type", "evidence_type", "evidence_strength"):
        if candidate.get(key):
            tags.add(str(candidate[key]))
    context = candidate.get("context")
    if isinstance(context, dict):
        tags.update(str(tag) for tag in context.get("risk_cap_tags", []) or [])
    evidence = candidate.get("evidence")
    if isinstance(evidence, dict) and isinstance(evidence.get("context"), dict):
        tags.update(str(tag) for tag in evidence["context"].get("risk_cap_tags", []) or [])
    return tags


def cap_from_rule(rule: Any) -> str | None:
    if isinstance(rule, str):
        return rule
    if isinstance(rule, dict):
        value = rule.get("max") or rule.get("default_max")
        return str(value) if value else None
    return None


def apply_cap(risk: str, cap: str | None, reason: str, caps_applied: list[str]) -> str:
    if not cap:
        return risk
    if risk_value(risk) > risk_value(cap):
        caps_applied.append(f"{reason}:{cap}")
        return cap_risk(risk, cap)
    return risk


def evidence_text(candidate: dict[str, Any]) -> str:
    try:
        return json.dumps(candidate.get("evidence", {}), ensure_ascii=False)
    except TypeError:
        return str(candidate.get("evidence", ""))


def calibrate_candidate(candidate: dict[str, Any], mode: str, rules: dict[str, Any]) -> dict[str, Any]:
    if mode not in rules["mode_caps"]:
        raise ContractError(f"unknown audit mode for risk rules: {mode}")

    tags = candidate_tags(candidate)
    starting_risk = suggested_risk(candidate)
    risk = starting_risk
    caps_applied: list[str] = []

    mode_cap = str(rules["mode_caps"][mode]["default_max"])
    risk = apply_cap(risk, mode_cap, "mode_cap", caps_applied)

    detector_caps = rules.get("detector_caps", {})
    for tag in sorted(tags):
        risk = apply_cap(risk, cap_from_rule(detector_caps.get(tag)), f"detector_cap:{tag}", caps_applied)

    contextual_caps = rules.get("contextual_caps", {})
    for tag in sorted(tags):
        risk = apply_cap(risk, cap_from_rule(contextual_caps.get(tag)), f"contextual_cap:{tag}", caps_applied)

    r4_tags = set(str(tag) for tag in rules.get("r4_requirements", []) or [])
    if risk == "R4" and not (tags & r4_tags):
        caps_applied.append("r4_requires_direct_contradiction:R3")
        risk = "R3"

    benign = list(candidate.get("benign_explanations", []) or [])
    required = list(candidate.get("required_materials", []) or [])
    action = candidate.get("recommended_action", "")
    mandatory = set(rules.get("mandatory_fields_for_r3_plus", []) or [])
    if risk_value(risk) >= risk_value("R3"):
        if "benign_explanations" in mandatory and not benign:
            benign = ["benign or technical explanation must be tested before escalation"]
            caps_applied.append("filled_mandatory_benign_explanations")
        if "required_materials_to_resolve" in mandatory and not required:
            required = ["source/raw records needed to resolve candidate"]
            caps_applied.append("filled_mandatory_required_materials")
        if "recommended_action" in mandatory and not action:
            action = "Verify against source/raw records before escalation."
            caps_applied.append("filled_mandatory_recommended_action")

    return {
        "finding_id": candidate.get("candidate_id", ""),
        "calibrated_risk_level": risk,
        "module": candidate.get("module", candidate.get("detector", "detector")),
        "location": " / ".join(candidate.get("locations", []) or [candidate.get("location", "")]),
        "finding_type": candidate.get("finding_type", candidate.get("candidate_type", "detector candidate")),
        "evidence_type": candidate.get("candidate_type", candidate.get("evidence_type", "")),
        "evidence": candidate.get("evidence", {}),
        "evidence_strength": candidate.get("evidence_strength", ""),
        "benign_explanations_considered": benign,
        "required_materials_to_resolve": required,
        "recommended_action": action,
        "risk_caps_applied": caps_applied,
        "calibration_reason": (
            f"Started from {starting_risk} based on risk_suggestion/evidence_strength; "
            f"applied mode, detector, contextual, and R4 caps from risk_rules.yaml."
        ),
        "requires_contextual_calibration": bool(candidate.get("requires_contextual_calibration", True)),
        "note": "Calibrated from detector candidate; not a misconduct verdict.",
        "source_candidate": candidate.get("candidate_id", ""),
        "source_candidate_tags": sorted(tags),
        "source_evidence_text": evidence_text(candidate)[:1000],
    }


def legacy_finding_to_candidate(item: dict[str, Any]) -> dict[str, Any]:
    evidence_type = str(item.get("evidence_type", item.get("finding_type", "legacy_finding")))
    weak = "weak" in evidence_type or "terminal" in evidence_type or "precision" in evidence_type
    return {
        "candidate_id": item.get("finding_id", ""),
        "detector": item.get("module", "legacy_finding"),
        "candidate_type": evidence_type,
        "locations": [item.get("location", "")],
        "evidence": item.get("evidence", {}),
        "evidence_strength": "weak_signal" if weak else "candidate",
        "risk_suggestion": item.get("risk_level", "R1"),
        "risk_cap_tags": [evidence_type, "weak_signal"] if weak else [evidence_type],
        "benign_explanations": item.get("benign_explanations_considered", []),
        "required_materials": item.get("required_materials_to_resolve", []),
        "recommended_action": item.get("recommended_action", ""),
        "requires_contextual_calibration": True,
    }


def load_candidates(paths: list[Path]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
            validate_instance(payload, DETECTOR_SCHEMA, f"detector output {path}")
            candidates.extend(payload["candidates"])
        elif isinstance(payload, dict) and isinstance(payload.get("findings"), list):
            candidates.extend(legacy_finding_to_candidate(item) for item in payload["findings"])
        else:
            raise ContractError(f"{path} is not a detector output or legacy findings payload")
    return candidates


def calibrate_payload(input_paths: list[Path], mode: str, rules_path: Path) -> dict[str, Any]:
    rules = load_rules(rules_path)
    candidates = load_candidates(input_paths)
    findings = [calibrate_candidate(candidate, mode, rules) for candidate in candidates]
    for idx, finding in enumerate(findings, start=1):
        if not finding.get("finding_id"):
            finding["finding_id"] = f"BIOMED-CAL-{idx:04d}"
    result = {
        "mode": mode,
        "findings": findings,
        "candidate_count": len(candidates),
        "rules": str(rules_path),
    }
    validate_instance(result, CALIBRATED_SCHEMA, "calibrated findings")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", default="internal_presubmission")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, default=Path("calibrated_findings.json"))
    args = parser.parse_args()

    result = calibrate_payload(
        [path.expanduser().resolve() for path in args.input],
        args.mode,
        args.rules.expanduser().resolve(),
    )
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "findings": len(result["findings"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
