# Changelog

## Unreleased

### Added
- True-PDF benchmark starter with a compressed-stream PDF fixture and known-gap runner for PDF text extraction.
- Package-internal text overlap detector for manuscripts, supplements, prior drafts, thesis chapters, preprints, and lab-prior-paper folders.
- Section-aware text overlap risk calibration for methods boilerplate, disclosed thesis/preprint overlap, results overlap, and abstract/conclusion overlap.
- Synthetic text-overlap eval cases `case_025` through `case_030`, including methods boilerplate, disclosed thesis reuse, clean text, and prompt-injection controls.

### Changed
- True binary PDFs are now explicitly skipped by the text-overlap detector with a recorded extraction-gap error instead of being read as raw UTF-8 text.
- The default audit pipeline now runs text overlap screening when supported text files are present.
- CI key audit regressions now include local patch cases `case_020` through `case_024` and text-overlap cases `case_025` through `case_030`.

## v0.4.0 - Provenance-aware Local Patch Reuse Detection

### Added
- Provenance-aware local patch image reuse detector with evidence crop export.
- Local patch contextual calibration for cross-context figure reuse, declared traceability exclusions, and R1 unmapped figure-to-raw gaps.
- Synthetic cases `case_020` through `case_024` for local patch clone and negative-calibration scenarios.

## v0.3.2 - Release Hardening and Provenance Summaries

### Added
- GitHub Actions validation across Python 3.10, 3.11, and 3.12.
- Machine-readable `positive_provenance` and `traceability_gaps` in `AUDIT_JSON_SUMMARY`.
- Structured `figure_assembly/assembly_manifest.csv` and `.yaml` parsing, with CSV/YAML precedence over text manifests.
- Regression tests for risk-rule contextual tag coverage and structured manifest parsing.

### Changed
- `audit_outputs/` is ignored locally and uploaded as a CI artifact for key package regressions.

## v0.3.1 - Provenance-First Negative Calibration

### Added
- Provenance graph construction from package manifests, figure-source maps, and assembly manifests.
- Resource-node and provenance-edge contracts for package-level traceability.
- Provenance-aware contextual image calibration before risk capping.
- Positive traceability evidence reporting for declared figure-to-raw/source similarity.
- False-positive regression coverage for clean-control and prompt-injection packages.

### Changed
- `scripts/audit_package.py` now builds a provenance graph before image contextual joining.
- Declared figure-to-raw/source similarity is treated as `expected_traceability`, not image-reuse risk.
- Unmapped figure-to-raw/source similarity is capped as an `R1` traceability gap.

### Fixed
- Clean-control false positive where figure panels matching their own raw images could escalate to `R3`.
- Prompt-injection package image false positive caused by ordinary figure-to-raw similarity.

### Known Limitations
- Local patch single-package detection is not included in v0.3.2; it was added in v0.4.0.
- No text overlap, self-overlap, or plagiarism-style detector yet.
- No cross-paper image-reuse search.
- Synthetic eval packages still simplify image generation, PDF realism, and lab-record complexity.
