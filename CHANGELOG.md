# Changelog

## Unreleased

### Added
- Local web app package-prep tools: inspect recommended package folders, create the scaffold
  without overwriting supplied files, and write `figure_assembly/assembly_manifest.csv` declared
  figure-to-source rows with package-relative path and relation-type validation.
- 16-bit TIFF real-image benchmark coverage for microscopy-derived duplicate detection.
- Required CI OCR gate: GitHub Actions installs `tesseract-ocr` and runs the scanned-PDF benchmark without skip mode.
- Same-image copy-move screening in the local patch detector, including coordinate evidence crops and contextual calibration.
- Default-orchestrator external literature phrase-search integration with deterministic fixture auto-detection, external-public Europe PMC auto mode, query/result provenance, and R1 provider-gap reporting.
- Audit Coverage / scope reporting: every report and `AUDIT_JSON_SUMMARY` now records which modules executed, which were not run (including methodology compliance and offline external search), how many image panels were screened, how many image files were unreadable, and a scope note stating that no findings in a module is not a guarantee of correctness.
- User self-audit onboarding: `docs/self-audit-guide.md` (non-developer guide to preparing materials, running the audit, reading the report, and which conclusions are not permitted), two runnable example packages under `examples/` (`minimal_package/` and `full_presubmission_package/`) with a deterministic image generator, and entry-point links from the README, SKILL, and architecture docs. A regression test asserts both examples run, expose an Audit Coverage block, carry no misconduct verdict, and (for the full package) show verified figure-to-raw traceability.
- Archived Codex-orchestrated eval evidence under `evals/llm_runs/2026-06-30-codex-orchestrated/`: 30 synthetic cases scored, 30 passed, 0 boundary violations, and 0 risk-cap violations, with a manifest that states this is not an independent third-party blinded LLM run.

### Changed
- Image detectors now normalize high-bit-depth grayscale inputs before hashing or tile screening, preserving contrast instead of relying on default PIL RGB conversion.
- The live skill, README, and architecture docs now describe same-image copy-move coverage and privacy-aware external literature search through `scripts/audit_package.py`.
- Implementation-boundary alignment for statistics: removed the `benford_style` and `p_value_clustering` caps from `schemas/risk_rules.yaml` because no detector emits them, and updated README, SKILL, architecture, and the module checklist to state explicitly that Benford-style first-digit analysis and p-value clustering/distribution tests are manual checks, not automated detector outputs. Only p-value range/validity is screened automatically.
- Statistical weak-signal calibration is more conservative for small samples: terminal-digit, rounding, precision, and digit-preservation screens now require at least 8 comparable values by default, and integer-count mean/SD/n feasibility checks require n >= 6 and respect reported mean/SD precision. Synthetic weak-statistics cases were updated so evals no longer depend on tiny-n triggers.

### Fixed
- Digit-preservation statistical screening now passes the shared-pair threshold explicitly instead of referencing an undefined name, restoring linear-transform/time-stratified synthetic detections after the small-sample threshold update.
- Detector JSON `errors` are now surfaced in `audit_coverage.detector_failures`, so a detector that emits a contract-valid payload with per-file errors is reported as partial coverage rather than silently appearing clean.
- Manifest suppression hardening: an author-declared figure-to-figure same-field/same-membrane relationship can no longer clear a verifiable whole-image near-duplicate. Such pairs are now flagged as an unverifiable `manifest_conflict` (R3) requiring raw-record review, instead of being downgraded to a positive-traceability completeness gap. Declared figure-to-raw/source links and genuine local-patch same-field pairs are unaffected.
- External literature phrase-search now reports an `external_literature_search_gap` R1 coverage finding whenever any query fails, even if other queries returned matches, so partial external coverage is never presented as complete.
- Statistical time-column detection no longer matches time tokens inside unrelated identifiers (for example `CD4`, `CD8`, `CD3`, `CD45`), preventing immunology/marker columns from being misread as longitudinal timepoints.
- SD-versus-SEM consistency screening now tolerates ordinary reporting precision: the mismatch tolerance accounts for the rounding half-ULP of the reported SD and SEM, so legitimately rounded summary tables are no longer flagged as SD/SEM contradictions while genuine large deviations still fire.

## v0.5.0 - Local Self-Audit Web App

### Added
- Local-first FastAPI backend under `webapp/backend` that launches `scripts/audit_package.py` as a background subprocess and serves the generated audit artifacts without recomputing risk.
- React/Vite report viewer under `webapp/frontend` with Audit Coverage, R0-R4 risk register, positive provenance evidence, missing-materials panel, evidence crop rendering, bilingual labels, local history, and delete support.
- `python3 -m webapp` launcher plus `biomed-self-audit-webapp` console entry point.
- Safe artifact serving for evidence crops, guarded zip-package extraction, and backend tests that assert the API preserves CLI artifact risk/coverage fields.
- Frontend polish for the local self-audit app: modular React components, local font assets, light/dark themes, Markdown report rendering with sanitization, zip drag/drop upload, toast feedback, evidence lightbox, module/risk filters, structured evidence metrics, traceability gaps, and materials-reviewed panels while preserving the no-verdict integrity boundary.

### Changed
- Project version advanced to `0.5.0`; README files now include the local web-app entry point.
- Web app font imports now use Latin-only IBM Plex subsets while keeping Chinese system-font fallbacks, reducing the offline frontend bundle without changing the typography model.

## v0.4.2 - OCR, Real-Image, and External-Search Benchmarks

### Added
- OCR fallback for image-only/scanned PDFs when PyMuPDF, pytesseract, and the tesseract binary are available.
- Scanned-PDF benchmark package and runner, with required mode for environments that provide the OCR runtime.
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
