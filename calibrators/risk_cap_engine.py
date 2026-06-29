#!/usr/bin/env python3
"""Calibrate detector candidates into bounded research-integrity findings."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}
ORDER_RISK = {value: key for key, value in RISK_ORDER.items()}
MODE_DEFAULT_CAPS = {
    "internal_presubmission": "R4",
    "external_public_material": "R3",
    "response_to_concern": "R4",
}
WEAK_TAGS = {
    "weak_forensic_triage_signal",
    "weak_signal",
    "terminal_digit",
    "p_value_clustering",
    "benford_style",
    "precision_mixing",
    "cross_file_sequence_reuse",
}
R4_TAGS = {
    "direct_contradiction",
    "raw_record_conflict",
    "source_to_figure_conflict",
    "source_data_cannot_reproduce_claim",
}


def risk_value(risk: str | None) -> int:
    return RISK_ORDER.get(str(risk or "R0").upper(), 0)


def cap_risk(risk: str, cap: str) -> str:
    return ORDER_RISK[min(risk_value(risk), risk_value(cap))]


def suggested_risk(candidate: dict[str, Any]) -> str:
    explicit = candidate.get("risk_level") or candidate.get("calibrated_risk_level")
    if explicit in RISK_ORDER:
        return explicit
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
    return tags


def calibrate_candidate(candidate: dict[str, Any], mode: str) -> dict[str, Any]:
    tags = candidate_tags(candidate)
    risk = suggested_risk(candidate)
    caps_applied = []

    mode_cap = MODE_DEFAULT_CAPS.get(mode, "R4")
    if risk_value(risk) > risk_value(mode_cap):
        caps_applied.append(f"mode_cap:{mode_cap}")
        risk = cap_risk(risk, mode_cap)

    if tags & WEAK_TAGS and risk_value(risk) > risk_value("R2"):
        caps_applied.append("weak_signal_max:R2")
        risk = "R2"

    if "completeness_gap" in tags and risk_value(risk) > risk_value("R1"):
        caps_applied.append("missing_material_max:R1")
        risk = "R1"

    if risk == "R4" and not (tags & R4_TAGS):
        caps_applied.append("r4_requires_direct_contradiction")
        risk = "R3"

    benign = list(candidate.get("benign_explanations", []) or [])
    required = list(candidate.get("required_materials", []) or [])
    action = candidate.get("recommended_action", "")
    if risk_value(risk) >= risk_value("R3"):
        if not benign:
            benign = ["benign or technical explanation must be tested before escalation"]
            caps_applied.append("added_required_benign_explanation")
        if not required:
            required = ["source/raw records needed to resolve candidate"]
            caps_applied.append("added_required_materials")
        if not action:
            action = "Verify against source/raw records before escalation."

    return {
        "finding_id": candidate.get("candidate_id", ""),
        "risk_level": risk,
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
        "requires_contextual_calibration": bool(candidate.get("requires_contextual_calibration", True)),
        "note": "Calibrated from detector candidate; not a misconduct verdict.",
    }


def load_candidates(paths: list[Path]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
            candidates.extend(payload["candidates"])
        elif isinstance(payload, dict) and isinstance(payload.get("findings"), list):
            for item in payload["findings"]:
                candidates.append({
                    "candidate_id": item.get("finding_id", ""),
                    "detector": item.get("module", "legacy_finding"),
                    "candidate_type": item.get("evidence_type", item.get("finding_type", "legacy_finding")),
                    "locations": [item.get("location", "")],
                    "evidence": item.get("evidence", {}),
                    "evidence_strength": "weak_signal" if str(item.get("evidence_type", "")).startswith("weak") else "candidate",
                    "risk_suggestion": item.get("risk_level", "R1"),
                    "risk_cap_tags": [item.get("evidence_type", "")],
                    "benign_explanations": item.get("benign_explanations_considered", []),
                    "required_materials": item.get("required_materials_to_resolve", []),
                    "recommended_action": item.get("recommended_action", ""),
                    "requires_contextual_calibration": True,
                })
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=sorted(MODE_DEFAULT_CAPS), default="internal_presubmission")
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, default=Path("calibrated_findings.json"))
    args = parser.parse_args()

    candidates = load_candidates([path.expanduser().resolve() for path in args.input])
    findings = [calibrate_candidate(candidate, args.mode) for candidate in candidates]
    for idx, finding in enumerate(findings, start=1):
        if not finding.get("finding_id"):
            finding["finding_id"] = f"BIOMED-CAL-{idx:04d}"
    result = {
        "mode": args.mode,
        "findings": findings,
        "candidate_count": len(candidates),
    }
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "findings": len(findings)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
