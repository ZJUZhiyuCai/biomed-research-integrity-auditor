#!/usr/bin/env python3
"""Run the contract-first biomedical integrity audit pipeline for a package."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from calibrators.contract_validation import ContractError, validate_instance  # noqa: E402


PYTHON = sys.executable
DETECTOR_SCHEMA = ROOT / "schemas" / "detector_output.schema.json"
CALIBRATED_SCHEMA = ROOT / "schemas" / "calibrated_findings.schema.json"
SUMMARY_SCHEMA = ROOT / "schemas" / "audit_summary.schema.json"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SOURCE_EXTS = {".csv", ".tsv"}
MODES = ("internal_presubmission", "external_public_material", "response_to_concern")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def has_files(path: Path, suffixes: set[str]) -> bool:
    return path.exists() and any(item.is_file() and item.suffix.lower() in suffixes for item in path.rglob("*"))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def manifest_mode(mode: str) -> str:
    return "external" if mode == "external_public_material" else "internal"


def build_manifest(package: Path, mode: str, domains: str, output_dir: Path) -> Path:
    manifest = output_dir / "manifest.json"
    run([
        PYTHON,
        "skill/biomed-research-integrity-auditor/scripts/build_package_manifest.py",
        str(package),
        "--mode",
        manifest_mode(mode),
        "--domains",
        domains,
        "--output",
        str(manifest),
    ])
    return manifest


def build_provenance(package: Path, manifest: Path, output_dir: Path) -> Path:
    figure_source_map = output_dir / "figure_source_map.json"
    run([
        PYTHON,
        "skill/biomed-research-integrity-auditor/scripts/figure_source_map.py",
        str(manifest),
        "--output",
        str(figure_source_map),
    ])

    figure_source_links = output_dir / "figure_source_links.json"
    run([
        PYTHON,
        "provenance/parse_figure_source_map.py",
        str(figure_source_map),
        "--output",
        str(figure_source_links),
    ])

    assembly_links = output_dir / "assembly_links.json"
    run([
        PYTHON,
        "provenance/parse_assembly_manifest.py",
        str(package),
        "--output",
        str(assembly_links),
    ])

    provenance_graph = output_dir / "provenance_graph.json"
    run([
        PYTHON,
        "provenance/build_resource_graph.py",
        "--manifest",
        str(manifest),
        "--links",
        str(assembly_links),
        "--links",
        str(figure_source_links),
        "--output",
        str(provenance_graph),
    ])
    return provenance_graph


def validate_detector(path: Path) -> None:
    validate_instance(read_json(path), DETECTOR_SCHEMA, f"detector output {path}")


def run_source_detectors(package: Path, output_dir: Path) -> list[Path]:
    source_dir = package / "source_data"
    outputs: list[Path] = []
    if not has_files(source_dir, SOURCE_EXTS):
        return outputs

    stats_output = output_dir / "stats_consistency_candidates.json"
    run([
        PYTHON,
        "skill/biomed-research-integrity-auditor/scripts/stats_consistency_check.py",
        str(source_dir),
        "--output",
        str(stats_output),
    ])
    validate_detector(stats_output)
    outputs.append(stats_output)

    pseudo_output = output_dir / "pseudoreplication_candidates.json"
    run([
        PYTHON,
        "detectors/stats/pseudoreplication_screen.py",
        str(source_dir),
        "--output",
        str(pseudo_output),
    ])
    validate_detector(pseudo_output)
    outputs.append(pseudo_output)
    return outputs


def run_image_detector(package: Path, output_dir: Path, provenance_graph: Path) -> list[Path]:
    if not has_files(package, IMAGE_EXTS):
        return []

    outputs: list[Path] = []
    image_output = output_dir / "global_image_candidates.json"
    run([
        PYTHON,
        "detectors/image/global_near_duplicate.py",
        str(package),
        "--output",
        str(image_output),
    ])
    validate_detector(image_output)

    contextual_output = output_dir / "contextual_image_candidates.json"
    run([
        PYTHON,
        "calibrators/contextual_joiner.py",
        "--input",
        str(image_output),
        "--package",
        str(package),
        "--provenance",
        str(provenance_graph),
        "--output",
        str(contextual_output),
    ])
    validate_detector(contextual_output)
    outputs.append(contextual_output)

    local_patch_output = output_dir / "local_patch_candidates.json"
    run([
        PYTHON,
        "detectors/image/local_patch_reuse.py",
        str(package),
        "--provenance",
        str(provenance_graph),
        "--evidence-dir",
        str(output_dir / "evidence" / "local_patch"),
        "--output",
        str(local_patch_output),
    ])
    validate_detector(local_patch_output)

    local_patch_contextual_output = output_dir / "local_patch_contextual_candidates.json"
    run([
        PYTHON,
        "calibrators/contextual_joiner.py",
        "--input",
        str(local_patch_output),
        "--package",
        str(package),
        "--provenance",
        str(provenance_graph),
        "--output",
        str(local_patch_contextual_output),
    ])
    validate_detector(local_patch_contextual_output)
    outputs.append(local_patch_contextual_output)
    return outputs


def write_empty_calibrated(mode: str, output: Path) -> None:
    payload = {
        "mode": mode,
        "findings": [],
        "candidate_count": 0,
        "rules": str(ROOT / "schemas" / "risk_rules.yaml"),
    }
    validate_instance(payload, CALIBRATED_SCHEMA, "empty calibrated findings")
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
    run(cmd)
    validate_instance(read_json(calibrated), CALIBRATED_SCHEMA, "calibrated findings")
    return calibrated


def run_report(manifest: Path, calibrated: Path, positive_sources: list[Path], mode: str, case_id: str | None, output_dir: Path) -> Path:
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
    if case_id:
        cmd.extend(["--case-id", case_id])
    run(cmd)
    return report


def extract_audit_summary(report: Path) -> dict[str, Any]:
    text = report.read_text(encoding="utf-8")
    match = re.search(r"```json AUDIT_JSON_SUMMARY\n(.*?)\n```", text, flags=re.DOTALL)
    if not match:
        raise ContractError(f"audit report has no AUDIT_JSON_SUMMARY block: {report}")
    summary = json.loads(match.group(1))
    validate_instance(summary, SUMMARY_SCHEMA, "audit summary")
    return summary


def run_pipeline(package: Path, mode: str, output_dir: Path, domains: str, case_id: str | None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(package, mode, domains, output_dir)
    provenance_graph = build_provenance(package, manifest, output_dir)
    detector_outputs = []
    detector_outputs.extend(run_source_detectors(package, output_dir))
    detector_outputs.extend(run_image_detector(package, output_dir, provenance_graph))
    calibrated = run_calibrator(detector_outputs, mode, output_dir)
    report = run_report(manifest, calibrated, detector_outputs, mode, case_id, output_dir)
    audit_summary = extract_audit_summary(report)
    audit_summary_path = output_dir / "AUDIT_JSON_SUMMARY.json"
    write_json(audit_summary_path, audit_summary)

    result = {
        "package": str(package),
        "mode": mode,
        "output_dir": str(output_dir),
        "manifest": str(manifest),
        "provenance_graph": str(provenance_graph),
        "detector_outputs": [str(path) for path in detector_outputs],
        "calibrated_findings": str(calibrated),
        "report": str(report),
        "audit_summary": str(audit_summary_path),
        "candidate_count": read_json(calibrated).get("candidate_count", 0),
        "finding_count": len(read_json(calibrated).get("findings", [])),
        "overall_risk": audit_summary.get("overall_risk"),
    }
    positive_count = 0
    for path in detector_outputs:
        payload = read_json(path)
        positive_count += len(payload.get("positive_evidence", []) or [])
    result["positive_provenance_count"] = positive_count
    write_json(output_dir / "pipeline_summary.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--mode", choices=MODES, default="internal_presubmission")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--domains", default="wetlab,animal,cell")
    parser.add_argument("--case-id")
    args = parser.parse_args()

    package = args.package_dir.expanduser().resolve()
    if not package.exists() or not package.is_dir():
        raise SystemExit(f"Package directory not found: {package}")
    output_dir = (args.output_dir or (ROOT / "audit_outputs" / package.name)).expanduser().resolve()
    result = run_pipeline(package, args.mode, output_dir, args.domains, args.case_id or package.name)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
