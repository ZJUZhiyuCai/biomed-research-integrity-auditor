#!/usr/bin/env python3
"""Run the contract-first biomedical integrity audit pipeline for a package."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import re
import shlex
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
SOURCE_EXTS = {".csv", ".tsv", ".xlsx"}
TEXT_EXTS = {".txt", ".md", ".pdf"}
MODES = ("internal_presubmission", "external_public_material", "response_to_concern")


@dataclass(frozen=True)
class DetectorRunResult:
    output: Path
    ok: bool


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def has_files(path: Path, suffixes: set[str]) -> bool:
    return path.exists() and any(item.is_file() and item.suffix.lower() in suffixes for item in path.rglob("*"))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def command_display(cmd: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in cmd)


def text_tail(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def stage_slug(stage: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", stage.lower()).strip("_") or "detector"


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


def write_detector_failure(
    stage: str,
    package: Path,
    output_dir: Path,
    cmd: list[str],
    expected_output: Path,
    reason: str,
    returncode: int | None = None,
    stdout: str = "",
    stderr: str = "",
) -> Path:
    slug = stage_slug(stage)
    error = {
        "stage": stage,
        "command": command_display(cmd),
        "expected_output": str(expected_output),
        "reason": reason,
        "returncode": returncode,
        "stdout_tail": text_tail(stdout),
        "stderr_tail": text_tail(stderr),
    }
    payload = {
        "detector_name": "audit.detector_failure",
        "detector_version": "0.1.0",
        "input": {
            "package": str(package),
            "stage": stage,
            "expected_output": str(expected_output),
        },
        "candidates": [
            {
                "candidate_id": f"AUDIT-DETECTOR-{slug.upper()}",
                "detector": "audit.detector_failure",
                "candidate_type": "detector_execution_failure",
                "locations": [str(package)],
                "evidence": {
                    "message": "A detector failed or produced invalid output; audit results are partial for this module.",
                    **error,
                },
                "evidence_strength": "weak_signal",
                "risk_suggestion": "R1_max",
                "risk_cap_tags": ["detector_execution_failure", "audit_coverage_gap", "completeness_gap"],
                "benign_explanations": [
                    "The input may use a format, encoding, image mode, or file structure not yet supported by this detector.",
                    "The detector or its runtime dependency may have failed independently of the research materials.",
                ],
                "required_materials": [
                    "detector stdout/stderr logs",
                    "supported source/raw files or converted exports for the failed module",
                    "manual review of the materials covered by the failed detector",
                ],
                "recommended_action": (
                    "Review the detector error, convert unsupported files when appropriate, and do not treat this module as clean."
                ),
                "requires_contextual_calibration": True,
            }
        ],
        "errors": [error],
    }
    output = output_dir / f"{slug}_failure_candidates.json"
    write_json(output, payload)
    validate_detector(output)
    return output


def run_detector(stage: str, package: Path, output_dir: Path, cmd: list[str], expected_output: Path) -> DetectorRunResult:
    result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return DetectorRunResult(
            write_detector_failure(
                stage,
                package,
                output_dir,
                cmd,
                expected_output,
                "detector command exited non-zero",
                result.returncode,
                result.stdout,
                result.stderr,
            ),
            False,
        )
    if not expected_output.exists():
        return DetectorRunResult(
            write_detector_failure(
                stage,
                package,
                output_dir,
                cmd,
                expected_output,
                "detector command completed but did not write the expected output",
                result.returncode,
                result.stdout,
                result.stderr,
            ),
            False,
        )
    try:
        validate_detector(expected_output)
    except Exception as exc:  # noqa: BLE001 - invalid detector output becomes an audit finding.
        return DetectorRunResult(
            write_detector_failure(
                stage,
                package,
                output_dir,
                cmd,
                expected_output,
                f"detector output failed contract validation: {exc}",
                result.returncode,
                result.stdout,
                result.stderr,
            ),
            False,
        )
    return DetectorRunResult(expected_output, True)


def run_source_detectors(package: Path, output_dir: Path) -> list[Path]:
    source_dir = package / "source_data"
    outputs: list[Path] = []
    if not has_files(source_dir, SOURCE_EXTS):
        return outputs

    stats_output = output_dir / "stats_consistency_candidates.json"
    result = run_detector("stats_consistency", package, output_dir, [
        PYTHON,
        "skill/biomed-research-integrity-auditor/scripts/stats_consistency_check.py",
        str(source_dir),
        "--output",
        str(stats_output),
    ], stats_output)
    outputs.append(result.output)

    pseudo_output = output_dir / "pseudoreplication_candidates.json"
    result = run_detector("pseudoreplication", package, output_dir, [
        PYTHON,
        "detectors/stats/pseudoreplication_screen.py",
        str(source_dir),
        "--output",
        str(pseudo_output),
    ], pseudo_output)
    outputs.append(result.output)
    return outputs


def run_image_detector(package: Path, output_dir: Path, provenance_graph: Path) -> list[Path]:
    if not has_files(package, IMAGE_EXTS):
        return []

    outputs: list[Path] = []
    image_output = output_dir / "global_image_candidates.json"
    global_result = run_detector("global_image", package, output_dir, [
        PYTHON,
        "detectors/image/global_near_duplicate.py",
        str(package),
        "--output",
        str(image_output),
    ], image_output)

    if global_result.ok:
        contextual_output = output_dir / "contextual_image_candidates.json"
        contextual_result = run_detector("contextual_image", package, output_dir, [
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
        ], contextual_output)
        outputs.append(contextual_result.output)
    else:
        outputs.append(global_result.output)

    local_patch_output = output_dir / "local_patch_candidates.json"
    local_patch_result = run_detector("local_patch", package, output_dir, [
        PYTHON,
        "detectors/image/local_patch_reuse.py",
        str(package),
        "--provenance",
        str(provenance_graph),
        "--evidence-dir",
        str(output_dir / "evidence" / "local_patch"),
        "--output",
        str(local_patch_output),
    ], local_patch_output)

    if local_patch_result.ok:
        local_patch_contextual_output = output_dir / "local_patch_contextual_candidates.json"
        local_patch_contextual_result = run_detector("local_patch_contextual", package, output_dir, [
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
        ], local_patch_contextual_output)
        outputs.append(local_patch_contextual_result.output)
    else:
        outputs.append(local_patch_result.output)
    return outputs


def run_text_detectors(package: Path, output_dir: Path) -> list[Path]:
    if not has_files(package, TEXT_EXTS):
        return []
    text_output = output_dir / "text_overlap_candidates.json"
    result = run_detector("text_overlap", package, output_dir, [
        PYTHON,
        "detectors/text/text_overlap_screen.py",
        str(package),
        "--output",
        str(text_output),
    ], text_output)
    return [result.output]


def write_audit_coverage_gap(package: Path, output_dir: Path) -> Path:
    files = [path for path in sorted(package.rglob("*")) if path.is_file()]
    relative_files = [str(path.relative_to(package)) for path in files[:25]]
    observed_suffixes = sorted({path.suffix.lower() or "<none>" for path in files})
    payload = {
        "detector_name": "audit.coverage",
        "detector_version": "0.1.0",
        "input": {
            "package": str(package),
            "file_count": len(files),
            "observed_suffixes": observed_suffixes,
            "supported_suffixes": {
                "image": sorted(IMAGE_EXTS),
                "source_table": sorted(SOURCE_EXTS),
                "text": sorted(TEXT_EXTS),
            },
        },
        "candidates": [
            {
                "candidate_id": "AUDIT-COVERAGE-0001",
                "detector": "audit.coverage",
                "candidate_type": "audit_coverage_gap",
                "locations": [str(package)],
                "evidence": {
                    "message": "No detector outputs were produced for this package; the audit scope is not equivalent to a clean result.",
                    "file_count": len(files),
                    "sample_files": relative_files,
                    "observed_suffixes": observed_suffixes,
                    "supported_suffixes": {
                        "image": sorted(IMAGE_EXTS),
                        "source_table": sorted(SOURCE_EXTS),
                        "text": sorted(TEXT_EXTS),
                    },
                },
                "evidence_strength": "weak_signal",
                "risk_suggestion": "R1_max",
                "risk_cap_tags": ["audit_coverage_gap", "completeness_gap"],
                "benign_explanations": [
                    "The package may contain valid research records in formats not yet supported by the current detectors.",
                    "Relevant raw/source materials may exist but were not supplied in this audit package.",
                ],
                "required_materials": [
                    "supported manuscript text, source-data CSV/TSV files, or image files",
                    "raw/source records or extracted text suitable for the current detector set",
                ],
                "recommended_action": (
                    "Add supported source/raw/text/image files or extracted text before treating this audit as complete."
                ),
                "requires_contextual_calibration": True,
            }
        ],
        "errors": [],
    }
    output = output_dir / "audit_coverage_candidates.json"
    write_json(output, payload)
    validate_detector(output)
    return output


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
    detector_outputs.extend(run_text_detectors(package, output_dir))
    if not detector_outputs:
        detector_outputs.append(write_audit_coverage_gap(package, output_dir))
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
