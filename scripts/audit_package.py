#!/usr/bin/env python3
"""Run the contract-first biomedical integrity audit pipeline for a package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.pipeline.common import (
    DetectorRunResult,
    EXECUTION_MODES,
    EXTERNAL_LITERATURE_PROVIDERS,
    MODES,
    REFERENCE_CHECK_PROVIDERS,
    ROOT,
    SCAN_PROFILES,
    resolve_external_literature_provider,
    run,
)
from scripts.pipeline import detectors as detector_stage
from scripts.pipeline import report as report_stage
from scripts.pipeline.coverage import build_coverage
from scripts.pipeline.detector_registry import DEFAULT_REGISTRY
from scripts.pipeline.detectors import run_detector, write_audit_coverage_gap, write_format_coverage_gaps
from scripts.pipeline.orchestrator import run_pipeline
from scripts.pipeline.report import extract_audit_summary


def run_source_detectors(package: Path, output_dir: Path) -> list[Path]:
    original = detector_stage.run_detector
    detector_stage.run_detector = run_detector
    try:
        return detector_stage.run_source_detectors(package, output_dir)
    finally:
        detector_stage.run_detector = original


def run_image_detector(
    package: Path,
    output_dir: Path,
    provenance_graph: Path,
    scan_profile: str = "standard",
    package_guardrails: dict[str, Any] | None = None,
) -> list[Path]:
    original = detector_stage.run_detector
    detector_stage.run_detector = run_detector
    try:
        return detector_stage.run_image_detector(package, output_dir, provenance_graph, scan_profile, package_guardrails)
    finally:
        detector_stage.run_detector = original


def run_text_detectors(
    package: Path,
    output_dir: Path,
    mode: str,
    external_literature_provider: str,
    external_literature_fixture: Path | None,
) -> list[Path]:
    original = detector_stage.run_detector
    detector_stage.run_detector = run_detector
    try:
        return detector_stage.run_text_detectors(
            package,
            output_dir,
            mode,
            external_literature_provider,
            external_literature_fixture,
        )
    finally:
        detector_stage.run_detector = original


def run_calibrator(detector_outputs: list[Path], mode: str, output_dir: Path) -> Path:
    original = report_stage.run
    report_stage.run = run
    try:
        return report_stage.run_calibrator(detector_outputs, mode, output_dir)
    finally:
        report_stage.run = original


def run_report(*args: object, **kwargs: object) -> Path:
    original = report_stage.run
    report_stage.run = run
    try:
        return report_stage.run_report(*args, **kwargs)
    finally:
        report_stage.run = original


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
            "copy-move, keypoint, splice-forensics triage, and external phrase search; standard is the "
            "default presubmission audit; deep uses stricter image thresholds."
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
    parser.add_argument(
        "--detector-registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help=(
            "Optional YAML registry for extension detectors that emit detector_output.schema.json. "
            "Use 'none' to disable extension-detector loading."
        ),
    )
    parser.add_argument(
        "--execution-mode",
        choices=EXECUTION_MODES,
        default="parallel",
        help=(
            "Pipeline scheduling. parallel runs independent intake and detector workstreams concurrently "
            "with deterministic merge order; sequential is a portable debugging/reproducibility fallback."
        ),
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
    detector_registry = None if str(args.detector_registry).lower() == "none" else args.detector_registry.expanduser().resolve()
    if detector_registry is not None and not detector_registry.is_file():
        raise SystemExit(f"Detector registry not found: {detector_registry}")
    try:
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
            detector_registry,
            args.execution_mode,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
