# Changelog

## Unreleased

### Added
- 16-bit TIFF real-image benchmark coverage for microscopy-derived duplicate detection.

### Changed
- Image detectors now normalize high-bit-depth grayscale inputs before hashing or tile screening, preserving contrast instead of relying on default PIL RGB conversion.

## v0.4.2 - OCR, Real-Image, and External-Search Benchmarks

### Added
- OCR fallback for image-only/scanned PDFs when PyMuPDF, pytesseract, and the tesseract binary are available.
- Scanned-PDF benchmark package and runner, with CI enforcing the OCR path.
- Real-microscopy-image benchmark based on a public-domain National Cancer Institute image, replacing one purely toy benchmark path with a real image asset.
- External literature/library phrase-search detector with Europe PMC, Crossref, and fixture-backed CI modes.

### Changed
- Validation now runs the real-image benchmark and locally skips the scanned-PDF benchmark only when OCR runtime dependencies are unavailable.
- The scanned-PDF benchmark can be run in required mode by omitting `--skip-if-unavailable`.

## v0.4.1 - Intake and Reliability Hardening

### Added
- Machine-readable true-PDF text extraction for package-internal overlap screening, backed by a compressed-stream PDF fixture.
- Package-internal text overlap detector for manuscripts, supplements, prior drafts, thesis chapters, preprints, and lab-prior-paper folders.
- Section-aware text overlap risk calibration for methods boilerplate, disclosed thesis/preprint overlap, results overlap, and abstract/conclusion overlap.
- Synthetic text-overlap eval cases `case_025` through `case_030`, including methods boilerplate, disclosed thesis reuse, clean text, and prompt-injection controls.
- Script-baseline audit-output assertions for CI risk ranges and required finding tags.
- Explicit `audit_coverage_gap` R1 finding when no detector can run on a supplied package.
- Detector failure isolation: non-zero detector exits or invalid detector JSON now produce `detector_execution_failure` R1 findings while preserving other module outputs.
- XLSX source-data intake for statistical consistency and pseudoreplication screening.
- Release metadata guardrail requiring the `pyproject.toml` version to have a matching changelog entry.

### Changed
- Figure-to-figure `declared_derived_from` manifest rows no longer clear image-reuse findings as positive traceability.
- True binary PDFs are extracted as machine-readable text when possible instead of being skipped or read as raw UTF-8 bytes.
- Censored or bounded numeric values such as `<5`, `<=0.01`, `>10`, or `>=8` are no longer treated as exact observations in statistical forensic screens.
- The default audit pipeline now runs text overlap screening when supported text files are present.
- Contract validation now fails closed when `jsonschema` is unavailable instead of silently using a partial fallback.
- R3/R4 candidates missing benign explanations, resolving materials, or recommended actions are capped to R2 instead of having generic text auto-filled.
- Risk-rule configuration now rejects unsupported safety keys, applies external `missing_source_data_max`, and honors R0 `report_as: positive_evidence` routing without hiding mixed risk candidates.
- The risk calibrator now rejects legacy hand-written findings payloads; inputs must satisfy the detector-output contract.
- Source-data availability gates are aligned to supported detector inputs: CSV, TSV, and XLSX.
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
