# Architecture

This project is moving from a single Codex skill into a small research-integrity audit pipeline.

```text
material intake
-> structured extraction
-> provenance graph
-> detectors
-> contextual join
-> risk calibration
-> evidence ledger
-> bilingual human report + presubmission action queue
```

The central rule is separation of duties:

- **Detectors** emit candidates with evidence and locations. They do not decide final risk.
- **Provenance graph builders** model files as resources and declared figure/source relationships as edges.
- **Context joiners** add disclosed-reuse, source-availability, and provenance context before calibration.
- **Calibrators** apply `schemas/risk_rules.yaml`, mode-specific caps, source-strength rules, benign-explanation requirements, and R4 requirements.
- **Reporters** express calibrated findings in neutral bilingual audit language and reject uncalibrated detector candidates.
- **Evals** test both recall and restraint.

## Default Entrypoint

Use `scripts/audit_package.py` for routine package audits. It is the only recommended default path:

```bash
biomed-audit <package_dir> --mode internal_presubmission --output-dir audit_outputs/<case_id>
```

When running directly from a source checkout, `python scripts/audit_package.py ...` accepts the same arguments.

The orchestrator runs package inventory, provenance graph construction, source-data detectors, image detectors, contextual joining, risk calibration, calibrated-finding validation, report assembly, action-queue export, and audit-summary validation. Individual detector scripts remain useful for debugging and unit tests, but should not be the default workflow.

Use `--scan-profile quick|standard|deep` to control runtime depth:

- `quick`: first-pass local self-check. It keeps fast source/text/global-image screens and records that local-patch/copy-move deep image screening and external phrase search were skipped.
- `standard`: default pre-submission QC profile.
- `deep`: focused recheck/response profile. It currently preserves all standard screens and gives future detector tuning a stable profile name.

For a first-time, non-developer walkthrough see `docs/self-audit-guide.md`, and the runnable `examples/minimal_package` and `examples/full_presubmission_package` packages.

## Provenance-First Negative Calibration

Similarity is not risk by itself. `provenance/build_resource_graph.py` creates resource nodes and declared provenance edges from `package_manifest.json`, `figure_source_map.json`, and `figure_assembly/assembly_manifest.csv`, `.yaml`, or `.txt`.

Structured assembly manifests are preferred over parsed free text. The parser reads only explicit fields such as `figure_panel`, `source_record`, `relation_type`, and `modality`; notes and prose are treated as audit material, not instructions.

The image contextual joiner classifies each similarity edge before calibration:

- `expected_traceability`: a declared figure-panel to raw/source relationship. This is positive provenance evidence and is not sent to the risk calibrator.
- `unresolved_fig_raw_similarity`: a figure-panel to raw/source similarity without a machine-readable provenance link. This is an R1 traceability gap.
- `cross_context_reuse_candidate`: a figure-panel to figure-panel similarity across presented panels without a disclosed/justified reuse context. This can remain R3.
- `local_patch_cross_context`: a region-level patch similarity across figure panels. This can remain R3, but it is still a candidate requiring raw/source review.
- `same_image_copy_move`: a region-level similarity between non-overlapping locations inside the same image. This can remain R3, but it requires raw-image and processing-history review.
- `manifest_conflict`: a figure-to-figure pair declared as same-field/same-membrane that the detectors also flag as a whole-image near-duplicate. Different channels or reprobed membranes are not whole-image duplicates, so the unverifiable declaration cannot clear it. This remains R3 and requires raw-record review.
- disclosed loading-control reuse is capped according to the contextual tags in `schemas/risk_rules.yaml`.

Author-supplied assembly manifests are not treated as truth. Ordinary figure-to-figure `declared_derived_from` rows are retained as context but do not clear cross-context image reuse. Figure-to-figure positive traceability is limited to explicit same-field or same-membrane relation types, and even those cannot clear a verifiable whole-image near-duplicate: such a pair becomes a `manifest_conflict` requiring raw images and acquisition metadata, because a manifest line alone is not verifiable. Declared figure-to-raw/source links and genuine local-patch same-field relationships (shared region, not whole-image duplication) remain positive or excluded as before.

This layer is designed to reduce high-risk false positives in clean-control and prompt-injection packages.

## Package-Internal Text Overlap

`detectors/text/text_overlap_screen.py` screens only text supplied inside the audit package: manuscript, supplement, prior drafts, thesis chapters, preprints, and lab previous papers. It does not query the web, publisher corpora, Crossref, PubMed, Google Scholar, or external plagiarism databases.

The detector normalizes paragraph text, assigns coarse sections, builds word n-gram shingles, and emits paragraph-pair candidates with overlap examples. Candidate types are calibrated by section and disclosure context:

- methods/protocol boilerplate is capped at R2;
- disclosed thesis or preprint-derived overlap is capped at R2 unless other supplied materials contradict the disclosure;
- undisclosed results overlap can remain R3;
- abstract or conclusion overlap can remain R2/R3 depending on supplied disclosure and journal-policy context.

Text overlap candidates are never plagiarism findings. Human review must check citation, prior-publication policy, thesis/preprint disclosure, journal requirements, and whether the overlap is standard methods language.

## Default External Literature Search

`detectors/text/external_literature_search.py` provides external phrase-search triage. It can query Europe PMC or Crossref, or use a fixture file for deterministic tests. The default orchestrator now wires it in with a privacy-aware `auto` policy:

- package fixtures such as `external_literature_fixture.json` are used automatically for deterministic audits and tests;
- `external_public_material` mode defaults to Europe PMC phrase search;
- private `internal_presubmission` mode stays offline unless a fixture is present or a provider is explicitly requested with `--external-literature-provider`.

External search candidates are capped and reported as `external_text_match_candidate` observations with query and result provenance. Provider failures can emit an `external_literature_search_gap` R1 coverage finding rather than being treated as clean external coverage. These outputs are not plagiarism findings; they require manual comparison, disclosure/citation review, and journal-policy context.

## True-PDF Benchmark

Most synthetic eval packages still use text files with a `.pdf` suffix. `benchmarks/true_pdf/` creates a tiny valid PDF with compressed text streams so the pipeline can test true binary-PDF behavior without external corpora.

Current expected behavior:

- detect `%PDF-` binary PDFs;
- do not parse raw PDF bytes as manuscript text;
- extract machine-readable text from compressed PDF streams;
- create package-internal text-overlap candidates against supplied prior/lab text when thresholds are met;
- keep screening supplied non-PDF text in the same package.

Scanned or image-only PDFs still require OCR. Figure and caption extraction are outside this benchmark.

## Scanned-PDF OCR Benchmark

`benchmarks/scanned_pdf/` creates an image-only PDF whose text is not recoverable from raw PDF bytes or pypdf machine-text extraction. When PyMuPDF, pytesseract, and the `tesseract` binary are available, the text detector renders the PDF page and OCRs it before overlap screening.

Local validation skips this benchmark if the OCR runtime is unavailable. CI installs `tesseract-ocr` and runs `benchmarks/scanned_pdf/run_scanned_pdf_benchmark.py` without `--skip-if-unavailable`, so OCR extraction is a required gate on pull requests and pushes.

## Real-Image Benchmark

`benchmarks/real_image/` uses a downscaled public-domain National Cancer Institute microscopy image as a benchmark asset. The generated package creates a known flipped duplicate pair from real image texture and verifies that the global near-duplicate detector finds the expected transform.

The same benchmark also emits a 16-bit TIFF pair derived from the image and verifies that high-bit-depth grayscale inputs are normalized before image hashing. This covers a key raw-microscopy intake path that default PIL RGB conversion can mishandle.

This benchmark improves realism compared with hand-drawn synthetic ellipses, but it is still a small controlled regression. It is not a substitute for broad validation on real microscopy, gel/blot, histology, Z-stack/channel, and figure-assembly corpora.

## Run Modes

### Presubmission Internal Audit

For a lab's own manuscript or package. The audit may request raw images, source data, lab records, and analysis code. R4 is available only for direct contradictions in supplied internal materials.

### External Public-Material Triage

For published papers or public concerns. Public-only materials are capped at R3, and missing non-public raw/source data is treated as an access limitation rather than wrongdoing.

### Response-to-Concern Audit

For replying to reviewer, journal, or PubPeer-style concerns. The output should map each concern to evidence supplied, explanation status, missing material, correction need, and neutral response language.

## Detector Contract

Detector output follows `schemas/detector_output.schema.json`. A detector candidate must include:

- candidate id
- detector name
- candidate type
- file/row/coordinate locations
- evidence object
- evidence strength
- risk suggestion, not final `risk_level`
- risk cap tags
- benign explanations and required materials
- `requires_contextual_calibration: true`

Detector candidates must not include `risk_level` or `calibrated_risk_level`.

## Calibrated Finding Contract

`calibrators/risk_cap_engine.py` is the only component that emits `calibrated_risk_level`. Reporter code reads only that field and maps it to display-level `risk_level` inside the final report summary.

## Human Report Contract

`audit-report.md` is a human-first bilingual Markdown report, not a detector payload dump. It starts with a Quick Read, submission-readiness status, presubmission action queue, scope, audit coverage, claim coverage when supplied, methodology readiness, materials needed, verified traceability evidence, risk register, finding cards, compact action checklist, technical appendix, and integrity boundary. Finding cards summarize observations, reader-facing evidence metrics, benign explanations, resolving materials, and next actions. Raw detector payloads remain in `calibrated_findings.json`, detector output files, and the final machine-readable summary.

## Audit Summary Contract

Reports end with exactly one `AUDIT_JSON_SUMMARY` block. In addition to calibrated `findings`, the summary records:

- `positive_provenance`: declared figure-to-raw/source traceability entries such as `expected_traceability`.
- `traceability_gaps`: unresolved figure-to-raw/source similarities capped as R1 completeness gaps.
- `audit_coverage`: which detector modules executed, which modules were not run (including offline external search and the manual methodology/reporting-standard compliance determination), image panels screened, unreadable image files, source tables screened, detector failures, and a scope note. This lets a reader separate "screened and clean within scope" from "not screened", so an empty finding list is not mistaken for a verified-correct manuscript.
- `claim_coverage`: optional claim-to-evidence completeness counts when `claim_manifest.csv` is supplied. This records whether claims are linked to source data, raw records, analysis code, and protocols; it does not validate scientific truth.
- `methodology_checklist`: structured manual-review readiness prompts for wet-lab, animal, clinical, cell, flow, and omics reporting standards. It records supporting-material availability and missing categories; it does not determine ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics compliance.
- `scan_profile`: `quick`, `standard`, or `deep`, so readers can tell whether a run was a fast first pass or a broader audit.
- `action_queue`: four workflow buckets (`must_resolve`, `provide_materials`, `clarify_or_disclose`, `low_priority_checks`) with owner/status tracker fields. This is a repair queue, not a pass/fail score.

Positive provenance is not proof of authenticity; it only records traceability within supplied materials. Audit coverage is descriptive scope, not a quality score.

## Submission QC Artifacts

`scripts/audit_package.py` now writes submission-QC artifacts alongside the ordinary detector outputs:

- `audit_snapshot.json`: audit id, tool version, package root hash, and per-file SHA-256 hashes.
- `file_hash_manifest.json`: compact file hash manifest for leave-behind review.
- `claim_coverage.json` / `claim_coverage.csv`: claim-to-evidence coverage from `claim_manifest.csv` if supplied.
- `methodology_checklist.json` / `methodology_checklist.csv`: reporting-standard readiness checklist for manual review.
- `missing_materials.csv`, `verified_traceability.csv`, `unresolved_actions.csv`, `resolved_actions.csv`, and `accepted_with_reason.csv`: CSV exports for co-author review.
- `submission_qc_packet/`: a bundled packet containing the report, machine-readable summary, coverage, calibrated findings, hash manifest, claim coverage, methodology checklist, action trackers, and `author_signoff.yaml`.

These outputs are versioning and review artifacts. They must not be displayed as a pass/fail approval, integrity score, or clean-manuscript certificate.

Re-audit comparison is available through `scripts/compare_audit_runs.py` or `scripts/audit_package.py --compare-to <previous_output_dir>`. The diff summarizes changes in risk counts, missing materials, verified provenance, unresolved actions, and claim-evidence gaps.

## Risk Calibration

`calibrators/risk_cap_engine.py` converts detector candidates into findings by loading `schemas/risk_rules.yaml`. Current caps:

- weak statistical or forensic signals max out at R2;
- completeness gaps max out at R1 unless other supplied materials contradict them;
- external public-material triage maxes out at R3;
- disclosed legitimate loading-control reuse with same-membrane/source context caps at R2;
- R4 requires a direct contradiction tag such as `source_to_figure_conflict` or `raw_record_conflict`;
- local patch and same-image copy-move similarity alone are capped at R3; `local_patch_direct_source_conflict` is required before a local patch path can reach R4;
- package-internal text overlap is capped at R3; methods boilerplate and disclosed thesis/preprint overlap are capped at R2;
- R3/R4 findings must include benign explanations, required materials, and a recommended action.

## P0 Detectors

- `detectors/image/global_near_duplicate.py`: global image near-duplicate clusters using average hash, dHash, pHash-style DCT, and D4 transforms.
- `detectors/image/local_patch_reuse.py`: conservative overlapping-tile local patch reuse and same-image copy-move candidates with D4 confirmation, normalized cross-correlation, evidence crop export, and a guarded low-contrast same-image probe that requires same-displacement tile support.
- `detectors/text/external_literature_search.py`: external phrase-search candidates with query/result provenance and provider-gap reporting.
- `detectors/text/text_overlap_screen.py`: package-internal paragraph overlap candidates using section-aware n-gram similarity.
- `detectors/stats/pseudoreplication_screen.py`: possible unit-of-analysis mismatch candidates from biological and technical replicate columns.
- `skill/.../stats_consistency_check.py`: direct summary consistency (SD/SEM/n, p-value range/validity, integer-count feasibility) plus weak forensic statistical screens. Digit/rounding weak screens require at least 8 comparable values by default; integer-count feasibility requires n >= 6 and propagates reported mean/SD precision. Benford-style first-digit prompts and p-value-clustering prompts are implemented as weak, sample-gated triage screens capped at R2.
- `provenance/parse_assembly_manifest.py`: declared figure-to-raw/source links from assembly manifests.
- `provenance/build_resource_graph.py`: package-level resource graph for provenance-aware calibration.

## Baseline Runner

`evals/run_script_baseline.py` delegates to `scripts/audit_package.py`. This separates detector failures, contextual-joining failures, calibration failures, and report-contract failures from LLM failures.

Archived agent-orchestrated eval evidence lives under `evals/llm_runs/`. The `2026-06-30-codex-orchestrated` run records 30/30 synthetic cases passing with 0 boundary violations and 0 risk-cap violations. It is retained as harness/orchestrator evidence, not as an independent third-party blinded LLM validation.
