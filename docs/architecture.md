# Architecture

This project is moving from a single Codex skill into a small research-integrity audit pipeline.

```text
material intake
-> structured extraction
-> detectors
-> contextual join
-> risk calibration
-> evidence ledger
-> human-reviewable report
```

The central rule is separation of duties:

- **Detectors** emit candidates with evidence and locations. They do not decide final risk.
- **Context joiners** add disclosed-reuse and source-availability context before calibration.
- **Calibrators** apply `schemas/risk_rules.yaml`, mode-specific caps, source-strength rules, benign-explanation requirements, and R4 requirements.
- **Reporters** express calibrated findings in neutral audit language and reject uncalibrated detector candidates.
- **Evals** test both recall and restraint.

## Default Entrypoint

Use `scripts/audit_package.py` for routine package audits. It is the only recommended default path:

```bash
python3 scripts/audit_package.py <package_dir> --mode internal_presubmission --output-dir audit_outputs/<case_id>
```

The orchestrator runs package inventory, source-data detectors, image detectors, contextual joining, risk calibration, calibrated-finding validation, report assembly, and audit-summary validation. Individual detector scripts remain useful for debugging and unit tests, but should not be the default workflow.

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

## Risk Calibration

`calibrators/risk_cap_engine.py` converts detector candidates into findings by loading `schemas/risk_rules.yaml`. Current caps:

- weak statistical or forensic signals max out at R2;
- completeness gaps max out at R1 unless other supplied materials contradict them;
- external public-material triage maxes out at R3;
- disclosed legitimate loading-control reuse with same-membrane/source context caps at R2;
- R4 requires a direct contradiction tag such as `source_to_figure_conflict` or `raw_record_conflict`;
- R3/R4 findings must include benign explanations, required materials, and a recommended action.

## P0 Detectors

- `detectors/image/global_near_duplicate.py`: global image near-duplicate clusters using average hash, dHash, pHash-style DCT, and D4 transforms.
- `detectors/stats/pseudoreplication_screen.py`: possible unit-of-analysis mismatch candidates from biological and technical replicate columns.
- `skill/.../stats_consistency_check.py`: direct summary consistency plus weak forensic statistical screens.

## Baseline Runner

`evals/run_script_baseline.py` delegates to `scripts/audit_package.py`. This separates detector failures, contextual-joining failures, calibration failures, and report-contract failures from LLM failures.
