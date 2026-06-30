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
from scripts.methodology_checklist import (  # noqa: E402
    build_methodology_checklist,
    write_methodology_checklist_csv,
)
from scripts.writing_readiness_check import (  # noqa: E402
    build_writing_readiness,
    write_csv as write_writing_readiness_csv,
)
from scripts.submission_qc import (  # noqa: E402
    build_audit_snapshot,
    build_claim_coverage,
    build_file_hash_manifest,
    build_re_audit_diff,
    correction_plan_rows,
    export_submission_qc_packet,
    find_claim_manifest,
    pyproject_version,
    unresolved_action_rows,
    write_claim_coverage_csv,
    write_correction_plan_csv,
    write_correction_plan_markdown,
    write_empty_action_tracker_csv,
    write_missing_materials_csv,
    write_json as write_qc_json,
    write_re_audit_diff_csv,
    write_unresolved_actions_csv,
    write_verified_traceability_csv,
)


PYTHON = sys.executable
DETECTOR_SCHEMA = ROOT / "schemas" / "detector_output.schema.json"
CALIBRATED_SCHEMA = ROOT / "schemas" / "calibrated_findings.schema.json"
SUMMARY_SCHEMA = ROOT / "schemas" / "audit_summary.schema.json"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SOURCE_EXTS = {".csv", ".tsv", ".xlsx"}
TEXT_EXTS = {".txt", ".md", ".pdf"}
MODES = ("internal_presubmission", "external_public_material", "response_to_concern")
SCAN_PROFILES = ("quick", "standard", "deep")
EXTERNAL_LITERATURE_PROVIDERS = ("auto", "none", "fixture", "europepmc", "crossref")
REFERENCE_CHECK_PROVIDERS = ("none", "crossref")
EXTERNAL_LITERATURE_FIXTURE_NAMES = (
    "external_literature_fixture.json",
    "external_literature/fixture.json",
)


@dataclass(frozen=True)
class DetectorRunResult:
    output: Path
    ok: bool


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def has_files(path: Path, suffixes: set[str]) -> bool:
    return path.exists() and any(item.is_file() and item.suffix.lower() in suffixes for item in path.rglob("*"))


def find_external_literature_fixture(package: Path) -> Path | None:
    for name in EXTERNAL_LITERATURE_FIXTURE_NAMES:
        candidate = package / name
        if candidate.is_file():
            return candidate
    return None


def resolve_external_literature_provider(mode: str, requested: str, fixture_path: Path | None) -> str | None:
    if requested == "none":
        return None
    if requested == "fixture":
        if fixture_path is None:
            raise SystemExit("--external-literature-provider fixture requires --external-literature-fixture or a package fixture")
        return "fixture"
    if requested in {"europepmc", "crossref"}:
        return requested
    if fixture_path is not None:
        return "fixture"
    if mode == "external_public_material":
        return "europepmc"
    return None


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


def run_image_detector(package: Path, output_dir: Path, provenance_graph: Path, scan_profile: str = "standard") -> list[Path]:
    if not has_files(package, IMAGE_EXTS):
        return []

    outputs: list[Path] = []
    image_output = output_dir / "global_image_candidates.json"
    global_cmd = [
        PYTHON,
        "detectors/image/global_near_duplicate.py",
        str(package),
        "--output",
        str(image_output),
    ]
    if scan_profile == "deep":
        global_cmd.extend(["--threshold", "8"])
    global_result = run_detector("global_image", package, output_dir, global_cmd, image_output)

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

    if scan_profile == "quick":
        return outputs

    local_patch_output = output_dir / "local_patch_candidates.json"
    local_patch_cmd = [
        PYTHON,
        "detectors/image/local_patch_reuse.py",
        str(package),
        "--provenance",
        str(provenance_graph),
        "--evidence-dir",
        str(output_dir / "evidence" / "local_patch"),
        "--output",
        str(local_patch_output),
    ]
    if scan_profile == "deep":
        local_patch_cmd.extend([
            "--tile-size",
            "96",
            "--stride",
            "48",
            "--hash-threshold",
            "5",
        ])
    local_patch_result = run_detector("local_patch", package, output_dir, local_patch_cmd, local_patch_output)

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


def run_text_detectors(
    package: Path,
    output_dir: Path,
    mode: str,
    external_literature_provider: str,
    external_literature_fixture: Path | None,
) -> list[Path]:
    if not has_files(package, TEXT_EXTS):
        return []
    outputs: list[Path] = []
    text_output = output_dir / "text_overlap_candidates.json"
    result = run_detector("text_overlap", package, output_dir, [
        PYTHON,
        "detectors/text/text_overlap_screen.py",
        str(package),
        "--output",
        str(text_output),
    ], text_output)
    outputs.append(result.output)

    fixture_path = external_literature_fixture or find_external_literature_fixture(package)
    provider = resolve_external_literature_provider(mode, external_literature_provider, fixture_path)
    if provider is None:
        return outputs

    external_output = output_dir / "external_literature_candidates.json"
    cmd = [
        PYTHON,
        "detectors/text/external_literature_search.py",
        str(package),
        "--provider",
        provider,
        "--output",
        str(external_output),
    ]
    if provider == "fixture":
        assert fixture_path is not None
        cmd.extend(["--fixture", str(fixture_path)])
    external_result = run_detector("external_literature_search", package, output_dir, cmd, external_output)
    outputs.append(external_result.output)
    return outputs


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


def build_coverage(
    package: Path,
    output_dir: Path,
    detector_outputs: list[Path],
    external_provider: str | None,
    scan_profile: str = "standard",
) -> dict[str, Any]:
    """Summarize what the audit actually screened so a clean report is not mistaken for a clean paper."""

    def load_safe(name: str) -> dict[str, Any] | None:
        path = output_dir / name
        return read_json(path) if path.exists() else None

    coverage: dict[str, Any] = {
        "modules_executed": [],
        "modules_not_executed": [],
        "image_panels_screened": 0,
        "image_files_unreadable": 0,
        "source_tables_screened": 0,
        "detector_failures": [],
        "audit_coverage_gap": False,
        "external_literature_provider": external_provider,
        "scan_profile": scan_profile,
        "profile_parameters": (
            {
                "global_image_hash_threshold": 8,
                "local_patch_tile_size": 96,
                "local_patch_stride": 48,
                "local_patch_hash_threshold": 5,
            }
            if scan_profile == "deep"
            else {}
        ),
        "scope_note": (
            "A module with no findings means no candidate was detected within the current detector "
            "scope and supplied materials; it is not a guarantee of correctness. Methodology and "
            "reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and "
            "exhaustive external plagiarism-database search are not performed automatically and require "
            "human review."
        ),
    }

    if has_files(package, IMAGE_EXTS):
        coverage["modules_executed"].append("image_global_near_duplicate")
        if scan_profile == "quick":
            coverage["modules_not_executed"].append(
                "local patch / same-image copy-move deep image screening (skipped by quick scan profile)"
            )
        else:
            coverage["modules_executed"].append("image_local_patch_and_same_image_copy_move")
        global_payload = load_safe("global_image_candidates.json")
        if global_payload:
            coverage["image_panels_screened"] = int(global_payload.get("images_screened", 0) or 0)
            coverage["image_files_unreadable"] += len(global_payload.get("errors", []) or [])
        if scan_profile != "quick":
            local_payload = load_safe("local_patch_candidates.json")
            if local_payload:
                coverage["image_files_unreadable"] += len(local_payload.get("errors", []) or [])
                coverage["modality_routing_enabled"] = bool(
                    (local_payload.get("input") or {}).get("modality_routing_enabled")
                )
                excluded = local_payload.get("panels_excluded_from_deep_scan", []) or []
                conflicts = local_payload.get("modality_conflicts", []) or []
                if conflicts:
                    coverage["modality_conflicts"] = conflicts
                    coverage["modality_conflict_note"] = (
                        "Panels listed below have mixed experimental and schematic/chart declarations on "
                        "authoritative manifest edges. Deep image screening was retained; this is not clearance."
                    )
                if excluded:
                    coverage["panels_excluded_from_deep_scan"] = excluded
                    coverage["deep_scan_exclusion_note"] = (
                        "Panels listed below were excluded from local patch / same-image copy-move "
                        "screening because of their declared modality. Exclusion records audit scope "
                        "only; it is not clearance, approval, or evidence that those panels are correct."
                    )
                    coverage["modules_not_executed"].append(
                        "local patch / same-image copy-move screening on "
                        f"{len(excluded)} schematic/chart panel(s) (modality-aware exclusion; not a clean result)"
                    )
    else:
        coverage["modules_not_executed"].append("image screening (no image files supplied)")

    if has_files(package / "source_data", SOURCE_EXTS):
        coverage["modules_executed"].extend(["statistics_consistency", "pseudoreplication"])
        stats_payload = load_safe("stats_consistency_candidates.json")
        if stats_payload:
            coverage["source_tables_screened"] = len(stats_payload.get("files_screened", []) or [])
    else:
        coverage["modules_not_executed"].append("statistics screening (no source_data CSV/TSV/XLSX supplied)")

    if has_files(package, TEXT_EXTS):
        coverage["modules_executed"].append("package_internal_text_overlap")
    else:
        coverage["modules_not_executed"].append("text-overlap screening (no manuscript/text supplied)")

    if scan_profile == "quick":
        coverage["modules_not_executed"].append("external literature phrase search (skipped by quick scan profile)")
    elif external_provider:
        coverage["modules_executed"].append(f"external_literature_search ({external_provider})")
    else:
        coverage["modules_not_executed"].append(
            "external literature phrase search (offline: private internal audit, or no provider/fixture)"
        )

    coverage["modules_executed"].append("methodology_readiness_checklist")
    coverage["modules_executed"].append("writing_submission_readiness")
    coverage["modules_not_executed"].append(
        "methodology/reporting-standard compliance determination (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession): manual review required"
    )
    coverage["modules_not_executed"].append(
        "journal-specific writing, language, and reference correctness determination: manual review required"
    )

    for path in detector_outputs:
        payload = read_json(path)
        for error in payload.get("errors", []) or []:
            stage = payload.get("detector_name") or path.stem
            error_path = error.get("path") if isinstance(error, dict) else None
            label = f"{stage}: {error_path}" if error_path else str(stage)
            coverage["detector_failures"].append(label)
        for candidate in payload.get("candidates", []) or []:
            candidate_type = candidate.get("candidate_type")
            if candidate_type == "detector_execution_failure":
                stage = candidate.get("evidence", {}).get("stage") or candidate.get("candidate_id", "detector")
                coverage["detector_failures"].append(str(stage))
            elif candidate_type == "audit_coverage_gap":
                coverage["audit_coverage_gap"] = True

    return coverage


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


def run_pipeline(
    package: Path,
    mode: str,
    output_dir: Path,
    domains: str,
    case_id: str | None,
    scan_profile: str = "standard",
    external_literature_provider: str = "auto",
    external_literature_fixture: Path | None = None,
    claim_manifest: Path | None = None,
    compare_to: Path | None = None,
    reference_check_provider: str = "none",
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(package, mode, domains, output_dir)
    manifest_payload = read_json(manifest)
    audit_id = case_id or package.name
    snapshot = build_audit_snapshot(manifest_payload, audit_id, pyproject_version(ROOT))
    snapshot_path = output_dir / "audit_snapshot.json"
    write_qc_json(snapshot_path, snapshot)
    file_hash_manifest_path = output_dir / "file_hash_manifest.json"
    write_qc_json(file_hash_manifest_path, build_file_hash_manifest(snapshot))

    resolved_claim_manifest = find_claim_manifest(package, claim_manifest)
    claim_coverage = build_claim_coverage(package, resolved_claim_manifest)
    claim_coverage_path = output_dir / "claim_coverage.json"
    write_qc_json(claim_coverage_path, claim_coverage)
    claim_coverage_csv = output_dir / "claim_coverage.csv"
    write_claim_coverage_csv(claim_coverage_csv, claim_coverage)
    methodology_checklist = build_methodology_checklist(manifest_payload)
    methodology_checklist_path = output_dir / "methodology_checklist.json"
    write_json(methodology_checklist_path, methodology_checklist)
    methodology_checklist_csv = output_dir / "methodology_checklist.csv"
    write_methodology_checklist_csv(methodology_checklist_csv, methodology_checklist)
    writing_readiness = build_writing_readiness(package, reference_check_provider)
    writing_readiness_path = output_dir / "writing_readiness.json"
    write_json(writing_readiness_path, writing_readiness)
    writing_readiness_csv = output_dir / "writing_readiness.csv"
    write_writing_readiness_csv(writing_readiness_csv, writing_readiness)

    provenance_graph = build_provenance(package, manifest, output_dir)
    detector_outputs = []
    detector_outputs.extend(run_source_detectors(package, output_dir))
    detector_outputs.extend(run_image_detector(package, output_dir, provenance_graph, scan_profile))
    effective_external_provider = "none" if scan_profile == "quick" else external_literature_provider
    detector_outputs.extend(run_text_detectors(
        package,
        output_dir,
        mode,
        effective_external_provider,
        external_literature_fixture,
    ))
    if not detector_outputs:
        detector_outputs.append(write_audit_coverage_gap(package, output_dir))
    calibrated = run_calibrator(detector_outputs, mode, output_dir)
    resolved_provider = resolve_external_literature_provider(
        mode,
        effective_external_provider,
        external_literature_fixture or find_external_literature_fixture(package),
    )
    coverage = build_coverage(package, output_dir, detector_outputs, resolved_provider, scan_profile)
    coverage_path = output_dir / "coverage.json"
    write_json(coverage_path, coverage)
    report = run_report(
        manifest,
        calibrated,
        detector_outputs,
        mode,
        case_id,
        output_dir,
        coverage_path,
        claim_coverage_path,
        methodology_checklist_path,
        writing_readiness_path,
        scan_profile,
    )
    audit_summary = extract_audit_summary(report)
    audit_summary_path = output_dir / "AUDIT_JSON_SUMMARY.json"
    write_json(audit_summary_path, audit_summary)
    missing_materials_csv = output_dir / "missing_materials.csv"
    write_missing_materials_csv(missing_materials_csv, manifest_payload)
    verified_traceability_csv = output_dir / "verified_traceability.csv"
    write_verified_traceability_csv(verified_traceability_csv, audit_summary)
    unresolved_actions_csv = output_dir / "unresolved_actions.csv"
    action_rows = unresolved_action_rows(manifest_payload, audit_summary, claim_coverage)
    write_unresolved_actions_csv(
        unresolved_actions_csv,
        action_rows,
    )
    correction_plan_csv = output_dir / "correction_plan.csv"
    correction_plan_md = output_dir / "correction_plan.md"
    correction_rows = correction_plan_rows(action_rows)
    write_correction_plan_csv(correction_plan_csv, correction_rows)
    write_correction_plan_markdown(correction_plan_md, correction_rows)
    resolved_actions_csv = output_dir / "resolved_actions.csv"
    accepted_with_reason_csv = output_dir / "accepted_with_reason.csv"
    write_empty_action_tracker_csv(resolved_actions_csv)
    write_empty_action_tracker_csv(accepted_with_reason_csv)

    re_audit_diff: dict[str, Any] | None = None
    re_audit_diff_path: Path | None = None
    re_audit_diff_csv: Path | None = None
    if compare_to is not None:
        re_audit_diff = build_re_audit_diff(compare_to, output_dir)
        re_audit_diff_path = output_dir / "re_audit_diff.json"
        re_audit_diff_csv = output_dir / "re_audit_diff.csv"
        write_qc_json(re_audit_diff_path, re_audit_diff)
        write_re_audit_diff_csv(re_audit_diff_csv, re_audit_diff)

    qc_packet = export_submission_qc_packet(
        output_dir,
        manifest_payload,
        audit_summary,
        coverage,
        read_json(calibrated),
        snapshot,
        claim_coverage,
        methodology_checklist,
        writing_readiness,
        re_audit_diff,
    )

    result = {
        "package": str(package),
        "mode": mode,
        "scan_profile": scan_profile,
        "output_dir": str(output_dir),
        "manifest": str(manifest),
        "audit_snapshot": str(snapshot_path),
        "file_hash_manifest": str(file_hash_manifest_path),
        "claim_coverage": str(claim_coverage_path),
        "claim_coverage_csv": str(claim_coverage_csv),
        "methodology_checklist": str(methodology_checklist_path),
        "methodology_checklist_csv": str(methodology_checklist_csv),
        "writing_readiness": str(writing_readiness_path),
        "writing_readiness_csv": str(writing_readiness_csv),
        "missing_materials_csv": str(missing_materials_csv),
        "verified_traceability_csv": str(verified_traceability_csv),
        "unresolved_actions_csv": str(unresolved_actions_csv),
        "correction_plan_csv": str(correction_plan_csv),
        "correction_plan_md": str(correction_plan_md),
        "resolved_actions_csv": str(resolved_actions_csv),
        "accepted_with_reason_csv": str(accepted_with_reason_csv),
        "provenance_graph": str(provenance_graph),
        "detector_outputs": [str(path) for path in detector_outputs],
        "calibrated_findings": str(calibrated),
        "report": str(report),
        "audit_summary": str(audit_summary_path),
        "candidate_count": read_json(calibrated).get("candidate_count", 0),
        "finding_count": len(read_json(calibrated).get("findings", [])),
        "overall_risk": audit_summary.get("overall_risk"),
        "external_literature_provider": resolved_provider,
        "coverage": str(coverage_path),
        "submission_qc_packet": qc_packet,
    }
    if re_audit_diff_path is not None:
        result["re_audit_diff"] = str(re_audit_diff_path)
        result["re_audit_diff_csv"] = str(re_audit_diff_csv)
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
    parser.add_argument(
        "--scan-profile",
        choices=SCAN_PROFILES,
        default="standard",
        help=(
            "Runtime depth. quick keeps fast presentation-layer screens and skips expensive local-patch "
            "and external phrase search; standard is the default presubmission audit; deep uses stricter image thresholds."
        ),
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--domains", default="wetlab,animal,cell")
    parser.add_argument("--case-id")
    parser.add_argument(
        "--external-literature-provider",
        choices=EXTERNAL_LITERATURE_PROVIDERS,
        default="auto",
        help=(
            "External phrase-search provider. auto uses package fixtures when present, "
            "runs Europe PMC for external_public_material mode, and skips external search for private internal packages."
        ),
    )
    parser.add_argument(
        "--external-literature-fixture",
        type=Path,
        help="Deterministic fixture JSON for external_literature_search.py.",
    )
    parser.add_argument(
        "--claim-manifest",
        type=Path,
        help="Optional claim_manifest.csv linking manuscript claims to source data, raw records, analysis code, and protocols.",
    )
    parser.add_argument(
        "--compare-to",
        type=Path,
        help="Optional previous audit output directory for re-audit diff generation.",
    )
    parser.add_argument(
        "--reference-check-provider",
        choices=REFERENCE_CHECK_PROVIDERS,
        default="none",
        help="Optional DOI/reference metadata provider for writing-readiness checks. Default stays offline.",
    )
    args = parser.parse_args()

    package = args.package_dir.expanduser().resolve()
    if not package.exists() or not package.is_dir():
        raise SystemExit(f"Package directory not found: {package}")
    output_dir = (args.output_dir or (ROOT / "audit_outputs" / package.name)).expanduser().resolve()
    claim_manifest = args.claim_manifest.expanduser().resolve() if args.claim_manifest else None
    if claim_manifest is not None and not claim_manifest.is_file():
        raise SystemExit(f"Claim manifest not found: {claim_manifest}")
    compare_to = args.compare_to.expanduser().resolve() if args.compare_to else None
    if compare_to is not None and not compare_to.is_dir():
        raise SystemExit(f"Previous audit output directory not found: {compare_to}")
    result = run_pipeline(
        package,
        args.mode,
        output_dir,
        args.domains,
        args.case_id or package.name,
        args.scan_profile,
        args.external_literature_provider,
        args.external_literature_fixture.expanduser().resolve() if args.external_literature_fixture else None,
        claim_manifest,
        compare_to,
        args.reference_check_provider,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
