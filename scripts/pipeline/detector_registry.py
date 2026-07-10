"""YAML-backed extension detector registry.

The core pipeline keeps its curated built-in detector stages explicit. This
registry is for local or contributed extension detectors that already emit the
standard detector-output contract.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from scripts.pipeline.common import PYTHON, ROOT, has_files
from scripts.pipeline.detectors import run_detector, write_detector_failure


DEFAULT_REGISTRY = ROOT / "schemas" / "detector_registry.yaml"
ALLOWED_KEYS = {
    "name",
    "output",
    "command",
    "profiles",
    "modes",
    "run_if_any_suffix",
}
PLACEHOLDER_RE = re.compile(r"{([A-Za-z_][A-Za-z0-9_]*)}")
RESERVED_OUTPUT_PATHS = {
    ".biomed-audit-run.json",
    "audit-report.md",
    "audit_snapshot.json",
    "AUDIT_JSON_SUMMARY.json",
    "accepted_with_reason.csv",
    "assembly_links.json",
    "audit_coverage_candidates.json",
    "calibrated_findings.json",
    "channel_metadata_candidates.json",
    "claim_coverage.csv",
    "claim_coverage.json",
    "correction_plan.csv",
    "correction_plan.md",
    "coverage.json",
    "contextual_image_candidates.json",
    "contextual_image_failure_candidates.json",
    "docx_structure.json",
    "external_literature_candidates.json",
    "fcs_metadata_intake.json",
    "file_hash_manifest.json",
    "figure_source_links.json",
    "figure_source_map.json",
    "format_coverage_candidates.json",
    "global_image_candidates.json",
    "image_screening_inputs.json",
    "image_metadata.json",
    "intake_coverage_candidates.json",
    "key_embedded_images.json",
    "keypoint_contextual_candidates.json",
    "keypoint_contextual_failure_candidates.json",
    "keypoint_image_candidates.json",
    "local_patch_candidates.json",
    "local_patch_contextual_candidates.json",
    "local_patch_contextual_failure_candidates.json",
    "manifest.json",
    "methodology_checklist.csv",
    "methodology_checklist.json",
    "missing_materials.csv",
    "package_guardrail_candidates.json",
    "pdf_embedded_images.json",
    "pdf_structure.json",
    "pipeline_summary.json",
    "pptx_embedded_images.json",
    "pptx_structure.json",
    "prism_project_intake.json",
    "provenance_graph.json",
    "psd_preview_images.json",
    "pseudoreplication_candidates.json",
    "re_audit_diff.csv",
    "re_audit_diff.json",
    "re_audit_diff.md",
    "registered_detector_registry_candidates.json",
    "resolved_actions.csv",
    "same_image_copy_move_candidates.json",
    "splice_forensics_candidates.json",
    "START_HERE.md",
    "stats_consistency_candidates.json",
    "submission_qc_packet.zip",
    "text_overlap_candidates.json",
    "unresolved_actions.csv",
    "verified_traceability.csv",
    "workstreams.json",
    "writing_readiness.csv",
    "writing_readiness.json",
    "xlsx_structure.json",
}
RESERVED_OUTPUT_ROOTS = {
    ".cache",
    "evidence",
    "image_screening_package",
    "key_embedded_images",
    "pdf_embedded_images",
    "pptx_embedded_images",
    "psd_preview_images",
    "submission_qc_packet",
}


def load_detector_registry(path: Path) -> list[dict[str, Any]]:
    registry_path = path
    if not registry_path.exists():
        return []
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    detectors = payload.get("detectors", [])
    if not isinstance(detectors, list):
        raise ValueError(f"Detector registry {registry_path} must define detectors as a list")
    normalized = []
    for idx, item in enumerate(detectors, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Detector registry item {idx} must be a mapping")
        unknown = sorted(set(item) - ALLOWED_KEYS)
        if unknown:
            raise ValueError(f"Detector registry item {idx} has unsupported keys: {', '.join(unknown)}")
        name = str(item.get("name", "")).strip()
        output = str(item.get("output", "")).strip()
        command = item.get("command")
        if not name:
            raise ValueError(f"Detector registry item {idx} must define name")
        if not output:
            raise ValueError(f"Detector registry item {idx} must define output")
        if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
            raise ValueError(f"Detector registry item {idx} must define command as a non-empty list of strings")
        normalized.append(item)
    return normalized


def normalized_output_path(output_dir: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Registered detector output must stay inside output_dir: {value}")
    return output_dir / candidate


def normalized_output_relpath(value: str) -> str:
    return Path(value).as_posix()


def detector_enabled(detector: dict[str, Any], package: Path, mode: str, scan_profile: str) -> bool:
    modes = detector.get("modes")
    if modes and mode not in {str(item) for item in modes}:
        return False
    profiles = detector.get("profiles")
    if profiles and scan_profile not in {str(item) for item in profiles}:
        return False
    suffixes = detector.get("run_if_any_suffix")
    if suffixes:
        suffix_set = {str(item).lower() for item in suffixes}
        if not has_files(package, suffix_set):
            return False
    return True


def expand_command(
    command: list[str],
    *,
    package: Path,
    output_dir: Path,
    output: Path,
    mode: str,
    scan_profile: str,
    provenance_graph: Path | None,
) -> list[str]:
    mapping = {
        "python": PYTHON,
        "root": str(ROOT),
        "package": str(package),
        "output_dir": str(output_dir),
        "output": str(output),
        "mode": mode,
        "scan_profile": scan_profile,
        "provenance_graph": str(provenance_graph or ""),
    }
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in mapping:
            raise ValueError(
                f"Unsupported command placeholder {{{key}}}; supported placeholders are: "
                f"{', '.join(sorted(mapping))}"
            )
        return str(mapping[key])

    return [PLACEHOLDER_RE.sub(replace, part) for part in command]


def detector_registry_failure(
    package: Path,
    output_dir: Path,
    registry_path: Path,
    reason: str,
    suffix: str = "",
) -> Path:
    stage = "registered_detector_registry"
    if suffix:
        stage = f"{stage}_{suffix}"
    return write_detector_failure(
        stage,
        package,
        output_dir,
        [str(registry_path)],
        output_dir / "registered_detector_registry_candidates.json",
        reason,
    )


def run_registered_detectors(
    package: Path,
    output_dir: Path,
    *,
    mode: str,
    scan_profile: str,
    registry_path: Path | None = None,
    provenance_graph: Path | None = None,
) -> list[Path]:
    if registry_path is None:
        return []
    outputs: list[Path] = []
    failure_count = 0

    def add_failure(reason: str) -> Path:
        nonlocal failure_count
        failure_count += 1
        return detector_registry_failure(package, output_dir, registry_path, reason, f"{failure_count:02d}")

    try:
        detectors = load_detector_registry(registry_path)
    except Exception as exc:  # noqa: BLE001 - registry problems are audit coverage gaps.
        return [add_failure(str(exc))]

    enabled: list[tuple[dict[str, Any], Path, str]] = []
    seen_relpaths: set[str] = set()
    for detector in detectors:
        if not detector_enabled(detector, package, mode, scan_profile):
            continue
        try:
            output = normalized_output_path(output_dir, str(detector["output"]))
        except Exception as exc:  # noqa: BLE001 - path validation errors are coverage gaps.
            outputs.append(add_failure(str(exc)))
            continue
        relpath = normalized_output_relpath(str(detector["output"]))
        if relpath in RESERVED_OUTPUT_PATHS or Path(relpath).parts[0] in RESERVED_OUTPUT_ROOTS:
            outputs.append(add_failure(
                f"Registered detector output collides with a reserved pipeline artifact: {relpath}",
            ))
            continue
        if relpath in seen_relpaths:
            outputs.append(add_failure(
                f"Registered detector output is duplicated in the registry: {relpath}",
            ))
            continue
        seen_relpaths.add(relpath)
        enabled.append((detector, output, relpath))

    for detector, output, _relpath in enabled:
        name = str(detector["name"])
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            cmd = expand_command(
                list(detector["command"]),
                package=package,
                output_dir=output_dir,
                output=output,
                mode=mode,
                scan_profile=scan_profile,
                provenance_graph=provenance_graph,
            )
        except ValueError as exc:
            outputs.append(add_failure(str(exc)))
            continue
        result = run_detector(f"registered_{name}", package, output_dir, cmd, output)
        outputs.append(result.output)
    return outputs
