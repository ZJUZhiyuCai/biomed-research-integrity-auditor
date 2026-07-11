"""Detector execution and detector-coverage candidate helpers."""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import Any

from calibrators.contract_validation import validate_instance
from scripts.pipeline.common import (
    DETECTOR_SCHEMA,
    DOCUMENT_CONTAINER_EXTS,
    DetectorRunResult,
    IMAGE_EXTS,
    LEGACY_SOURCE_EXTS,
    OPAQUE_ASSEMBLY_CONTAINER_EXTS,
    PDF_IMAGE_CONTAINER_CATEGORIES,
    PYTHON,
    ROOT,
    SOURCE_EXTS,
    TEXT_EXTS,
    VENDOR_RAW_IMAGE_CONTAINER_EXTS,
    command_display,
    find_external_literature_fixture,
    has_files,
    read_json,
    resolve_external_literature_provider,
    stage_slug,
    text_tail,
    write_json,
)


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
    expected_output.parent.mkdir(parents=True, exist_ok=True)
    expected_output.unlink(missing_ok=True)
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


def append_contextual_or_raw(
    outputs: list[Path],
    raw_result: DetectorRunResult,
    contextual_result: DetectorRunResult,
) -> None:
    if contextual_result.ok:
        outputs.append(contextual_result.output)
        return
    outputs.append(raw_result.output)
    outputs.append(contextual_result.output)


INTAKE_COVERAGE_ARTIFACTS = (
    "xlsx_structure.json",
    "prism_project_intake.json",
    "fcs_metadata_intake.json",
    "docx_structure.json",
    "pdf_structure.json",
    "pdf_embedded_images.json",
    "pptx_structure.json",
    "pptx_embedded_images.json",
    "key_embedded_images.json",
    "psd_preview_images.json",
    "image_metadata.json",
)


def intake_error_location(package: Path, artifact_name: str, error: Any) -> str:
    if not isinstance(error, dict):
        return artifact_name
    raw_path = error.get("path")
    if not isinstance(raw_path, str):
        return artifact_name
    raw_path = raw_path.strip()
    if not raw_path or "\x00" in raw_path:
        return artifact_name
    try:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = package / candidate
        relative = candidate.resolve().relative_to(package.resolve())
        if relative == Path("."):
            return artifact_name
        return relative.as_posix()
    except (OSError, RuntimeError, ValueError):
        return artifact_name


def write_intake_coverage_gaps(package: Path, output_dir: Path) -> Path | None:
    candidates: list[dict[str, Any]] = []
    for artifact_name in INTAKE_COVERAGE_ARTIFACTS:
        artifact = output_dir / artifact_name
        payload = read_json(artifact) if artifact.is_file() else None
        if not payload:
            continue
        for error in payload.get("errors", []) or []:
            detail = error if isinstance(error, dict) else {"error": str(error)}
            message = str(detail.get("error") or detail.get("reason") or "intake extraction failed")
            candidates.append({
                "candidate_id": f"AUDIT-INTAKE-{len(candidates) + 1:04d}",
                "detector": "audit.intake_coverage",
                "candidate_type": "audit_coverage_gap",
                "locations": [intake_error_location(package, artifact_name, error)],
                "finding_type": "material intake extraction gap",
                "evidence": {
                    "gap_type": "intake_extraction_failed",
                    "artifact": artifact_name,
                    "stage": str(detail.get("stage", "")),
                    "message": message,
                },
                "evidence_strength": "weak_signal",
                "risk_suggestion": "R1_max",
                "risk_cap_tags": ["audit_coverage_gap", "completeness_gap", "intake_extraction_failed"],
                "benign_explanations": [
                    "the supplied file may be valid but use a container feature or encoding not supported by this intake extractor",
                    "an equivalent machine-readable export may exist outside the supplied package",
                ],
                "required_materials": [
                    "a machine-readable export of the affected material",
                    "manual review of the affected file until automated intake can be repeated",
                ],
                "recommended_action": (
                    "Review the intake error, provide a supported export where possible, and do not treat the affected material as screened."
                ),
                "requires_contextual_calibration": True,
            })
    if not candidates:
        return None
    output = output_dir / "intake_coverage_candidates.json"
    write_json(output, {
        "detector_name": "audit.intake_coverage",
        "detector_version": "0.1.0",
        "input": {"package": str(package)},
        "candidates": candidates,
        "errors": [],
    })
    validate_detector(output)
    return output


def supplementary_source_table_candidates(package: Path) -> list[Path]:
    candidates = []
    for item in sorted(package.rglob("*")):
        if item.is_symlink() or not item.is_file() or item.suffix.lower() not in SOURCE_EXTS:
            continue
        try:
            relative = item.relative_to(package)
        except ValueError:
            continue
        parts = {part.lower() for part in relative.parts[:-1]}
        name = item.name.lower()
        if "source_data" in parts:
            continue
        if name.startswith("moesm") or parts.intersection({"supplementary", "supplemental", "supplement", "supplements"}):
            candidates.append(item)
    return candidates


def run_source_detectors(package: Path, output_dir: Path) -> list[Path]:
    source_dir = package / "source_data"
    outputs: list[Path] = []
    stats_inputs: list[Path] = []
    if has_files(source_dir, SOURCE_EXTS):
        stats_inputs.append(source_dir)
    stats_inputs.extend(supplementary_source_table_candidates(package))
    if not stats_inputs:
        return outputs

    stats_output = output_dir / "stats_consistency_candidates.json"
    result = run_detector("stats_consistency", package, output_dir, [
        PYTHON,
        "skill/biomed-research-integrity-auditor/scripts/stats_consistency_check.py",
        *[str(path) for path in stats_inputs],
        "--output",
        str(stats_output),
    ], stats_output)
    outputs.append(result.output)

    if has_files(source_dir, SOURCE_EXTS):
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


DERIVED_IMAGE_ARTIFACTS = (
    ("pdf_embedded_images.json", "figures/_derived_pdf_embedded"),
    ("pptx_embedded_images.json", "figures/_derived_pptx_embedded"),
    ("key_embedded_images.json", "figures/_derived_keynote_embedded"),
    ("psd_preview_images.json", "figures/_derived_psd_preview"),
)


def derived_image_records(output_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for artifact_name, target_prefix in DERIVED_IMAGE_ARTIFACTS:
        artifact = output_dir / artifact_name
        if not artifact.is_file():
            continue
        try:
            payload = read_json(artifact)
        except Exception:
            continue
        for item in payload.get("images", []) or []:
            output_path = str(item.get("output_path", ""))
            if not output_path:
                continue
            output_rel = Path(output_path)
            if output_rel.is_absolute() or ".." in output_rel.parts:
                continue
            source = output_dir / output_rel
            if not source.is_file() or source.suffix.lower() not in IMAGE_EXTS:
                continue
            records.append({
                "artifact": artifact_name,
                "source": source,
                "source_output_path": output_path,
                "target_relative_path": str(Path(target_prefix) / output_rel),
                "source_container": (
                    item.get("source_pdf")
                    or item.get("source_pptx")
                    or item.get("source_key")
                    or item.get("source_psd")
                    or ""
                ),
                "page": item.get("page", ""),
                "width": item.get("width", ""),
                "height": item.get("height", ""),
            })
    return records


def prepare_image_screening_root(package: Path, output_dir: Path) -> Path:
    """Build an output-local image-screening package when derived images exist."""
    derived_records = derived_image_records(output_dir)
    if not derived_records:
        return package

    screening_root = output_dir / "image_screening_package"
    if screening_root.exists():
        shutil.rmtree(screening_root)
    screening_root.mkdir(parents=True, exist_ok=True)

    original_records: list[dict[str, Any]] = []
    for source in sorted(package.rglob("*")):
        if source.is_symlink() or not source.is_file() or source.suffix.lower() not in IMAGE_EXTS:
            continue
        rel = source.relative_to(package)
        target = screening_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        original_records.append({
            "source_path": rel.as_posix(),
            "target_relative_path": rel.as_posix(),
        })

    copied_derived: list[dict[str, Any]] = []
    for record in derived_records:
        target_rel = Path(str(record["target_relative_path"]))
        target = screening_root / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(record["source"], target)
        copied_derived.append({
            key: value
            for key, value in record.items()
            if key != "source"
        })

    write_json(output_dir / "image_screening_inputs.json", {
        "schema_version": "0.1.0",
        "input_package": str(package),
        "screening_root": str(screening_root),
        "original_images": original_records,
        "derived_images": copied_derived,
        "original_image_count": len(original_records),
        "derived_image_count": len(copied_derived),
        "scope_note": (
            "Image detectors screened an output-local package containing original supplied images plus "
            "presentation-layer images exported from PDFs/PPTX/Keynote/PSD. Derived images are screening "
            "inputs only; they are not raw records or provenance proof."
        ),
    })
    return screening_root


def run_image_detector(
    package: Path,
    output_dir: Path,
    provenance_graph: Path,
    scan_profile: str = "standard",
    package_guardrails: dict[str, Any] | None = None,
) -> list[Path]:
    if package_guardrails and package_guardrails.get("image_screening_blocked"):
        return []
    image_root = prepare_image_screening_root(package, output_dir)
    if not has_files(image_root, IMAGE_EXTS):
        return []

    outputs: list[Path] = []
    image_output = output_dir / "global_image_candidates.json"
    global_cmd = [
        PYTHON,
        "detectors/image/global_near_duplicate.py",
        str(image_root),
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
            "--screening-inputs",
            str(output_dir / "image_screening_inputs.json"),
            "--output",
            str(contextual_output),
        ], contextual_output)
        append_contextual_or_raw(outputs, global_result, contextual_result)
    else:
        outputs.append(global_result.output)

    channel_metadata_output = output_dir / "channel_metadata_candidates.json"
    channel_metadata_result = run_detector("channel_metadata", package, output_dir, [
        PYTHON,
        "detectors/image/channel_metadata_consistency.py",
        str(package),
        "--provenance",
        str(provenance_graph),
        "--metadata",
        str(output_dir / "image_metadata.json"),
        "--output",
        str(channel_metadata_output),
    ], channel_metadata_output)
    outputs.append(channel_metadata_result.output)

    if scan_profile == "quick":
        return outputs

    splice_output = output_dir / "splice_forensics_candidates.json"
    splice_cmd = [
        PYTHON,
        "detectors/image/splice_forensics_triage.py",
        str(image_root),
        "--output",
        str(splice_output),
    ]
    if scan_profile == "deep":
        splice_cmd.extend([
            "--ela-z-threshold",
            "6.0",
            "--noise-z-threshold",
            "6.0",
            "--max-images",
            "500",
        ])
    splice_result = run_detector("splice_forensics", package, output_dir, splice_cmd, splice_output)
    outputs.append(splice_result.output)

    keypoint_output = output_dir / "keypoint_image_candidates.json"
    keypoint_cmd = [
        PYTHON,
        "detectors/image/keypoint_geometric_match.py",
        str(image_root),
        "--provenance",
        str(provenance_graph),
        "--output",
        str(keypoint_output),
    ]
    if scan_profile == "deep":
        keypoint_cmd.extend([
            "--max-dimension",
            "1400",
            "--min-inliers",
            "18",
            "--min-inlier-ratio",
            "0.20",
            "--max-pair-comparisons",
            "5000",
        ])
    keypoint_result = run_detector("keypoint_image", package, output_dir, keypoint_cmd, keypoint_output)

    if keypoint_result.ok:
        keypoint_contextual_output = output_dir / "keypoint_contextual_candidates.json"
        keypoint_contextual_result = run_detector("keypoint_contextual", package, output_dir, [
            PYTHON,
            "calibrators/contextual_joiner.py",
            "--input",
            str(keypoint_output),
            "--package",
            str(package),
            "--provenance",
            str(provenance_graph),
            "--screening-inputs",
            str(output_dir / "image_screening_inputs.json"),
            "--output",
            str(keypoint_contextual_output),
        ], keypoint_contextual_output)
        append_contextual_or_raw(outputs, keypoint_result, keypoint_contextual_result)
    else:
        outputs.append(keypoint_result.output)

    local_patch_output = output_dir / "local_patch_candidates.json"
    local_patch_cmd = [
        PYTHON,
        "detectors/image/local_patch_reuse.py",
        str(image_root),
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
            "--screening-inputs",
            str(output_dir / "image_screening_inputs.json"),
            "--output",
            str(local_patch_contextual_output),
        ], local_patch_contextual_output)
        append_contextual_or_raw(outputs, local_patch_result, local_patch_contextual_result)
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
    else:
        cmd.extend([
            "--cache-dir",
            str(output_dir / ".cache" / "external_literature"),
            "--retries",
            "1",
        ])
    external_result = run_detector("external_literature_search", package, output_dir, cmd, external_output)
    outputs.append(external_result.output)
    return outputs


def write_audit_coverage_gap(package: Path, output_dir: Path) -> Path:
    files = [path for path in sorted(package.rglob("*")) if not path.is_symlink() and path.is_file()]
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


def unsupported_format_groups(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}

    def add(kind: str, file_item: dict[str, Any], message: str, action: str, exports: list[str]) -> None:
        group = groups.setdefault(kind, {
            "kind": kind,
            "message": message,
            "recommended_action": action,
            "recommended_exports": exports,
            "files": [],
            "extensions": set(),
            "categories": set(),
        })
        group["files"].append(str(file_item.get("path", "")))
        group["extensions"].add(str(file_item.get("extension", "")).lower())
        group["categories"].add(str(file_item.get("category", "")))

    for file_item in manifest.get("files", []) or []:
        path = str(file_item.get("path", ""))
        category = str(file_item.get("category", ""))
        extension = str(file_item.get("extension", "")).lower()
        if not path:
            continue
        if extension in DOCUMENT_CONTAINER_EXTS and category in {"manuscript", "supplementary", "protocols"}:
            add(
                "document_text_container_not_screened",
                file_item,
                "Legacy Word document containers are inventoried but not text-screened by the current automated text detectors.",
                "Save the current manuscript/protocol as DOCX, PDF with extractable text, or plain text and keep the original document for records.",
                ["DOCX", "PDF with extractable text", "TXT/MD text export"],
            )
        elif extension == ".xls" and category in {"source_data", "statistics_code", "protocols"}:
            add(
                "legacy_excel_source_not_screened",
                file_item,
                "Legacy .xls workbooks are inventoried but not parsed by the current source-data detectors.",
                "Export each relevant sheet to CSV/TSV or modern XLSX, then re-run the audit.",
                ["CSV/TSV per sheet", "XLSX"],
            )
        elif extension == ".pdf" and category in PDF_IMAGE_CONTAINER_CATEGORIES:
            add(
                "pdf_embedded_figures_not_image_screened",
                file_item,
                "PDF figure/supplement containers may contain presentation-layer embedded panels. The audit can export embedded raster images for intake review, but these exports are not raw records or provenance proof.",
                "Provide raw/uncropped images or original panel exports alongside the PDF-derived presentation images before treating image provenance as complete.",
                ["raw or uncropped image files", "original PNG/JPG/TIFF panel exports"],
            )
        elif extension in OPAQUE_ASSEMBLY_CONTAINER_EXTS and category == "figure_assembly":
            add(
                "opaque_figure_assembly_project_requires_export",
                file_item,
                "Figure-assembly project containers may contain layered or presentation-level panels that are not fully parsed as provenance records by the automated audit.",
                "Export final figure panels to PNG/JPG/TIFF, provide raw/uncropped images, and keep the original assembly project for manual review.",
                ["PNG/JPG/TIFF panel exports", "raw or uncropped image files", "manual review of the original assembly project"],
            )
        elif extension in VENDOR_RAW_IMAGE_CONTAINER_EXTS and category == "raw_images":
            add(
                "vendor_raw_image_container_requires_metadata_export",
                file_item,
                "Vendor microscopy raw containers are inventoried as raw-image records, but the automated image metadata intake cannot parse their channel/Z-stack acquisition metadata without a supported export.",
                "Export OME-TIFF or channel/Z metadata sidecars from the microscope software or Bio-Formats, and keep the original vendor raw container for manual review.",
                ["OME-TIFF export", "channel/Z-stack metadata sidecar", "manual review of the original vendor raw container"],
            )

    result: list[dict[str, Any]] = []
    for group in groups.values():
        result.append({
            "kind": group["kind"],
            "message": group["message"],
            "recommended_action": group["recommended_action"],
            "recommended_exports": group["recommended_exports"],
            "files": sorted(group["files"]),
            "extensions": sorted(item for item in group["extensions"] if item),
            "categories": sorted(item for item in group["categories"] if item),
        })
    return sorted(result, key=lambda item: item["kind"])


def write_format_coverage_gaps(package: Path, output_dir: Path, manifest: dict[str, Any]) -> Path | None:
    groups = unsupported_format_groups(manifest)
    if not groups:
        return None

    candidates = []
    for idx, group in enumerate(groups, start=1):
        files = group["files"]
        candidates.append({
            "candidate_id": f"AUDIT-FORMAT-{idx:04d}",
            "detector": "audit.format_coverage",
            "candidate_type": "audit_coverage_gap",
            "locations": files,
            "evidence": {
                "gap_type": group["kind"],
                "message": group["message"],
                "files": files,
                "extensions": group["extensions"],
                "categories": group["categories"],
                "recommended_exports": group["recommended_exports"],
                "screened_by_current_detectors": False,
            },
            "evidence_strength": "weak_signal",
            "risk_suggestion": "R1_max",
            "risk_cap_tags": ["audit_coverage_gap", "completeness_gap", group["kind"]],
            "benign_explanations": [
                "The files may be valid records, but they require export or manual review before the automated modules can screen them.",
                "Equivalent supported exports may already exist elsewhere in the package; this item records that the listed containers themselves were not parsed.",
            ],
            "required_materials": [
                *group["recommended_exports"],
                "manual confirmation that each listed container is either duplicated by a supported export or intentionally out of scope",
            ],
            "recommended_action": group["recommended_action"],
            "requires_contextual_calibration": True,
        })

    payload = {
        "detector_name": "audit.format_coverage",
        "detector_version": "0.1.0",
        "input": {
            "package": str(package),
            "unsupported_relevant_format_groups": len(groups),
            "unsupported_relevant_file_count": sum(len(group["files"]) for group in groups),
        },
        "candidates": candidates,
        "errors": [],
    }
    output = output_dir / "format_coverage_candidates.json"
    write_json(output, payload)
    validate_detector(output)
    return output
