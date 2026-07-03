"""Top-level audit pipeline orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.methodology_checklist import (
    build_methodology_checklist,
    write_methodology_checklist_csv,
)
from scripts.pipeline.common import (
    ROOT,
    find_external_literature_fixture,
    read_json,
    resolve_external_literature_provider,
    write_json,
)
from scripts.pipeline.coverage import build_coverage
from scripts.pipeline.detectors import (
    run_image_detector,
    run_source_detectors,
    run_text_detectors,
    write_audit_coverage_gap,
    write_format_coverage_gaps,
)
from scripts.pipeline.guardrails import (
    scan_package_guardrails,
    write_package_guardrail_candidates,
)
from scripts.pipeline.intake import (
    build_docx_structure,
    build_fcs_metadata_intake,
    build_image_metadata,
    build_key_embedded_images,
    build_manifest,
    build_pdf_embedded_images,
    build_pdf_structure,
    build_pptx_embedded_images,
    build_pptx_structure,
    build_prism_project_intake,
    build_provenance,
    build_psd_preview_images,
    build_xlsx_structure,
)
from scripts.pipeline.report import (
    extract_audit_summary,
    run_calibrator,
    run_report,
    write_start_here,
)
from scripts.submission_qc import (
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
    write_json as write_qc_json,
    write_missing_materials_csv,
    write_re_audit_diff_csv,
    write_re_audit_diff_markdown,
    write_unresolved_actions_csv,
    write_verified_traceability_csv,
)
from scripts.writing_readiness_check import (
    build_writing_readiness,
    write_csv as write_writing_readiness_csv,
)


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
    package_guardrails = scan_package_guardrails(package)
    package_guardrail_output = write_package_guardrail_candidates(package, output_dir, package_guardrails)
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
    build_xlsx_structure(package, output_dir)
    build_prism_project_intake(package, output_dir)
    build_fcs_metadata_intake(package, output_dir)
    build_docx_structure(package, output_dir)
    build_pdf_structure(package, output_dir)
    build_pdf_embedded_images(package, output_dir)
    build_pptx_structure(package, output_dir)
    build_pptx_embedded_images(package, output_dir)
    build_key_embedded_images(package, output_dir)
    build_psd_preview_images(package, output_dir)
    if not package_guardrails.get("image_screening_blocked"):
        build_image_metadata(package, output_dir)

    provenance_graph = build_provenance(package, manifest, output_dir)
    detector_outputs = []
    if package_guardrail_output is not None:
        detector_outputs.append(package_guardrail_output)
    detector_outputs.extend(run_source_detectors(package, output_dir))
    detector_outputs.extend(run_image_detector(package, output_dir, provenance_graph, scan_profile, package_guardrails))
    effective_external_provider = "none" if scan_profile == "quick" else external_literature_provider
    detector_outputs.extend(run_text_detectors(
        package,
        output_dir,
        mode,
        effective_external_provider,
        external_literature_fixture,
    ))
    format_coverage = write_format_coverage_gaps(package, output_dir, manifest_payload)
    if format_coverage is not None:
        detector_outputs.append(format_coverage)
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
    re_audit_diff_md: Path | None = None
    if compare_to is not None:
        re_audit_diff = build_re_audit_diff(compare_to, output_dir)
        re_audit_diff_path = output_dir / "re_audit_diff.json"
        re_audit_diff_csv = output_dir / "re_audit_diff.csv"
        re_audit_diff_md = output_dir / "re_audit_diff.md"
        write_qc_json(re_audit_diff_path, re_audit_diff)
        write_re_audit_diff_csv(re_audit_diff_csv, re_audit_diff)
        write_re_audit_diff_markdown(re_audit_diff_md, re_audit_diff)

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
    start_here = write_start_here(output_dir, package, qc_packet, audit_summary)

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
        "start_here": str(start_here),
    }
    if re_audit_diff_path is not None:
        result["re_audit_diff"] = str(re_audit_diff_path)
        result["re_audit_diff_csv"] = str(re_audit_diff_csv)
        result["re_audit_diff_md"] = str(re_audit_diff_md)
    positive_count = 0
    for path in detector_outputs:
        payload = read_json(path)
        positive_count += len(payload.get("positive_evidence", []) or [])
    result["positive_provenance_count"] = positive_count
    write_json(output_dir / "pipeline_summary.json", result)
    return result
