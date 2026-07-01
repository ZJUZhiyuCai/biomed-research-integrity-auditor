# Changelog

## Unreleased

### Added
- Local patch / same-image copy-move screening now uses a NumPy-backed normalized
  cross-correlation path and records explicit tile/comparison budget limits. If
  a local image run is capped before all tile pairs are examined, the detector emits
  an R1 `audit_coverage_gap` rather than letting partial screening look complete.
- Human reports and `AUDIT_JSON_SUMMARY.audit_coverage` now include an explicit image-screening
  boundary: automated checks performed, manipulation classes not covered by current image
  detectors, and the reminder that no image finding is not complete image-forensics clearance.

### Fixed
- Decimal-comma numeric parsing in the statistics detector: unambiguous European decimals such
  as `1,5` and `0,049` now parse as `1.5` and `0.049`; semicolon-delimited CSV exports are
  detected; ambiguous single-comma values such as `1,234` are left unparsed and reported as an
  R1 numeric-format coverage gap instead of being silently interpreted at the wrong magnitude.
- Contextual image joining now preserves local-patch coverage-gap candidates instead of treating
  them as similarity candidates with no edges and dropping them.

## v0.6.2 - Local Usability and Coverage Hardening

### Added
- User-facing safety hardening for human reports: Quick Read now surfaces open actions, unreadable
  image counts, modules not run, and detector activity (`raw candidates -> positive provenance ->
  findings`), while Submission Readiness explicitly states when open actions mean the package is
  not yet ready for a complete self-audit.
- Unreadable image files now generate an R1 `provide_materials` action and appear in the report's
  Materials Needed section, so corrupt or unsupported image exports cannot be mistaken for clean
  image screening.
- Plain-language module notes in Audit Coverage explain what each executed screening module did.
- Webapp overview counters now include unresolved actions, and the R-level pill has an inline
  scope explanation.
- `make run` source-checkout launcher for non-developer local webapp use: it prepares `.venv`,
  installs dependencies, builds the frontend, starts the local server, and opens the browser.
- Assembly-manifest parser warnings now appear in Audit Coverage, Materials Needed, and the
  presubmission action queue instead of remaining only in `assembly_links.json`.
- Modality-aware panel routing for local patch / same-image copy-move screening: schematic and
  chart panels declared in `assembly_manifest.csv` are excluded from deep image screening, with
  explicit coverage records that exclusion is scope control rather than clearance. Legacy modality
  labels such as `blot`, `gel`, and `image` normalize to `western_blot` or `other`. Mixed modality
  declarations on the same panel default to deep scan with an explicit `modality_conflicts` record;
  only authoritative expected-traceability edges may control routing.
- Webapp manifest builder modality dropdown aligned to the canonical panel types.
- Scan profiles for the default audit entrypoint: `--scan-profile quick|standard|deep`.
  Quick runs skip expensive local-patch/copy-move deep image screening and external phrase search,
  and coverage records those scope limits explicitly.
- Presubmission action queue in the human report and `AUDIT_JSON_SUMMARY`, grouping follow-up
  work as must-resolve, missing-material, clarify/disclose, and low-priority review items.
- Team correction tracker exports: `resolved_actions.csv` and `accepted_with_reason.csv`, plus
  owner/status/human-note/accepted-reason fields in `unresolved_actions.csv`.
- Webapp scan-profile selection wired through to the local CLI backend.
- Product-facing console entry points: `biomed-audit`, `biomed-audit-diff`, and
  `biomed-audit-web`, while retaining existing script/module fallbacks.
- Expanded the public-data smoke benchmark to download all current ORI public image-forensics
  JPG samples, not just the original three-image subset.
- `evaluation_role` for PPPR finding labels, separating metric-bearing `recall_label` entries
  from `scope_gap` and `reference_only` records.
- A conservative low-contrast autocontrast probe for same-image copy-move screening, guarded by
  same-displacement tile clustering and positive/negative synthetic regression tests.
- Structured methodology/reporting-standard readiness output (`methodology_checklist.json` and
  `.csv`) covering wet-lab, animal, clinical, cell, flow, and omics manual-review prompts, with
  bilingual report and webapp panels.
- Separate Writing & Submission Readiness output (`writing_readiness.json` / `.csv`) for
  language placeholders, generic submission-file prompts, and opt-in DOI/reference metadata
  review. This module is rendered separately and is not merged into integrity findings.
- Webapp submission workspace surfaces claim coverage, unresolved action trackers, re-audit diffs,
  correction-plan trackers, QC-packet download links, and writing-readiness prompts.
- Frame-level screening for multi-frame TIFF-like image files in global near-duplicate and local
  patch/copy-move detectors.
- Sample-gated weak Benford-style first-digit and p-value-clustering prompts, capped as weak
  statistical triage signals.
- Release artifact tooling: `make release-artifacts`, `scripts/build_release_artifacts.py`,
  GitHub Release/frontend-smoke workflow templates, and Homebrew/macOS packaging templates.
- External literature search query provenance now records provider, query timestamp, result count,
  and per-query failure count for every executed external query.

### Changed
- Project version advanced to `0.6.2`.
- Structured assembly manifests now reject unsupported `relation_type` values with warnings instead
  of treating arbitrary strings as high-confidence expected traceability.
- The report no longer shows a misleading Quick Read row named `Coverage gap: no`; scope limits are
  represented as modules not run and detector activity instead.
- The report label for `figure_assembly` now refers to project files (`PPT/PS/AI`) rather than
  implying that an assembly manifest satisfies that category.
- Action Queue report tables now label owners as suggested owners.
- Human-facing CSV exports in the submission QC packet and webapp-created assembly manifests now
  neutralize spreadsheet formula-like cells, and webapp audit endpoints reject malformed audit IDs
  before filesystem lookup.
- Uploaded webapp zip packages now reject symlink members in addition to unsafe absolute or
  traversal paths.
- `evals/run_script_baseline.py` now runs all synthetic cases by default when neither `--case` nor
  `--package` is supplied, matching the downstream audit-output assertion workflow.
- Python support metadata now matches the documented and CI-tested requirement: Python 3.10+.
- The archived `public_smoke_2026-06-30` result now reports 13 ORI images screened, 2/2
  detector-scope ORI recall labels hit, and two retained ORI scope gaps for future
  same-section/low-contrast image recall work.
- Same-image copy-move screening preserves the existing luma path while applying the stricter
  displacement-cluster requirement only to low-contrast enhanced tiles.
- Audit coverage now records the methodology readiness checklist as executed while still stating
  that ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics compliance determinations require manual review.
- The `deep` scan profile now applies stricter image similarity parameters and records those
  thresholds in coverage.
- Source/wheel packaging metadata now includes schema, skill, template, and built webapp assets
  needed by the installed CLI entry points.

## v0.6.1 - Human Bilingual Reports and Public Smoke Benchmark

### Added
- Human-first bilingual Markdown reports from the CLI assembler, with a Quick Read, scope,
  audit coverage, claim coverage, materials-needed table, verified traceability evidence,
  risk register, finding cards, action checklist, technical appendix, integrity boundary,
  and the existing machine-readable `AUDIT_JSON_SUMMARY` block.
- Regression tests that assert reports are bilingual, readable without raw detector JSON in
  the main body, preserve exactly one `AUDIT_JSON_SUMMARY` block, and summarize image evidence
  with reader-facing metrics.
- PPPR/public-concern benchmark scaffold under `benchmarks/pppr_integrity_benchmark/`, including
  a dataset card, data-ethics boundaries, finding-level label schema, source/label manifests,
  and offline scripts for RWDB/Crossref normalization, PubPeer manifest normalization, PMC OA
  local-package assembly, matched-control metadata, benchmark running, and audit-output evaluation.
- Documentation for PubPeer/RWDB/PMC OA/ORI benchmark use that explicitly treats PubPeer as case
  discovery / weak public-concern metadata, not misconduct ground truth, and forbids scraping,
  comment redistribution, and clean-paper labels for controls.
- Public-data smoke benchmark runner for ORI public image samples plus PMC Open Access S3 packages,
  with local package generation, source manifests, split/label generation, auditor execution, and
  evaluation. The archived summary (`public_smoke_2026-06-30`) records compact public-data smoke
  metrics without storing third-party article or image files.

### Changed
- Project version advanced to `0.6.1`.
- The report assembler now treats the Markdown body as the human reading surface and keeps
  raw detector payloads in supporting JSON artifacts / the final machine-readable summary.
- `make validate` now compiles nested benchmark helper scripts.

## v0.6.0 - Submission QC Packet

### Added
- Submission-QC artifact foundation: `audit_snapshot.json` with package file hashes,
  `file_hash_manifest.json`, optional `claim_coverage.json` / `.csv` from `claim_manifest.csv`,
  root-level `missing_materials.csv`, `verified_traceability.csv`, `unresolved_actions.csv`,
  and a `submission_qc_packet/` leave-behind bundle with report HTML/PDF exports and an
  `author_signoff.yaml` template.
- Re-audit comparison support through `scripts/compare_audit_runs.py` and
  `scripts/audit_package.py --compare-to`, summarizing changes in risk counts, missing materials,
  verified traceability, unresolved actions, and claim-evidence gaps without pass/fail language.
- Machine-readable submission-QC templates for `claim_manifest.csv`, author sign-off, ARRIVE 2.0,
  ICMJE authorship/disclosure, Nature image integrity, and Nature data/code/material availability.
- Local web app package-prep tools: inspect recommended package folders, create the scaffold
  without overwriting supplied files, and write `figure_assembly/assembly_manifest.csv` declared
  figure-to-source rows with package-relative path and relation-type validation.
- Package inventory guardrails for the local web app and assembly-manifest parser: bounded file/depth
  scanning, symlink skips, inventory warnings, and stricter relation-type/source-role validation so
  package prep cannot silently scan an overly broad directory or write semantically incompatible
  manifest rows.
- 16-bit TIFF real-image benchmark coverage for microscopy-derived duplicate detection.
- Required CI OCR gate: GitHub Actions installs `tesseract-ocr` and runs the scanned-PDF benchmark without skip mode.
- Same-image copy-move screening in the local patch detector, including coordinate evidence crops and contextual calibration.
- Default-orchestrator external literature phrase-search integration with deterministic fixture auto-detection, external-public Europe PMC auto mode, query/result provenance, and R1 provider-gap reporting.
- Audit Coverage / scope reporting: every report and `AUDIT_JSON_SUMMARY` now records which modules executed, which were not run (including methodology compliance and offline external search), how many image panels were screened, how many image files were unreadable, and a scope note stating that no findings in a module is not a guarantee of correctness.
- User self-audit onboarding: `docs/self-audit-guide.md` (non-developer guide to preparing materials, running the audit, reading the report, and which conclusions are not permitted), two runnable example packages under `examples/` (`minimal_package/` and `full_presubmission_package/`) with a deterministic image generator, and entry-point links from the README, SKILL, and architecture docs. A regression test asserts both examples run, expose an Audit Coverage block, carry no misconduct verdict, and (for the full package) show verified figure-to-raw traceability.
- Archived Codex-orchestrated eval evidence under `evals/llm_runs/2026-06-30-codex-orchestrated/`: 30 synthetic cases scored, 30 passed, 0 boundary violations, and 0 risk-cap violations, with a manifest that states this is not an independent third-party blinded LLM run.

### Changed
- Package manifest classification now respects the top-level recommended package directories before
  filename keyword heuristics, so `figure_assembly/assembly_manifest.csv` is no longer reported as
  a missing figure-assembly category while source-data files with `Figure_*` names remain source data.
- Project version advanced to `0.6.0`.
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
