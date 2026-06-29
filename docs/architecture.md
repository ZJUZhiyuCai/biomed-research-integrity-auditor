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
-> human-reviewable report
```

The central rule is separation of duties:

- **Detectors** emit candidates with evidence and locations. They do not decide final risk.
- **Provenance graph builders** model files as resources and declared figure/source relationships as edges.
- **Context joiners** add disclosed-reuse, source-availability, and provenance context before calibration.
- **Calibrators** apply `schemas/risk_rules.yaml`, mode-specific caps, source-strength rules, benign-explanation requirements, and R4 requirements.
- **Reporters** express calibrated findings in neutral audit language and reject uncalibrated detector candidates.
- **Evals** test both recall and restraint.

## Default Entrypoint

Use `scripts/audit_package.py` for routine package audits. It is the only recommended default path:

```bash
python3 scripts/audit_package.py <package_dir> --mode internal_presubmission --output-dir audit_outputs/<case_id>
```

The orchestrator runs package inventory, provenance graph construction, source-data detectors, image detectors, contextual joining, risk calibration, calibrated-finding validation, report assembly, and audit-summary validation. Individual detector scripts remain useful for debugging and unit tests, but should not be the default workflow.

## Provenance-First Negative Calibration

Similarity is not risk by itself. `provenance/build_resource_graph.py` creates resource nodes and declared provenance edges from `package_manifest.json`, `figure_source_map.json`, and `figure_assembly/assembly_manifest.csv`, `.yaml`, or `.txt`.

Structured assembly manifests are preferred over parsed free text. The parser reads only explicit fields such as `figure_panel`, `source_record`, `relation_type`, and `modality`; notes and prose are treated as audit material, not instructions.

The image contextual joiner classifies each similarity edge before calibration:

- `expected_traceability`: a declared figure-panel to raw/source relationship. This is positive provenance evidence and is not sent to the risk calibrator.
- `unresolved_fig_raw_similarity`: a figure-panel to raw/source similarity without a machine-readable provenance link. This is an R1 traceability gap.
- `cross_context_reuse_candidate`: a figure-panel to figure-panel similarity across presented panels without a disclosed/justified reuse context. This can remain R3.
- `local_patch_cross_context`: a region-level patch similarity across figure panels. This can remain R3, but it is still a candidate requiring raw/source review.
- disclosed loading-control reuse is capped according to the contextual tags in `schemas/risk_rules.yaml`.

This layer is designed to reduce high-risk false positives in clean-control and prompt-injection packages.

## Package-Internal Text Overlap

`detectors/text/text_overlap_screen.py` screens only text supplied inside the audit package: manuscript, supplement, prior drafts, thesis chapters, preprints, and lab previous papers. It does not query the web, publisher corpora, Crossref, PubMed, Google Scholar, or external plagiarism databases.

The detector normalizes paragraph text, assigns coarse sections, builds word n-gram shingles, and emits paragraph-pair candidates with overlap examples. Candidate types are calibrated by section and disclosure context:

- methods/protocol boilerplate is capped at R2;
- disclosed thesis or preprint-derived overlap is capped at R2 unless other supplied materials contradict the disclosure;
- undisclosed results overlap can remain R3;
- abstract or conclusion overlap can remain R2/R3 depending on supplied disclosure and journal-policy context.

Text overlap candidates are never plagiarism findings. Human review must check citation, prior-publication policy, thesis/preprint disclosure, journal requirements, and whether the overlap is standard methods language.

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

## Audit Summary Contract

Reports end with exactly one `AUDIT_JSON_SUMMARY` block. In addition to calibrated `findings`, the summary records:

- `positive_provenance`: declared figure-to-raw/source traceability entries such as `expected_traceability`.
- `traceability_gaps`: unresolved figure-to-raw/source similarities capped as R1 completeness gaps.

Positive provenance is not proof of authenticity; it only records traceability within supplied materials.

## Risk Calibration

`calibrators/risk_cap_engine.py` converts detector candidates into findings by loading `schemas/risk_rules.yaml`. Current caps:

- weak statistical or forensic signals max out at R2;
- completeness gaps max out at R1 unless other supplied materials contradict them;
- external public-material triage maxes out at R3;
- disclosed legitimate loading-control reuse with same-membrane/source context caps at R2;
- R4 requires a direct contradiction tag such as `source_to_figure_conflict` or `raw_record_conflict`;
- local patch similarity alone is capped at R3; `local_patch_direct_source_conflict` is required before a local patch path can reach R4;
- package-internal text overlap is capped at R3; methods boilerplate and disclosed thesis/preprint overlap are capped at R2;
- R3/R4 findings must include benign explanations, required materials, and a recommended action.

## P0 Detectors

- `detectors/image/global_near_duplicate.py`: global image near-duplicate clusters using average hash, dHash, pHash-style DCT, and D4 transforms.
- `detectors/image/local_patch_reuse.py`: conservative overlapping-tile local patch reuse candidates with D4 confirmation, normalized cross-correlation, and evidence crop export.
- `detectors/text/text_overlap_screen.py`: package-internal paragraph overlap candidates using section-aware n-gram similarity.
- `detectors/stats/pseudoreplication_screen.py`: possible unit-of-analysis mismatch candidates from biological and technical replicate columns.
- `skill/.../stats_consistency_check.py`: direct summary consistency plus weak forensic statistical screens.
- `provenance/parse_assembly_manifest.py`: declared figure-to-raw/source links from assembly manifests.
- `provenance/build_resource_graph.py`: package-level resource graph for provenance-aware calibration.

## Baseline Runner

`evals/run_script_baseline.py` delegates to `scripts/audit_package.py`. This separates detector failures, contextual-joining failures, calibration failures, and report-contract failures from LLM failures.
